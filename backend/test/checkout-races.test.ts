import { describe, expect, it } from "vitest";
import { pool } from "../src/db/pool";
import { createProduct, createUser, eventTypes, getOrder, startServer, stockOf } from "./helpers";
import { fakeStripe } from "./fakes";

// The guarantees in the README's "Orders, stock and payments" section,
// exercised against a real Postgres with requests running concurrently.

const api = startServer();

function checkout(cookie: string, items: { productId: number; quantity: number }[]) {
  return api().post("/api/checkout/create-session").set("Cookie", cookie).send({ items });
}

describe("stock reservation under concurrency", () => {
  it("sells the last unit to exactly one of many simultaneous buyers", async () => {
    const productId = await createProduct({ stock: 1 });
    const buyers = await Promise.all(Array.from({ length: 12 }, () => createUser()));

    const responses = await Promise.all(buyers.map((b) => checkout(b.cookie, [{ productId, quantity: 1 }])));
    const statuses = responses.map((r) => r.status).sort();

    expect(statuses.filter((s) => s === 200)).toHaveLength(1);
    expect(statuses.filter((s) => s === 409)).toHaveLength(11);
    for (const r of responses.filter((r) => r.status === 409)) {
      expect(r.body.error.code).toBe("OUT_OF_STOCK");
    }
    expect(await stockOf(productId)).toBe(0);

    // Only the winner got an order, and only the winner reached Stripe.
    const { rows } = await pool.query(`SELECT status, stock_reserved FROM orders`);
    expect(rows).toEqual([{ status: "pending", stock_reserved: true }]);
    expect(fakeStripe.checkout.sessions.create).toHaveBeenCalledTimes(1);
  });

  it("never oversells when concurrent buyers want different quantities", async () => {
    const productId = await createProduct({ stock: 10 });
    const buyers = await Promise.all(Array.from({ length: 8 }, () => createUser()));
    const quantities = [3, 3, 3, 3, 2, 2, 1, 1]; // 18 wanted, 10 available

    const responses = await Promise.all(
      buyers.map((b, i) => checkout(b.cookie, [{ productId, quantity: quantities[i] }]))
    );
    const sold = responses.reduce((sum, r, i) => (r.status === 200 ? sum + quantities[i] : sum), 0);

    expect(sold).toBeLessThanOrEqual(10);
    expect(await stockOf(productId)).toBe(10 - sold);
    const { rows } = await pool.query(
      `SELECT COALESCE(sum(quantity), 0)::int AS reserved FROM order_items`
    );
    expect(rows[0].reserved).toBe(sold);
  });

  it("doesn't deadlock when carts lock the same products in opposite order", async () => {
    const a = await createProduct({ stock: 100 });
    const b = await createProduct({ stock: 100 });
    const buyers = await Promise.all(Array.from({ length: 10 }, () => createUser()));

    const responses = await Promise.all(
      buyers.map((buyer, i) =>
        checkout(
          buyer.cookie,
          i % 2 === 0
            ? [{ productId: a, quantity: 1 }, { productId: b, quantity: 1 }]
            : [{ productId: b, quantity: 1 }, { productId: a, quantity: 1 }]
        )
      )
    );

    expect(responses.map((r) => r.status)).toEqual(Array(10).fill(200));
    expect(await stockOf(a)).toBe(90);
    expect(await stockOf(b)).toBe(90);
  });

  it("merges repeated cart lines before checking stock", async () => {
    const productId = await createProduct({ stock: 3 });
    const buyer = await createUser();

    const res = await checkout(buyer.cookie, [
      { productId, quantity: 2 },
      { productId, quantity: 2 },
    ]);

    expect(res.status).toBe(409);
    expect(await stockOf(productId)).toBe(3);
  });

  it("rolls back the whole order when one product in the cart is short", async () => {
    const plenty = await createProduct({ stock: 50 });
    const scarce = await createProduct({ stock: 1 });
    const buyer = await createUser();

    const res = await checkout(buyer.cookie, [
      { productId: plenty, quantity: 5 },
      { productId: scarce, quantity: 2 },
    ]);

    expect(res.status).toBe(409);
    expect(await stockOf(plenty)).toBe(50);
    expect(await stockOf(scarce)).toBe(1);
    expect((await pool.query(`SELECT 1 FROM orders`)).rowCount).toBe(0);
  });

  it("uses server-side prices, whatever the client sends", async () => {
    const productId = await createProduct({ stock: 5, priceCents: 2500 });
    const buyer = await createUser();

    const res = await checkout(buyer.cookie, [
      { productId, quantity: 2, price_cents: 1 } as never,
    ]);

    expect(res.status).toBe(200);
    expect((await getOrder(res.body.orderId)).total_cents).toBe(5000);
  });
});

describe("Stripe failures", () => {
  it("cancels the order and returns its stock when the session can't be created", async () => {
    const productId = await createProduct({ stock: 2 });
    const buyer = await createUser();
    fakeStripe.checkout.sessions.create.mockRejectedValueOnce(new Error("Stripe is down"));

    const res = await checkout(buyer.cookie, [{ productId, quantity: 2 }]);

    expect(res.status).toBe(502);
    expect(res.body.error.code).toBe("PAYMENT_PROVIDER_ERROR");
    expect(await stockOf(productId)).toBe(2);
    const { rows } = await pool.query(`SELECT id, status, stock_reserved FROM orders`);
    expect(rows).toMatchObject([{ status: "cancelled", stock_reserved: false }]);
    expect(await eventTypes(rows[0].id)).toEqual(["created", "stock_released", "cancelled"]);
  });

  it("sends a per-order idempotency key so a retried call can't open a second session", async () => {
    const productId = await createProduct();
    const buyer = await createUser();

    const res = await checkout(buyer.cookie, [{ productId, quantity: 1 }]);

    const [, options] = fakeStripe.checkout.sessions.create.mock.calls[0];
    expect(options).toEqual({ idempotencyKey: `checkout-order-${res.body.orderId}` });
    expect(await eventTypes(res.body.orderId)).toEqual(["created", "checkout_session_created"]);
  });
});

describe("checkout guards", () => {
  it("requires a verified email", async () => {
    const productId = await createProduct();
    const buyer = await createUser(undefined, { verified: false });

    const res = await checkout(buyer.cookie, [{ productId, quantity: 1 }]);

    expect(res.status).toBe(403);
    expect(res.body.error.code).toBe("EMAIL_NOT_VERIFIED");
    expect(await stockOf(productId)).toBe(10);
  });

  it("requires a session", async () => {
    const res = await api().post("/api/checkout/create-session").send({ items: [{ productId: 1, quantity: 1 }] });
    expect(res.status).toBe(401);
    expect(res.body.error.code).toBe("UNAUTHENTICATED");
  });
});
