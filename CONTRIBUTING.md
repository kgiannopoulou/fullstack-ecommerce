# Contributing

Thanks for taking a look. This is a personal portfolio project, but issues and
pull requests are welcome.

## Setup

Node.js 20+ and Docker. Full instructions (Stripe test keys, webhooks, demo
accounts) are in the [README quick start](README.md#quick-start).

```sh
docker compose up -d                 # Postgres (dev + test) and Mailpit
cd backend && npm install && npm run migrate && npm run db:seed && npm run dev
cd frontend && npm install && npm run dev
```

## Checks

```sh
cd backend
npm run typecheck
npm test            # 62 tests against the postgres-test container (port 5437)
npm run build

cd ../frontend
npm run lint
npm run build
```

CI runs all of these plus a Docker build of the API on every push and pull request.

## Rules of the order pipeline

All order and stock transitions go through `backend/src/features/checkout/orderLifecycle.ts`.
If you touch it:

* Stock moves only inside a transaction that also checks and flips `stock_reserved`.
* Every transition writes an `order_events` row in the same transaction.
* Add a test that runs the new path **concurrently** and with **replayed** webhooks — the
  existing race and replay tests are the template.
* Schema changes are a new numbered file in `backend/src/db/migrations/`; never edit an applied one.

## Workflow

* Branch from `main` (`feat/…`, `fix/…`, `test/…`, `docs/…`).
* Conventional Commits: `feat: add coupon codes`, `fix: release stock when Stripe session creation times out`.
* Open a pull request with what changed, why and how you tested it.
