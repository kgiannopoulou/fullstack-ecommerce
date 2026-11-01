import { PoolClient } from "pg";
import Stripe from "stripe";
import { pool } from "../../db/pool";
import { stripe } from "../../lib/stripe";

// Every change to an order's status or to the stock it holds goes through
// this file, so the rules live in one place:
//
//   - Stock is taken when the order is created (reserveStock) and given back
//     only through releaseOrderStock. Both check-and-flip the order's
//     `stock_reserved` flag in the same transaction, so stock can never be
//     taken or returned twice for one order, whatever happens to `status`.
//   - `paid_at` is set exactly once, the first time a payment for the order
//     is processed. A replayed webhook sees it and does nothing.
//   - Every change is written to order_events in the same transaction, so
//     the audit trail always matches the order row.

// Checkout sessions stay payable for 30 minutes (Stripe's minimum), and the
// stock is held a few minutes longer so the session is guaranteed to have
// expired on Stripe's side before the sweeper gives the stock back.
export const CHECKOUT_SESSION_MINUTES = 30;
export const RESERVATION_MINUTES = CHECKOUT_SESSION_MINUTES + 5;

export class OutOfStockError extends Error {
  constructor(public productId: number) {
    super(`Not enough stock for product ${productId}`);
  }
}

// --- Audit trail ----------------------------------------------------------

// Who caused a change: the customer (checkout), Stripe (a webhook), the
// system (the reservation sweeper, or cleanup after a Stripe error) or an
// admin (with their user id).
export type Actor =
  | { kind: "customer"; userId: number }
  | { kind: "stripe" }
  | { kind: "system" }
  | { kind: "admin"; userId: number };

export type OrderEventType =
  | "created"
  | "checkout_session_created"
  | "paid"
  | "stock_reacquired"
  | "stock_released"
  | "refunded"
  | "cancelled"
  | "shipped";

export async function recordOrderEvent(
  client: PoolClient,
  orderId: number,
  type: OrderEventType,
  actor: Actor,
  change: { from?: string | null; to?: string | null; data?: Record<string, unknown> } = {}
) {
  await client.query(
    `INSERT INTO order_events (order_id, type, from_status, to_status, actor, actor_user_id, data)
     VALUES ($1, $2, $3, $4, $5, $6, $7)`,
    [
      orderId,
      type,
      change.from ?? null,
      change.to ?? null,
      actor.kind,
      "userId" in actor ? actor.userId : null,
      change.data ?? {},
    ]
  );
}

// --- Stock ----------------------------------------------------------------

// Atomically decrements stock for each item, failing (and leaving the
// caller's transaction to be rolled back) if any product doesn't have
// enough. `stock >= $1` in the WHERE clause plus Postgres's row lock means
// two concurrent checkouts for the last unit can't both succeed: the second
// one waits for the first to commit, then sees the new stock and matches no
// row. Items are locked in product-id order so two carts with the same
// products can't deadlock.
export async function reserveStock(
  client: PoolClient,
  items: { productId: number; quantity: number }[]
) {
  const sorted = [...items].sort((a, b) => a.productId - b.productId);
  for (const item of sorted) {
    const { rowCount } = await client.query(
      `UPDATE products SET stock = stock - $1 WHERE id = $2 AND stock >= $1`,
      [item.quantity, item.productId]
    );
    if (rowCount === 0) {
      throw new OutOfStockError(item.productId);
    }
  }
}

async function orderItems(client: PoolClient, orderId: number) {
  const { rows } = await client.query<{ product_id: number; quantity: number }>(
    `SELECT product_id, quantity FROM order_items WHERE order_id = $1 ORDER BY product_id`,
    [orderId]
  );
  return rows.map((row) => ({ productId: row.product_id, quantity: row.quantity }));
}

// Gives an order's stock back, if (and only if) it is currently holding it.
export async function releaseOrderStock(client: PoolClient, orderId: number, actor: Actor) {
  const { rowCount } = await client.query(
    `UPDATE orders SET stock_reserved = FALSE WHERE id = $1 AND stock_reserved`,
    [orderId]
  );
  if (rowCount === 0) return;
  const items = await orderItems(client, orderId);
  for (const item of items) {
    await client.query(`UPDATE products SET stock = stock + $1 WHERE id = $2`, [
      item.quantity,
      item.productId,
    ]);
  }
  await recordOrderEvent(client, orderId, "stock_released", actor, { data: { items } });
}

