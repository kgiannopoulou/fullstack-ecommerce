import { beforeEach, describe, expect, it } from "vitest";
import { pool } from "../src/db/pool";
import { sweepExpiredReservations } from "../src/features/checkout/orderLifecycle";
import { createProduct, createUser, eventTypes, getOrder, sendWebhook, sessionEvent, startServer, stockOf } from "./helpers";
import { completeSession, fakeStripe, sessions } from "./fakes";

const api = startServer();

let admin: Awaited<ReturnType<typeof createUser>>;
let productId: number;

async function placeOrder(quantity = 1) {
  const buyer = await createUser();
  const res = await api()
    .post("/api/checkout/create-session")
    .set("Cookie", buyer.cookie)
    .send({ items: [{ productId, quantity }] });
  expect(res.status).toBe(200);
  return { orderId: res.body.orderId as number, sessionId: `cs_test_${res.body.orderId}`, buyer };
}

function setStatus(orderId: number, status: string) {
  return api().patch(`/api/admin/orders/${orderId}`).set("Cookie", admin.cookie).send({ status });
}

async function expireReservation(orderId: number) {
  await pool.query(`UPDATE orders SET reserved_until = now() - interval '1 minute' WHERE id = $1`, [orderId]);
}

beforeEach(async () => {
  admin = await createUser("admin@test.dev", { role: "admin" });
  productId = await createProduct({ stock: 10 });
});

describe("reservation sweeper", () => {
  it("cancels lapsed pending orders, expires their Stripe session and returns stock", async () => {
    const { orderId, sessionId } = await placeOrder(3);
    expect(await stockOf(productId)).toBe(7);
    await expireReservation(orderId);

    await sweepExpiredReservations();

    expect((await getOrder(orderId)).status).toBe("cancelled");
    expect(await stockOf(productId)).toBe(10);
    expect(sessions.get(sessionId)!.status).toBe("expired");
  });

  it("leaves orders whose reservation hasn't lapsed", async () => {
    const { orderId } = await placeOrder();
    await sweepExpiredReservations();
    expect((await getOrder(orderId)).status).toBe("pending");
  });

  it("marks the order paid instead if the customer paid but the webhook was missed", async () => {
    const { orderId, sessionId } = await placeOrder(2);
    completeSession(sessionId);
    await expireReservation(orderId);

    await sweepExpiredReservations();

    expect((await getOrder(orderId)).status).toBe("paid");
    expect(await stockOf(productId)).toBe(8);
  });

  it("is safe to run concurrently with itself", async () => {
    const orders = await Promise.all([placeOrder(1), placeOrder(2), placeOrder(3)]);
    for (const { orderId } of orders) await expireReservation(orderId);

    await Promise.all([sweepExpiredReservations(), sweepExpiredReservations(), sweepExpiredReservations()]);

    expect(await stockOf(productId)).toBe(10);
    for (const { orderId } of orders) {
      expect((await eventTypes(orderId)).filter((t) => t === "stock_released")).toHaveLength(1);
    }
  });

  it("cleans up an order whose Stripe session was never stored", async () => {
    const { orderId } = await placeOrder(4);
    await pool.query(`UPDATE orders SET stripe_session_id = NULL WHERE id = $1`, [orderId]);
    await expireReservation(orderId);

    await sweepExpiredReservations();

    expect((await getOrder(orderId)).status).toBe("cancelled");
    expect(await stockOf(productId)).toBe(10);
  });
});

