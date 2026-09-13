import { Request, Response } from "express";
import { z } from "zod";
import { env } from "../../config/env";
import { pool } from "../../db/pool";
import { HttpError } from "../../middleware/errorHandler";
import { stripe } from "../../lib/stripe";
import Stripe from "stripe";

// The client only ever sends { productId, quantity } pairs — never a price.
// Prices are always looked up server-side from the database below, so a
// tampered client request can't check out at an arbitrary price.
const createSessionSchema = z.object({
  items: z
    .array(
      z.object({
        productId: z.number().int().positive(),
        quantity: z.number().int().positive().max(99),
      })
    )
    .min(1),
});

// Called when a signed-in user clicks "Checkout". Validates the cart against
// the database, records a 'pending' order, then hands off to Stripe's
// hosted Checkout page. The order is only marked 'paid' later, by the
// stripeWebhook handler below, once Stripe confirms payment actually
// succeeded — never directly from this request.
export async function createCheckoutSession(req: Request, res: Response) {
  const { items } = createSessionSchema.parse(req.body);
  const user = req.user!; // guaranteed present: this route is behind requireAuth

  const productIds = items.map((item) => item.productId);
  const { rows: products } = await pool.query(
    `SELECT id, name, price_cents, stock FROM products WHERE id = ANY($1::int[])`,
    [productIds]
  );
  const productById = new Map(products.map((p) => [p.id, p]));

  let totalCents = 0;
  const lineItems: Stripe.Checkout.SessionCreateParams.LineItem[] = [];
  const orderItemRows: { productId: number; quantity: number; priceCents: number }[] = [];

  for (const item of items) {
    const product = productById.get(item.productId);
    if (!product) {
      throw new HttpError(400, `Product ${item.productId} not found`);
    }
    if (product.stock < item.quantity) {
      throw new HttpError(400, `Not enough stock for ${product.name}`);
    }

    totalCents += product.price_cents * item.quantity;
    orderItemRows.push({
      productId: product.id,
      quantity: item.quantity,
      priceCents: product.price_cents,
    });
    lineItems.push({
      quantity: item.quantity,
      price_data: {
        currency: "usd",
        unit_amount: product.price_cents, // Stripe also expects integer cents
        product_data: { name: product.name },
      },
    });
  }

  // Order + order_items are written in one transaction so we never end up
  // with an order that has no line items (or vice versa) if something
  // fails partway through.
  const client = await pool.connect();
  let orderId: number;
  try {
    await client.query("BEGIN");
    const { rows } = await client.query(
      `INSERT INTO orders (user_id, status, total_cents) VALUES ($1, 'pending', $2) RETURNING id`,
      [user.id, totalCents]
    );
    orderId = rows[0].id;

    for (const row of orderItemRows) {
      await client.query(
        `INSERT INTO order_items (order_id, product_id, quantity, price_cents) VALUES ($1, $2, $3, $4)`,
        [orderId, row.productId, row.quantity, row.priceCents]
      );
    }
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }

  // metadata.orderId is how the webhook below maps a Stripe event back to
  // our own order row — Stripe echoes this metadata back on every event.
  const session = await stripe.checkout.sessions.create({
    mode: "payment",
    payment_method_types: ["card"],
    line_items: lineItems,
    metadata: { orderId: String(orderId) },
    success_url: `${env.clientUrl}/account/orders?checkout=success`,
    cancel_url: `${env.clientUrl}/cart?checkout=cancelled`,
  });

  await pool.query(`UPDATE orders SET stripe_session_id = $1 WHERE id = $2`, [
    session.id,
    orderId,
  ]);

  // Frontend does `window.location.href = data.url` to send the browser to
  // Stripe's hosted payment page.
  res.json({ url: session.url });
}

// Stripe calls this endpoint directly (not the browser) once a payment
// finishes, so the "was this actually paid?" decision never depends on the
// user's browser successfully redirecting back — someone closing the tab
// right after paying still gets a fulfilled order.
//
// req.body here is the *raw* request buffer, not parsed JSON — see the
// express.raw() middleware wired up for this exact path in index.ts, which
// must run instead of the normal express.json() parser because Stripe's
// signature is computed over the raw bytes.
export async function stripeWebhook(req: Request, res: Response) {
  const signature = req.headers["stripe-signature"];
  if (!signature || typeof signature !== "string") {
    return res.status(400).send("Missing Stripe signature");
  }

  // Proves the request really came from Stripe (using STRIPE_WEBHOOK_SECRET)
  // and wasn't forged by a third party hitting this public URL directly.
  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(req.body, signature, env.stripeWebhookSecret);
  } catch (err) {
    return res.status(400).send(`Webhook signature verification failed: ${(err as Error).message}`);
  }

  if (event.type === "checkout.session.completed") {
    const session = event.data.object as Stripe.Checkout.Session;
    const orderId = Number(session.metadata?.orderId);
    if (orderId) {
      await fulfillOrder(orderId);
    }
  }
  // Other event types (e.g. failed payments) are ignored — this app only
  // needs to react to a completed checkout.

  res.json({ received: true });
}

// Marks the order paid and decrements stock for what was bought.
async function fulfillOrder(orderId: number) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    // The `AND status = 'pending'` guard makes this idempotent: if Stripe
    // ever retries the same webhook event (it does, on a slow/failed
    // response), the second call updates zero rows and stock is not
    // double-decremented.
    const { rows } = await client.query(
      `UPDATE orders SET status = 'paid' WHERE id = $1 AND status = 'pending' RETURNING id`,
      [orderId]
    );
    if (rows.length > 0) {
      const { rows: items } = await client.query(
        `SELECT product_id, quantity FROM order_items WHERE order_id = $1`,
        [orderId]
      );
      for (const item of items) {
        await client.query(`UPDATE products SET stock = stock - $1 WHERE id = $2`, [
          item.quantity,
          item.product_id,
        ]);
      }
    }
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}
