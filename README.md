# E-commerce app

[![CI](https://github.com/kgiannopoulou/fullstack-ecommerce/actions/workflows/ci.yml/badge.svg)](https://github.com/kgiannopoulou/fullstack-ecommerce/actions/workflows/ci.yml)

Next.js storefront and admin panel, Express/TypeScript API, PostgreSQL and Stripe Checkout. The interesting part is the order pipeline: **stock can't be oversold, a payment can't be processed twice, and abandoned or late payments clean up after themselves.** An automated test suite proves each of these against a real Postgres, with requests running concurrently.

## What the tests prove

`backend/test/` holds 62 tests that run against a real database through the real HTTP stack, with a fake Stripe that uses Stripe's own webhook signing:

| Guarantee | Test |
|---|---|
| 12 buyers race for the last unit: exactly one wins, 11 get `OUT_OF_STOCK`, stock ends at 0, Stripe is called once | `checkout-races.test.ts` |
| Concurrent buyers wanting different quantities never oversell | `checkout-races.test.ts` |
| Carts locking the same products in opposite order don't deadlock | `checkout-races.test.ts` |
| A failed Stripe call cancels the order and returns its stock | `checkout-races.test.ts` |
| A replayed webhook (same event id) is acknowledged but not re-processed | `webhooks.test.ts` |
| 8 concurrent deliveries of one event, or the same payment as different events, mark the order paid once | `webhooks.test.ts` |
| An expired-session webhook returns stock exactly once, however often it's replayed, and can't cancel a paid order | `webhooks.test.ts` |
| A late payment re-reserves stock, or refunds **once** (idempotency key) if the stock is gone | `webhooks.test.ts` |
| If the refund call fails, the webhook returns 500, nothing changes, and Stripe's retry is processed | `webhooks.test.ts` |
| The reservation sweeper expires sessions, catches missed payments and is safe to run in parallel | `order-lifecycle.test.ts` |
| Admin moves are restricted, and an admin cancel racing the payment webhook never moves stock twice | `order-lifecycle.test.ts` |
| Single-use, hashed, expiring tokens for email verification and password reset, which also revokes old sessions | `auth.test.ts` |
| Rate limits on auth and checkout; validation errors with field paths; SQL-injection-safe search | `auth.test.ts`, `api.test.ts` |

Some of these were checked by breaking the guard on purpose: removing `AND stock >= $1` or the `paid_at` check makes the race and replay tests fail.

## Features

- **Atomic stock reservation** at checkout, released on expiry, cancellation or Stripe failure
- **Stripe Checkout + webhooks** with signature verification, event de-duplication and idempotent handlers
- **Order audit trail**: every status change and stock movement is recorded with who caused it (customer, Stripe, sweeper, admin), written in the same transaction as the change
- **Accounts**: email verification (required to order), password reset, sessions revoked on reset, role changes applied immediately
- **Rate limiting** on signup/login/reset and on checkout sessions per user
- **Consistent API errors**: `{ error: { code, message, details?, requestId } }` and Zod validation on every body, query and path parameter
- **Catalog** search, price/stock filters, sorting and pagination
- **Admin panel** for products and orders, with filters, pagination and each order's history
- **CI** on every push: type check, tests against Postgres, build, lint and Docker image

Full endpoint reference: [docs/API.md](docs/API.md).

## Quick start

Prerequisites: Node.js 20+, Docker, and a [Stripe](https://dashboard.stripe.com/register) account in test mode (plus the [Stripe CLI](https://docs.stripe.com/stripe-cli) for local webhooks).

```sh
# 1. Postgres (dev + test) and Mailpit for emails
docker compose up -d

# 2. Backend
cd backend
cp .env.example .env      # fill in STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, JWT_SECRET
npm install
npm run migrate
npm run db:seed            # sample catalog + demo accounts
npm run dev                # http://localhost:4000

# 3. Frontend (separate terminal)
cd frontend
cp .env.local.example .env.local
npm install
npm run dev                # http://localhost:3000

# 4. Stripe webhooks (separate terminal)
stripe listen --forward-to localhost:4000/api/webhooks/stripe
# copy the whsec_... it prints into backend/.env as STRIPE_WEBHOOK_SECRET
```

Verification and password-reset emails land in Mailpit at http://localhost:8026.

### Demo accounts

`npm run db:seed` creates two pre-verified accounts:

| Account | Password | |
|---|---|---|
| `admin@demo.test` | `demo-admin-pass` | Admin panel at `/admin` |
| `customer@demo.test` | `demo-customer-pass` | Can check out straight away |

Pay with `4242 4242 4242 4242`, any future expiry and any CVC. "Limited Edition Print" has one unit in stock, so you can try the last-unit race by hand from two browsers.

### Tests

```sh
cd backend
npm test        # needs the postgres-test container from docker compose (port 5437)
```

The test database is rebuilt from the real migrations on every run. Set `TEST_DATABASE_URL` to use a different one.

## Orders, stock and payments

All order/stock transitions live in `backend/src/features/checkout/orderLifecycle.ts`:

- **Stock is reserved at checkout**, not when payment arrives. Creating the checkout session decrements stock atomically (`... WHERE stock >= qty`) in the same transaction as the order, so two customers can't both pay for the last unit. The second gets a "not enough stock" error before reaching Stripe. Rows are locked in product-id order, so overlapping carts can't deadlock.
- **Quantities are merged per product** before validation, so the same product on several cart lines can't exceed stock.
- **Unpaid reservations are released**: Stripe sessions expire after 30 minutes. The `checkout.session.expired` webhook and a once-a-minute sweeper cancel the pending order and return its stock. The sweeper also cleans up orders whose Stripe session was never created, and marks orders paid if the payment webhook was missed.
- **Stripe failures don't leave orphans**: if creating the session fails, the order is cancelled and its stock returned immediately (502 to the client).
- **Idempotent stock movements**: each order has a `stock_reserved` flag that every reserve/release checks and flips in the same transaction, and `paid_at` marks a payment as processed. Webhook retries/replays, admin edits and the sweeper can't move stock twice. On top of that, processed Stripe event ids are stored and duplicates are acknowledged without being processed.
- **Restricted admin status changes**: `pending → cancelled`, `paid → shipped | cancelled`. Orders never go back to `pending`, and `paid` is only set by a confirmed Stripe payment. Cancelling returns stock (refund paid orders from the Stripe dashboard).
- If a payment arrives after its reservation was released and the stock is gone, the customer is **refunded automatically** and the order cancelled.
- **Every change is audited** in `order_events`, written in the same transaction, so the history can't disagree with the order. Customers see their order's timeline; admins also see who did each step.

## Accounts and sessions

- The session JWT (httpOnly, `SameSite=Lax` cookie) carries only the user id and a `session_version`. Role and verification status are loaded from the database on every request, so promoting a user to admin takes effect immediately and a password reset logs out every other session.
- Verification and reset links use random 256-bit tokens. Only their SHA-256 hash is stored, they are single-use (atomic `UPDATE … WHERE used_at IS NULL`) and they expire (24 h / 30 min).
- "Forgot password" answers identically whether or not the account exists, and login gives the same error for an unknown email and a wrong password.

To make yourself an admin without the seed, sign up and run:

```sql
UPDATE users SET role = 'admin' WHERE email = 'you@example.com';
```

## Deploying a demo

`render.yaml` deploys Postgres, the API (Docker) and the storefront to Render's free tier, with Stripe in test mode. See [docs/DEPLOY.md](docs/DEPLOY.md) for the steps.

## Project layout

- `backend/`: Express API with raw `pg` and hand-written SQL migrations (`backend/src/db/migrations`). `src/app.ts` builds the app (used by the tests), and `src/index.ts` starts it.
- `backend/test/`: Vitest + supertest suite against Postgres
- `frontend/`: Next.js App Router storefront and admin panel
- `docs/`: API reference and deployment guide
- `docker-compose.yml`: local Postgres, test Postgres and Mailpit
