import { beforeEach, describe, expect, it } from "vitest";
import { pool } from "../src/db/pool";
import {
  createProduct,
  createUser,
  eventTypes,
  getOrder,
  sendWebhook,
  sessionEvent,
  startServer,
  stockOf,
} from "./helpers";
import { completeSession, fakeStripe, sessions } from "./fakes";

// Stripe delivers webhooks at least once, possibly out of order, possibly
// concurrently. These tests replay events the way Stripe can and check that
// stock and payment state only ever move once.

const api = startServer();

let productId: number;
let orderId: number;
let sessionId: string;

beforeEach(async () => {
  productId = await createProduct({ stock: 5 });
  const buyer = await createUser();
  const res = await api()
    .post("/api/checkout/create-session")
    .set("Cookie", buyer.cookie)
    .send({ items: [{ productId, quantity: 2 }] });
  expect(res.status).toBe(200);
  orderId = res.body.orderId;
  sessionId = `cs_test_${orderId}`;
});

function paidEvent(eventId?: string) {
  return sessionEvent("checkout.session.completed", completeSession(sessionId), eventId);
}

function expiredEvent(eventId?: string) {
  return sessionEvent("checkout.session.expired", sessions.get(sessionId)!, eventId);
}

describe("signature verification", () => {
  it("rejects an unsigned request", async () => {
    const res = await api().post("/api/webhooks/stripe").set("Content-Type", "application/json").send("{}");
    expect(res.status).toBe(400);
  });

  it("rejects an event signed with the wrong secret", async () => {
    const res = await sendWebhook(api, paidEvent(), "whsec_attacker");
    expect(res.status).toBe(400);
    expect((await getOrder(orderId)).status).toBe("pending");
  });
});

describe("payment succeeded", () => {
  it("marks the order paid and keeps the reserved stock taken", async () => {
    const res = await sendWebhook(api, paidEvent());

    expect(res.status).toBe(200);
    const order = await getOrder(orderId);
    expect(order).toMatchObject({ status: "paid", stock_reserved: true });
    expect(order.paid_at).not.toBeNull();
    expect(await stockOf(productId)).toBe(3);
  });

  it("acknowledges a replay of the same event id without processing it again", async () => {
    const event = paidEvent("evt_same");

    const first = await sendWebhook(api, event);
    const second = await sendWebhook(api, event);

    expect(first.body).toEqual({ received: true });
    expect(second.body).toEqual({ received: true, duplicate: true });
    expect(await eventTypes(orderId)).toEqual(["created", "checkout_session_created", "paid"]);
  });

  it("is idempotent for the same payment delivered as different events", async () => {
    // e.g. checkout.session.completed and async_payment_succeeded, or a
    // re-sent event with a new id.
    await sendWebhook(api, paidEvent());
    await sendWebhook(api, sessionEvent("checkout.session.async_payment_succeeded", sessions.get(sessionId)!));
    await sendWebhook(api, paidEvent());

    expect(await stockOf(productId)).toBe(3);
    expect((await eventTypes(orderId)).filter((t) => t === "paid")).toHaveLength(1);
  });

  it("handles concurrent duplicate deliveries without double-processing", async () => {
    const event = paidEvent("evt_concurrent");

    const responses = await Promise.all(Array.from({ length: 8 }, () => sendWebhook(api, event)));

    expect(responses.every((r) => r.status === 200)).toBe(true);
    expect(await stockOf(productId)).toBe(3);
    expect((await eventTypes(orderId)).filter((t) => t === "paid")).toHaveLength(1);
    const { rows } = await pool.query(`SELECT count(*)::int AS n FROM stripe_webhook_events WHERE id = 'evt_concurrent'`);
    expect(rows[0].n).toBe(1);
  });

  it("ignores a completed session that isn't actually paid yet", async () => {
    const session = completeSession(sessionId);
    session.payment_status = "unpaid";
    await sendWebhook(api, sessionEvent("checkout.session.completed", session));
    expect((await getOrder(orderId)).status).toBe("pending");
  });
});

describe("session expired", () => {
  it("cancels the order and returns its stock exactly once", async () => {
    await sendWebhook(api, expiredEvent());
    await sendWebhook(api, expiredEvent()); // replayed with a new id
    await sendWebhook(api, expiredEvent("evt_x"));
    await sendWebhook(api, expiredEvent("evt_x")); // same id again

    expect((await getOrder(orderId)).status).toBe("cancelled");
    expect(await stockOf(productId)).toBe(5);
    expect(await eventTypes(orderId)).toEqual([
      "created",
      "checkout_session_created",
      "stock_released",
      "cancelled",
    ]);
  });

  it("can't cancel an order that is already paid (out-of-order delivery)", async () => {
    await sendWebhook(api, paidEvent());
    await sendWebhook(api, expiredEvent());

    expect((await getOrder(orderId)).status).toBe("paid");
    expect(await stockOf(productId)).toBe(3);
  });
});

describe("payment after the reservation was released", () => {
  beforeEach(async () => {
    // The session expired and the stock went back on the shelf...
    await sendWebhook(api, expiredEvent());
    expect(await stockOf(productId)).toBe(5);
  });

  it("takes the stock again if it's still available", async () => {
    await sendWebhook(api, paidEvent());

    expect(await getOrder(orderId)).toMatchObject({ status: "paid", stock_reserved: true });
    expect(await stockOf(productId)).toBe(3);
    expect(fakeStripe.refunds.create).not.toHaveBeenCalled();
    expect((await eventTypes(orderId)).slice(-2)).toEqual(["stock_reacquired", "paid"]);
  });

  it("refunds automatically, exactly once, if the stock is gone", async () => {
    await pool.query(`UPDATE products SET stock = 1 WHERE id = $1`, [productId]); // someone else bought it

    await sendWebhook(api, paidEvent());
    await sendWebhook(api, paidEvent()); // retried delivery

    const order = await getOrder(orderId);
    expect(order).toMatchObject({ status: "cancelled", stock_reserved: false });
    expect(order.paid_at).not.toBeNull();
    expect(await stockOf(productId)).toBe(1);
    expect(fakeStripe.refunds.create).toHaveBeenCalledTimes(1);
    expect(fakeStripe.refunds.create).toHaveBeenCalledWith(
      { payment_intent: `pi_${sessionId}`, reason: "requested_by_customer" },
      { idempotencyKey: `refund-order-${orderId}` }
    );
    expect(await eventTypes(orderId)).toContain("refunded");
  });

  it("returns 500 and leaves everything unchanged if the refund call fails, so Stripe retries", async () => {
    await pool.query(`UPDATE products SET stock = 0 WHERE id = $1`, [productId]);
    fakeStripe.refunds.create.mockRejectedValueOnce(new Error("Stripe is down"));

    const failed = await sendWebhook(api, paidEvent("evt_retry"));
    expect(failed.status).toBe(500);
    expect((await getOrder(orderId)).paid_at).toBeNull();

    // Stripe's retry of the same event id is processed, not skipped.
    const retried = await sendWebhook(api, paidEvent("evt_retry"));
    expect(retried.body).toEqual({ received: true });
    expect(fakeStripe.refunds.create).toHaveBeenCalledTimes(2);
    expect((await getOrder(orderId)).status).toBe("cancelled");
  });
});