// Re-takes stock for an order whose reservation was already released (e.g.
// payment arrived after the sweeper cancelled it). Returns false, with no
// changes made, if the stock is no longer available.
async function tryReacquireOrderStock(client: PoolClient, orderId: number) {
  await client.query("SAVEPOINT reacquire");
  try {
    await reserveStock(client, await orderItems(client, orderId));
    await client.query(`UPDATE orders SET stock_reserved = TRUE WHERE id = $1`, [orderId]);
    await client.query("RELEASE SAVEPOINT reacquire");
    return true;
  } catch (err) {
    await client.query("ROLLBACK TO SAVEPOINT reacquire");
    if (err instanceof OutOfStockError) return false;
    throw err;
  }
}

export async function inTransaction<T>(fn: (client: PoolClient) => Promise<T>): Promise<T> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const result = await fn(client);
    await client.query("COMMIT");
    return result;
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

type LockedOrder = {
  id: number;
  status: string;
  stock_reserved: boolean;
  paid_at: Date | null;
  stripe_session_id: string | null;
};

// SELECT ... FOR UPDATE serializes everything that touches one order
// (webhook, sweeper, admin), so they can't interleave half-way.
async function lockOrder(client: PoolClient, orderId: number) {
  const { rows } = await client.query<LockedOrder>(
    `SELECT id, status, stock_reserved, paid_at, stripe_session_id
     FROM orders WHERE id = $1 FOR UPDATE`,
    [orderId]
  );
  return rows[0] as LockedOrder | undefined;
}

// --- Transitions ----------------------------------------------------------

// Called when Stripe reports a successful payment. Safe to call any number
// of times for the same order.
//
// Normally the order is still pending and holding its stock, so it simply
// becomes 'paid'. If its reservation was already released (it expired, or
// the request that stores the session id failed), the stock is taken again;
// if that's no longer possible the customer is refunded automatically and
// the order is cancelled, so nobody ends up charged for an order stuck in
// 'pending'.
export async function markOrderPaid(
  orderId: number,
  paymentIntentId: string | null,
  actor: Actor = { kind: "stripe" }
) {
  await inTransaction(async (client) => {
    const order = await lockOrder(client, orderId);
    if (!order || order.paid_at) return; // unknown order, or payment already processed

    const hadStock = order.stock_reserved;
    if (hadStock || (await tryReacquireOrderStock(client, orderId))) {
      if (!hadStock) await recordOrderEvent(client, orderId, "stock_reacquired", actor);
      await client.query(
        `UPDATE orders SET status = 'paid', paid_at = now(), reserved_until = NULL WHERE id = $1`,
        [orderId]
      );
      await recordOrderEvent(client, orderId, "paid", actor, {
        from: order.status,
        to: "paid",
        data: { paymentIntentId },
      });
      return;
    }

    await client.query(
      `UPDATE orders SET status = 'cancelled', paid_at = now(), reserved_until = NULL WHERE id = $1`,
      [orderId]
    );
    // Refunded before COMMIT: if Stripe errors, the transaction rolls back,
    // the webhook returns 500 and Stripe retries it. The idempotency key
    // makes sure a retry can't refund twice.
    if (paymentIntentId) {
      await stripe.refunds.create(
        { payment_intent: paymentIntentId, reason: "requested_by_customer" },
        { idempotencyKey: `refund-order-${orderId}` }
      );
    }
    await recordOrderEvent(client, orderId, "refunded", actor, {
      from: order.status,
      to: "cancelled",
      data: { paymentIntentId, reason: "stock_unavailable" },
    });
    console.warn(`Order ${orderId}: paid after its stock was gone; refunded and cancelled.`);
  });
}

// Cancels an order that is still pending and gives its stock back. Returns
// false (changing nothing) if the order isn't pending any more.
export async function cancelPendingOrder(orderId: number, actor: Actor, reason: string) {
  return inTransaction(async (client) => {
    const order = await lockOrder(client, orderId);
    if (!order || order.status !== "pending") return false;
    await releaseOrderStock(client, orderId, actor);
    await client.query(
      `UPDATE orders SET status = 'cancelled', reserved_until = NULL WHERE id = $1`,
      [orderId]
    );
    await recordOrderEvent(client, orderId, "cancelled", actor, {
      from: "pending",
      to: "cancelled",
      data: { reason },
    });
    return true;
  });
}

