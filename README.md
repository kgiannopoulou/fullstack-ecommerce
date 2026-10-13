# E-commerce app

Next.js frontend + Express/TypeScript backend + PostgreSQL, with Stripe Checkout for payments.

## Prerequisites

- [Node.js](https://nodejs.org/) 
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 
- A [Stripe](https://dashboard.stripe.com/register) 
- Optional, for local webhook testing: the [Stripe CLI](https://docs.stripe.com/stripe-cli)

## First-time setup

```sh
# 1. Start Postgres
docker compose up -d

# 2. Backend
cd backend
cp .env.example .env      # then fill in STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, JWT_SECRET
npm install
npm run migrate
npm run db:seed            # optional: adds a few sample products
npm run dev                 # http://localhost:4000

# 3. Frontend (separate terminal)
cd frontend
cp .env.local.example .env.local
npm install
npm run dev                 # http://localhost:3000
```

## Stripe webhook (local dev)

Checkout only marks an order "paid" once Stripe's webhook fires. Locally, forward events with the Stripe CLI:

```sh
stripe listen --forward-to localhost:4000/api/webhooks/stripe
```

Copy the `whsec_...` value it prints into `backend/.env` as `STRIPE_WEBHOOK_SECRET`.

## Orders, stock and payments

All order/stock transitions live in `backend/src/features/checkout/orderLifecycle.ts`:

- **Stock is reserved at checkout**, not when payment arrives. Creating the
  checkout session decrements stock atomically (`... WHERE stock >= qty`) in
  the same transaction as the order, so two customers can't both pay for the
  last unit — the second gets a "not enough stock" error before reaching Stripe.
- **Quantities are merged per product** before validation, so the same product
  on several cart lines can't exceed stock.
- **Unpaid reservations are released**: Stripe sessions expire after 30 minutes;
  the `checkout.session.expired` webhook and a once-a-minute sweeper cancel the
  pending order and return its stock. The sweeper also cleans up orders whose
  Stripe session was never created, and marks orders paid if the payment
  webhook was missed.
- **Stripe failures don't leave orphans**: if creating the session fails, the
  order is cancelled and its stock returned immediately (502 to the client).
- **Idempotent stock movements**: each order has a `stock_reserved` flag that
  every reserve/release checks and flips in the same transaction, and `paid_at`
  marks a payment as processed. Webhook retries/replays, admin edits and the
  sweeper can't move stock twice.
- **Restricted admin status changes**: `pending → cancelled`,
  `paid → shipped | cancelled`. Orders never go back to `pending` and `paid` is
  only set by a confirmed Stripe payment. Cancelling returns stock (refund paid
  orders from the Stripe dashboard).
- If a payment arrives after its reservation was released and the stock is
  gone, the customer is refunded automatically and the order cancelled.

Run `npm run migrate` after pulling to apply `0002_stock_reservation.sql`.

## Becoming an admin

Sign up normally, then promote your account directly in Postgres:

```sql
UPDATE users SET role = 'admin' WHERE email = 'you@example.com';
```

The `/admin` panel (product + order management) becomes available once the role is set. Your session's role is baked into the JWT issued at login, so a page refresh alone won't pick up the change — **log out and log back in** after updating the role in the database.

## Project layout

- `backend/` — Express API, raw `pg` + hand-written SQL migrations (`backend/src/db/migrations`)
- `frontend/` — Next.js App Router UI
- `docker-compose.yml` — local Postgres

## Testing the full flow

1. Browse products on `/`, add to cart.
2. Go to `/cart`, click Checkout — redirects to `/login` if not signed in.
3. Sign up, then checkout again — redirected to Stripe's hosted Checkout.
4. Pay with the test card `4242 4242 4242 4242`, any future expiry, any CVC.
5. Redirected back — order appears as "paid" in `/account/orders` (requires the webhook to be running, see above).
6. As an admin, manage products/orders at `/admin`.
