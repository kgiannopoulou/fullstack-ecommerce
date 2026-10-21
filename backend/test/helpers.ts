import bcrypt from "bcryptjs";
import type { Server } from "node:http";
import request from "supertest";
import { afterAll } from "vitest";
import { createApp } from "../src/app";
import { pool } from "../src/db/pool";
import { COOKIE_NAME, signSessionToken } from "../src/middleware/auth";
import type { RateLimitOptions } from "../src/middleware/rateLimit";
import { fakeStripe } from "./fakes";
import { WEBHOOK_SECRET } from "./env";

export async function resetDb() {
  await pool.query(
    `TRUNCATE users, products, orders, order_items, order_events, auth_tokens, stripe_webhook_events
     RESTART IDENTITY CASCADE`
  );
}

// Limits high enough that only the rate-limit tests ever hit them.
const RELAXED: RateLimitOptions = {
  auth: { windowMs: 60_000, limit: 10_000 },
  checkout: { windowMs: 60_000, limit: 10_000 },
};

// A real listening server (not supertest's per-request one), so concurrent
// requests in the race tests really run in parallel against one app.
export function startServer(rateLimits: RateLimitOptions = RELAXED) {
  const server: Server = createApp({ rateLimits }).listen(0);
  afterAll(() => new Promise<void>((resolve) => server.close(() => resolve())));
  return () => request(server);
}

export const PASSWORD = "correct-horse-battery";
const PASSWORD_HASH = bcrypt.hashSync(PASSWORD, 4);

export async function createUser(
  email = `user${Math.random().toString(36).slice(2, 8)}@test.dev`,
  { role = "user", verified = true }: { role?: "user" | "admin"; verified?: boolean } = {}
) {
  const { rows } = await pool.query(
    `INSERT INTO users (email, password_hash, role, email_verified_at)
     VALUES ($1, $2, $3, ${verified ? "now()" : "NULL"}) RETURNING id, session_version`,
    [email, PASSWORD_HASH, role]
  );
  const { id, session_version } = rows[0];
  return { id: id as number, email, cookie: `${COOKIE_NAME}=${signSessionToken(id, session_version)}` };
}

export async function createProduct({ stock = 10, priceCents = 1000, name }: { stock?: number; priceCents?: number; name?: string } = {}) {
  const n = name ?? `Product ${Math.random().toString(36).slice(2, 8)}`;
  const { rows } = await pool.query(
    `INSERT INTO products (name, slug, price_cents, stock) VALUES ($1, $2, $3, $4) RETURNING id`,
    [n, n.toLowerCase().replace(/[^a-z0-9]+/g, "-"), priceCents, stock]
  );
  return rows[0].id as number;
}

export async function stockOf(productId: number) {
  const { rows } = await pool.query(`SELECT stock FROM products WHERE id = $1`, [productId]);
  return rows[0].stock as number;
}

export async function getOrder(orderId: number) {
  const { rows } = await pool.query(`SELECT * FROM orders WHERE id = $1`, [orderId]);
  return rows[0];
}

export async function eventTypes(orderId: number) {
  const { rows } = await pool.query(`SELECT type FROM order_events WHERE order_id = $1 ORDER BY id`, [orderId]);
  return rows.map((r) => r.type as string);
}

let eventCounter = 0;

// A Stripe event for a checkout session, the way Stripe would send it.
export function sessionEvent(
  type: string,
  session: { id: string; metadata: Record<string, string>; payment_status?: string; payment_intent?: string | null },
  id = `evt_test_${++eventCounter}_${Date.now()}`
) {
  return {
    id,
    object: "event",
    type,
    data: { object: { object: "checkout.session", payment_status: "unpaid", payment_intent: null, ...session } },
  };
}

// POSTs an event to the webhook with a valid Stripe signature.
export function sendWebhook(api: () => request.Agent | ReturnType<typeof request>, event: object, secret = WEBHOOK_SECRET) {
  const payload = JSON.stringify(event);
  const signature = fakeStripe.webhooks.generateTestHeaderString({ payload, secret });
  return (api() as ReturnType<typeof request>)
    .post("/api/webhooks/stripe")
    .set("Content-Type", "application/json")
    .set("Stripe-Signature", signature)
    .send(payload);
}