// Cancels a pending order whose Stripe session may still be open. The
// session is expired on Stripe's side first, so the customer can't pay
// after their stock has been given back. If it turns out the customer has
// already paid, the order is marked paid instead.
// Returns 'cancelled' or 'paid' for what happened, or null if the order was
// left alone (no longer pending, or still awaiting an asynchronous payment).
export async function expireAndCancelOrder(
  orderId: number,
  actor: Actor,
  reason: string
): Promise<"cancelled" | "paid" | null> {
  const { rows } = await pool.query<{ stripe_session_id: string | null }>(
    `SELECT stripe_session_id FROM orders WHERE id = $1`,
    [orderId]
  );
  const sessionId = rows[0]?.stripe_session_id;

  if (sessionId) {
    let session: Stripe.Checkout.Session = await stripe.checkout.sessions.retrieve(sessionId);
    if (session.status === "open") {
      try {
        session = await stripe.checkout.sessions.expire(sessionId);
      } catch (err) {
        // Most likely the customer completed payment in the meantime.
        session = await stripe.checkout.sessions.retrieve(sessionId);
        if (session.status === "open") throw err;
      }
    }
    if (session.status === "complete") {
      if (session.payment_status !== "paid") return null;
      await markOrderPaid(orderId, paymentIntentId(session), { kind: "system" });
      return "paid";
    }
  }

  return (await cancelPendingOrder(orderId, actor, reason)) ? "cancelled" : null;
}

export function paymentIntentId(session: Stripe.Checkout.Session) {
  const pi = session.payment_intent;
  return typeof pi === "string" ? pi : pi?.id ?? null;
}

// Cleans up abandoned checkouts: every pending order whose reservation has
// lapsed is cancelled and its stock returned. This also covers orders whose
// Stripe session was never created (Stripe was down, or the server crashed
// between saving the order and calling Stripe).
export async function sweepExpiredReservations() {
  const { rows } = await pool.query<{ id: number }>(
    `SELECT id FROM orders
     WHERE status = 'pending' AND (reserved_until IS NULL OR reserved_until < now())
     ORDER BY id LIMIT 100`
  );
  for (const { id } of rows) {
    try {
      await expireAndCancelOrder(id, { kind: "system" }, "reservation_expired");
    } catch (err) {
      // Leave it for the next sweep rather than aborting the whole batch.
      console.error(`Failed to clean up expired order ${id}:`, err);
    }
  }
}

export function startReservationSweeper(intervalMs = 60_000) {
  const run = () => sweepExpiredReservations().catch((err) => console.error("Sweeper failed:", err));
  run();
  return setInterval(run, intervalMs);
}

// --- Admin status changes -------------------------------------------------

// The only manual moves an admin can make. Orders never go back to
// 'pending', and 'paid' can only be set by a confirmed Stripe payment
// (markOrderPaid), never by hand.
export const ADMIN_TRANSITIONS: Record<string, string[]> = {
  pending: ["cancelled"],
  paid: ["shipped", "cancelled"],
  shipped: [],
  cancelled: [],
};

export class InvalidTransitionError extends Error {}

export async function adminSetStatus(orderId: number, next: string, adminUserId: number) {
  const actor: Actor = { kind: "admin", userId: adminUserId };
  const current = await inTransaction(async (client) => {
    const order = await lockOrder(client, orderId);
    if (!order) return null;
    if (!ADMIN_TRANSITIONS[order.status]?.includes(next)) {
      throw new InvalidTransitionError(
        `Cannot change an order from '${order.status}' to '${next}'`
      );
    }
    if (order.status === "paid") {
      // paid -> shipped, or paid -> cancelled (stock goes back on the
      // shelf; any refund is issued from the Stripe dashboard). paid_at stays
      // set, so a replayed payment webhook can't resurrect this order.
      if (next === "cancelled") await releaseOrderStock(client, orderId, actor);
      await client.query(`UPDATE orders SET status = $1 WHERE id = $2`, [next, orderId]);
      await recordOrderEvent(client, orderId, next === "shipped" ? "shipped" : "cancelled", actor, {
        from: "paid",
        to: next,
        ...(next === "cancelled" ? { data: { reason: "admin" } } : {}),
      });
    }
    return order.status;
  });
  if (current === null) return null;

  // pending -> cancelled has to talk to Stripe (expire the open session), so
  // it's done outside the transaction above.
  if (current === "pending") {
    const result = await expireAndCancelOrder(orderId, actor, "admin");
    if (result !== "cancelled") {
      throw new InvalidTransitionError(
        result === "paid"
          ? "The customer has just paid for this order, so it was marked paid instead"
          : "The order changed while it was being cancelled; refresh and try again"
      );
    }
  }

  const { rows } = await pool.query(`SELECT * FROM orders WHERE id = $1`, [orderId]);
  return rows[0];
}

// Full history of one order, oldest first.
export async function orderHistory(orderId: number) {
  const { rows } = await pool.query(
    `SELECT e.id, e.type, e.from_status, e.to_status, e.actor, e.data, e.created_at,
            u.email AS actor_email
     FROM order_events e LEFT JOIN users u ON u.id = e.actor_user_id
     WHERE e.order_id = $1 ORDER BY e.id`,
    [orderId]
  );
  return rows;
}
