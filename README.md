# E-commerce app

Next.js frontend + Express/TypeScript backend + PostgreSQL, with Stripe Checkout for payments.

## Prerequisites

- [Node.js](https://nodejs.org/) 20+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — runs Postgres locally via `docker-compose.yml`
- A [Stripe](https://dashboard.stripe.com/register) account (free) for test-mode API keys
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
