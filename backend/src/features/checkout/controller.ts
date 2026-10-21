import { Request, Response } from "express";
import { z } from "zod";
import { env } from "../../config/env";
import { pool } from "../../db/pool";
import { HttpError } from "../../middleware/errorHandler";
import { stripe } from "../../lib/stripe";
import Stripe from "stripe";
import {
  CHECKOUT_SESSION_MINUTES,
  OutOfStockError,
  RESERVATION_MINUTES,
  cancelPendingOrder,
  inTransaction,
  markOrderPaid,
  paymentIntentId,
  recordOrderEvent,
  reserveStock,
} from "./orderLifecycle";

export const MAX_QUANTITY_PER_PRODUCT = 99;

// The client only ever sends { productId, quantity } pairs — never a price.
// Prices are always looked up server-side from the database below, so a
// tampered client request can't check out at an arbitrary price.
const createSessionSchema = z.object({
  items: z
    .array(
      z.object({
        productId: z.number().int().positive(),
        quantity: z.number().int().positive().max(MAX_QUANTITY_PER_PRODUCT),
      })
    )
    .min(1)
    .max(50),
});

// Called when a signed-in user clicks "Checkout". Validates the cart against
// the database, records a 'pending' order *and reserves its stock* in one
// transaction, then hands off to Stripe's hosted Checkout page. The order is
// only marked 'paid' later, by the stripeWebhook handler below, once Stripe
// confirms payment actually succeeded — never directly from this request.
//
// Reserving stock up front (instead of decrementing it when the payment
// webhook arrives) is what stops two customers from both paying for the last
// unit: the second checkout is rejected here, before Stripe is involved.
// Unpaid reservations are given back when the Stripe session expires, see
// orderLifecycle.ts.
export async function createCheckoutSession(req: Request, res: Response) {
  const { items } = createSessionSchema.parse(req.body);
  const user = req.user!; // guaranteed present: this route is behind requireAuth

  // The same product can appear on several lines of the request. Merge them
  // first, so stock is checked against the *total* quantity per product
  // rather than each line on its own.
  const quantityById = new Map<number, number>();
  for (const item of items) {
    quantityById.set(item.productId, (quantityById.get(item.productId) ?? 0) + item.quantity);
  }
  const wanted = [...quantityById].map(([productId, quantity]) => ({ productId, quantity }));
  for (const item of wanted) {
    if (item.quantity > MAX_QUANTITY_PER_PRODUCT) {
      throw new HttpError(400, `At most ${MAX_QUANTITY_PER_PRODUCT} of each product per order`);
    }
  }

  // Order + order_items + the stock reservation + the audit event are
  // written in one transaction: either the order exists and holds its
  // stock, or nothing changed at all.
  const client = await pool.connect();
  let orderId: number;
  const lineItems: Stripe.Checkout.SessionCreateParams.LineItem[] = [];
  try {
    await client.query("BEGIN");

    const { rows: products } = await client.query(
      `SELECT id, name, price_cents FROM products WHERE id = ANY($1::int[])`,
      [wanted.map((item) => item.productId)]
    );
    const productById = new Map(products.map((p) => [p.id, p]));

    let totalCents = 0;
    for (const item of wanted) {
      const product = productById.get(item.productId);
      if (!product) {
        throw new HttpError(400, `Product ${item.productId} not found`);
      }
      totalCents += product.price_cents * item.quantity;
      lineItems.push({
        quantity: item.quantity,
        price_data: {
          currency: "usd",
          unit_amount: product.price_cents, // Stripe also expects integer cents
          product_data: { name: product.name },
        },
      });
    }

    try {
      await reserveStock(client, wanted);
    } catch (err) {
      if (err instanceof OutOfStockError) {
        const name = productById.get(err.productId)?.name ?? `product ${err.productId}`;
        throw new HttpError(409, `Not enough stock for ${name}`, "OUT_OF_STOCK");
      }
      throw err;
    }

    const { rows } = await client.query(
      `INSERT INTO orders (user_id, status, total_cents, stock_reserved, reserved_until)
       VALUES ($1, 'pending', $2, TRUE, now() + make_interval(mins => $3))
       RETURNING id`,
      [user.id, totalCents, RESERVATION_MINUTES]
    );
    orderId = rows[0].id;

    for (const item of wanted) {
      await client.query(
        `INSERT INTO order_items (order_id, product_id, quantity, price_cents) VALUES ($1, $2, $3, $4)`,
        [orderId, item.productId, item.quantity, productById.get(item.productId).price_cents]
      );
    }
    await recordOrderEvent(client, orderId, "created", { kind: "customer", userId: user.id }, {
      to: "pending",
      data: { totalCents, items: wanted },
    });
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }

  // metadata.orderId is how the webhook below maps a Stripe event back to
  // our own order row — Stripe echoes this metadata back on every event.
  // The idempotency key means a retried call for this order can never
  // create a second, separately payable session.
  let session: Stripe.Checkout.Session;
  try {
    session = await stripe.checkout.sessions.create(
      {
        mode: "payment",
        payment_method_types: ["card"],
        line_items: lineItems,
        metadata: { orderId: String(orderId) },
        customer_email: user.email,
        expires_at: Math.floor(Date.now() / 1000) + CHECKOUT_SESSION_MINUTES * 60,
        success_url: `${env.clientUrl}/account/orders?checkout=success`,
        cancel_url: `${env.clientUrl}/cart?checkout=cancelled`,
      },
      { idempotencyKey: `checkout-order-${orderId}` }
    );
  } catch (err) {
    // Stripe couldn't be reached: don't leave a pending order holding stock
    // with no way to pay for it. (If this cleanup itself fails, or the
    // process dies before getting here, the reservation sweeper cancels the
    // order once reserved_until passes.)
    console.error(`Stripe session creation failed for order ${orderId}:`, err);
    await cancelPendingOrder(orderId, { kind: "system" }, "payment_provider_error").catch(
      (cleanupErr) => console.error(`Could not cancel order ${orderId}:`, cleanupErr)
    );
    throw new HttpError(502, "Could not start payment. Please try again.");
  }

  await inTransaction(async (tx) => {
    await tx.query(`UPDATE orders SET stripe_session_id = $1 WHERE id = $2`, [session.id, orderId]);
    await recordOrderEvent(tx, orderId, "checkout_session_created", { kind: "system" }, {
      data: { sessionId: session.id },
    });
  });

  // Frontend does `window.location.href = data.url` to send the browser to
  // Stripe's hosted payment page.
  res.json({ url: session.url, orderId });
}