describe("admin status changes", () => {
  it("allows only the documented transitions", async () => {
    const { orderId, sessionId } = await placeOrder();

    const toPaid = await setStatus(orderId, "paid");
    expect(toPaid.status).toBe(409);
    expect(toPaid.body.error.code).toBe("INVALID_TRANSITION");

    await sendWebhook(api, sessionEvent("checkout.session.completed", completeSession(sessionId)));
    expect((await setStatus(orderId, "shipped")).status).toBe(200);
    expect((await setStatus(orderId, "pending")).status).toBe(409);
    expect((await setStatus(orderId, "cancelled")).status).toBe(409);
  });

  it("cancelling a paid order returns stock once, and a replayed payment can't revive it", async () => {
    const { orderId, sessionId } = await placeOrder(2);
    const paid = sessionEvent("checkout.session.completed", completeSession(sessionId));
    await sendWebhook(api, paid);

    expect((await setStatus(orderId, "cancelled")).status).toBe(200);
    expect((await setStatus(orderId, "cancelled")).status).toBe(409);
    await sendWebhook(api, { ...paid, id: "evt_replayed_later" });

    expect((await getOrder(orderId)).status).toBe("cancelled");
    expect(await stockOf(productId)).toBe(10);
  });

  it("cancelling a pending order expires its Stripe session first", async () => {
    const { orderId, sessionId } = await placeOrder(5);

    const res = await setStatus(orderId, "cancelled");

    expect(res.status).toBe(200);
    expect(sessions.get(sessionId)!.status).toBe("expired");
    expect(await stockOf(productId)).toBe(10);
  });

  it("reports when the customer paid while the admin was cancelling", async () => {
    const { orderId, sessionId } = await placeOrder();
    // The session completes between our retrieve and expire calls.
    fakeStripe.checkout.sessions.expire.mockImplementationOnce(async () => {
      completeSession(sessionId);
      throw new Error("Session is not open");
    });

    const res = await setStatus(orderId, "cancelled");

    expect(res.status).toBe(409);
    expect(res.body.error.message).toMatch(/just paid/);
    expect((await getOrder(orderId)).status).toBe("paid");
  });

  it("an admin cancel racing the payment webhook never moves stock twice", async () => {
    const { orderId, sessionId } = await placeOrder(3);
    const paid = sessionEvent("checkout.session.completed", completeSession(sessionId));
    // The session is already complete on Stripe's side, so the admin path
    // will see that too; both paths contend for the order row lock.
    await Promise.all([setStatus(orderId, "cancelled"), sendWebhook(api, paid)]);

    const order = await getOrder(orderId);
    expect(order.status).toBe("paid");
    expect(await stockOf(productId)).toBe(7);
  });
});

describe("audit trail", () => {
  it("records who did what, in order", async () => {
    const { orderId, sessionId } = await placeOrder(2);
    await sendWebhook(api, sessionEvent("checkout.session.completed", completeSession(sessionId)));
    await setStatus(orderId, "shipped");

    const res = await api().get(`/api/admin/orders/${orderId}/history`).set("Cookie", admin.cookie);

    expect(res.status).toBe(200);
    expect(
      res.body.history.map((e: { type: string; actor: string; to_status: string | null }) => [e.type, e.actor, e.to_status])
    ).toEqual([
      ["created", "customer", "pending"],
      ["checkout_session_created", "system", null],
      ["paid", "stripe", "paid"],
      ["shipped", "admin", "shipped"],
    ]);
    expect(res.body.history[3].actor_email).toBe("admin@test.dev");
  });

  it("lets customers see their own order history but not anyone else's", async () => {
    const { orderId, buyer } = await placeOrder();
    const stranger = await createUser();

    const own = await api().get(`/api/orders/${orderId}`).set("Cookie", buyer.cookie);
    const other = await api().get(`/api/orders/${orderId}`).set("Cookie", stranger.cookie);

    expect(own.status).toBe(200);
    expect(own.body.history.map((e: { type: string }) => e.type)).toEqual(["created", "checkout_session_created"]);
    expect(own.body.history[0]).not.toHaveProperty("actor_email");
    expect(other.status).toBe(404);
  });

  it("is admin-only", async () => {
    const { orderId, buyer } = await placeOrder();
    const res = await api().get(`/api/admin/orders/${orderId}/history`).set("Cookie", buyer.cookie);
    expect(res.status).toBe(403);
  });
});
