# Deploying a test-mode demo (Render)

`render.yaml` describes the whole demo: a free Postgres, the API (Docker) and the storefront (Node). Stripe stays in **test mode**, so no real payments are possible.

## 1. Create the services

1. Push the repo to GitHub. In Render go to **New → Blueprint** and pick the repository. Render reads `render.yaml` and proposes `shop-db`, `shop-api` and `shop-web`.
2. Render asks for the values marked `sync: false`. Leave them empty on this first pass, because you don't know the service URLs yet. Create the services.
3. Note the two URLs Render assigns, e.g. `https://shop-api-ab12.onrender.com` and `https://shop-web-cd34.onrender.com`.

## 2. Stripe (test mode)

1. In the Stripe dashboard, switch on **Test mode** and copy the secret key (`sk_test_…`).
2. **Developers → Webhooks → Add endpoint**:
   - URL: `https://shop-api-ab12.onrender.com/api/webhooks/stripe` (the API directly, not the storefront)
   - Events: `checkout.session.completed`, `checkout.session.expired`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`
3. Copy the endpoint's signing secret (`whsec_…`).

## 3. Fill in the environment

**shop-api**

| Key | Value |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_test_…` |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` |
| `CLIENT_URL` | `https://shop-web-cd34.onrender.com` |
| `CORS_ORIGIN` | `https://shop-web-cd34.onrender.com` |
| `SMTP_URL` | optional, see below |

**shop-web**

| Key | Value |
|---|---|
| `API_PROXY_TARGET` | `https://shop-api-ab12.onrender.com` |
| `API_INTERNAL_URL` | `https://shop-api-ab12.onrender.com` |

Redeploy both services. `API_PROXY_TARGET` is read at **build** time (Next.js bakes rewrites into the build), so the storefront needs a fresh build, not just a restart.

## 4. Try it

The API runs migrations on every start, and with `SEED_DEMO=true` it seeds the catalog and two pre-verified accounts:

| Account | Password |
|---|---|
| `admin@demo.test` | `demo-admin-pass` |
| `customer@demo.test` | `demo-customer-pass` |

Pay with `4242 4242 4242 4242`, any future expiry date and any CVC. "Limited Edition Print" has exactly one unit in stock, so you can open two browsers and watch the second checkout get `Not enough stock`.

## Why the storefront proxies `/api`

Render gives each service its own `onrender.com` subdomain. `onrender.com` is on the Public Suffix List, so browsers treat the two services as different *sites*, and a `SameSite=Lax` session cookie set by the API wouldn't be sent on the storefront's fetches. With `API_PROXY_TARGET` set, the browser calls `/api/*` on the storefront's own origin, Next.js forwards the request to the API (`frontend/next.config.ts`), and the cookie stays first-party. That's also why `TRUST_PROXY=2` is set on the API: requests pass through Render's load balancer and the Next.js proxy, and the rate limiter needs the real client IP.

## Email

Without `SMTP_URL`, verification and reset emails are only printed to the API log (Render → shop-api → Logs). New sign-ups can still find their link there, and the demo accounts are already verified. For real delivery, use any SMTP provider's credentials, e.g. `smtp://USER:PASS@smtp.example.com:587`.

## Free-tier caveats

Free web services sleep after inactivity and take ~30 s to wake. The free Postgres expires after 30 days. Recreate it from the Blueprint, and the API re-migrates and re-seeds on its next start.