// Stripe calls this endpoint directly (not the browser) once a payment
// finishes, so the "was this actually paid?" decision never depends on the
// user's browser successfully redirecting back — someone closing the tab
// right after paying still gets a fulfilled order.
//
// req.body here is the *raw* request buffer, not parsed JSON — see the
// express.raw() middleware wired up for this exact path in app.ts, which
// must run instead of the normal express.json() parser because Stripe's
// signature is computed over the raw bytes.
export async function stripeWebhook(req: Request, res: Response) {
  const signature = req.headers["stripe-signature"];
  if (!signature || typeof signature !== "string") {
    throw new HttpError(400, "Missing Stripe signature");
  }

  // Proves the request really came from Stripe (using STRIPE_WEBHOOK_SECRET)
  // and wasn't forged by a third party hitting this public URL directly.
  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(req.body, signature, env.stripeWebhookSecret);
  } catch (err) {
    throw new HttpError(400, `Webhook signature verification failed: ${(err as Error).message}`);
  }

  // First layer of replay protection: an event id that was already handled
  // is acknowledged and skipped. Two deliveries racing each other can both
  // get past this check, which is fine: every handler below is idempotent on
  // its own (see orderLifecycle.ts), so Stripe retrying an event, or an
  // event being replayed after an admin changed the order, can never move
  // stock or take payment twice.
  const { rowCount: seen } = await pool.query(`SELECT 1 FROM stripe_webhook_events WHERE id = $1`, [
    event.id,
  ]);
  if (seen) {
    return res.json({ received: true, duplicate: true });
  }

  let orderId: number | null = null;
  switch (event.type) {
    // A completed session is normally already paid (card payments). The
    // async_payment_* events only matter for delayed payment methods, but
    // handling them keeps this correct if more methods are enabled later.
    case "checkout.session.completed":
    case "checkout.session.async_payment_succeeded": {
      const session = event.data.object;
      orderId = Number(session.metadata?.orderId) || null;
      if (orderId && session.payment_status === "paid") {
        await markOrderPaid(orderId, paymentIntentId(session), { kind: "stripe" });
      }
      break;
    }
    // The customer never paid: give the reserved stock back right away
    // instead of waiting for the sweeper.
    case "checkout.session.expired":
    case "checkout.session.async_payment_failed": {
      const session = event.data.object;
      orderId = Number(session.metadata?.orderId) || null;
      if (orderId) {
        await cancelPendingOrder(orderId, { kind: "stripe" }, event.type.replace("checkout.session.", ""));
      }
      break;
    }
    // Other event types are ignored.
  }

  // Recorded only after the handler succeeded: if it threw, Stripe gets a
  // 500 and retries, and the retry must be processed.
  await pool.query(
    `INSERT INTO stripe_webhook_events (id, type, order_id)
     VALUES ($1, $2, (SELECT id FROM orders WHERE id = $3))
     ON CONFLICT (id) DO NOTHING`,
    [event.id, event.type, orderId]
  );

  res.json({ received: true });
}
