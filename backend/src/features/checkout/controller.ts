import { Request, Response } from "express";
import { z } from "zod";
import { env } from "../../config/env";
import { pool } from "../../db/pool";
import { HttpError } from "../../middleware/errorHandler";
import { stripe } from "../../lib/stripe";
import Stripe from "stripe";

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

export async function createCheckoutSession(req: Request, res: Response) {
  const { items } = createSessionSchema.parse(req.body);
  const user = req.user!;

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
        unit_amount: product.price_cents,
        product_data: { name: product.name },
      },
    });
  }

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

  res.json({ url: session.url });
}

export async function stripeWebhook(req: Request, res: Response) {
  const signature = req.headers["stripe-signature"];
  if (!signature || typeof signature !== "string") {
    return res.status(400).send("Missing Stripe signature");
  }

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

  res.json({ received: true });
}

async function fulfillOrder(orderId: number) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
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
