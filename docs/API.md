# API reference

Base URL: `http://localhost:4000` in development. All bodies are JSON. Authentication is an httpOnly `token` cookie set by signup, login and password reset; send requests with `credentials: "include"`.

## Error format

Every error response has the same shape:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Invalid request",
    "details": [{ "path": "items.0.quantity", "message": "Number must be less than or equal to 99" }],
    "requestId": "5b0c6e0a-6c1f-4a3e-9f0e-2a2f1d1f6f4b"
  }
}
```

- `code` is stable and machine-readable. Clients branch on it, never on `message`.
- `message` is safe to show to a user.
- `details` is only present for `VALIDATION_FAILED`, with one entry per invalid field.
- `requestId` matches the `X-Request-Id` response header and the server log line for the request. An incoming `X-Request-Id` is reused.

| Code | Status | When |
|---|---|---|
| `VALIDATION_FAILED` | 400 | Body, query or path parameter failed its schema |
| `INVALID_JSON` | 400 | Body isn't valid JSON |
| `INVALID_TOKEN` | 400 | Verification/reset token unknown, used or expired |
| `UNAUTHENTICATED` | 401 | No session, or it expired or was revoked |
| `INVALID_CREDENTIALS` | 401 | Wrong email or password (same answer for both) |
| `FORBIDDEN` | 403 | Signed in but not allowed (e.g. not an admin) |
| `EMAIL_NOT_VERIFIED` | 403 | Checkout before verifying the email address |
| `NOT_FOUND` | 404 | Unknown resource or route |
| `CONFLICT` | 409 | Unique/foreign-key conflict (duplicate slug, product in use) |
| `EMAIL_TAKEN` | 409 | Signup with an existing email |
| `OUT_OF_STOCK` | 409 | Not enough stock to reserve the cart |
| `INVALID_TRANSITION` | 409 | Admin status change not allowed from the current status |
| `RATE_LIMITED` | 429 | Too many requests; see the `RateLimit` / `RateLimit-Policy` headers |
| `PAYMENT_PROVIDER_ERROR` | 502 | Stripe couldn't be reached; the order was cancelled and its stock returned |
| `INTERNAL` | 500 | Unexpected; details are only in the server log |

## Rate limits

| Scope | Default | Key |
|---|---|---|
| Signup, login, email verification, password forgot/reset | 20 requests / 15 min | client IP |
| `POST /api/checkout/create-session` | 10 requests / min | user |

## Auth

| Method & path | Auth | Body | Response |
|---|---|---|---|
| `POST /api/auth/signup` | – | `{ email, password }` (8–72 chars) | `201 { user }`, sets cookie, sends verification email |
| `POST /api/auth/login` | – | `{ email, password }` | `200 { user }`, sets cookie |
| `POST /api/auth/logout` | – | – | `204`, clears cookie |
| `GET /api/auth/me` | optional | – | `{ user }` or `{ user: null }` |
| `POST /api/auth/verify-email` | – | `{ token }` | `{ verified: true }` |
| `POST /api/auth/verify-email/resend` | user | – | `202 { sent }` |
| `POST /api/auth/password/forgot` | – | `{ email }` | always `202` with the same body |
| `POST /api/auth/password/reset` | – | `{ token, password }` | `{ user }`, sets a new cookie, revokes all other sessions |

`user` is `{ id, email, role: "user" | "admin", emailVerified }`. Emails are matched case-insensitively. Tokens are single-use, only their SHA-256 hash is stored, and they expire after 24 h (verification) or 30 min (reset). Requesting a new one invalidates the previous one.

The session cookie carries only the user id and a `session_version`. Role and verification status are read from the database on every request, so a role change applies immediately and a password reset logs out every other session.

## Products

`GET /api/products` (public)

| Query | Type | Default | Notes |
|---|---|---|---|
| `q` | string | – | Case-insensitive match on name or description |
| `minPrice`, `maxPrice` | integer cents | – | `minPrice` ≤ `maxPrice` |
| `inStock` | `true` \| `false` | – | Only in-stock / only sold-out |
| `sort` | `newest` \| `price_asc` \| `price_desc` \| `name` | `newest` | |
| `page` | integer ≥ 1 | 1 | |
| `pageSize` | 1–50 | 12 | |

```json
{
  "products": [{ "id": 1, "name": "Ceramic Coffee Mug", "slug": "ceramic-coffee-mug", "description": "…", "price_cents": 1499, "image_url": "…", "stock": 100 }],
  "pagination": { "page": 1, "pageSize": 12, "total": 16, "totalPages": 2 }
}
```

`GET /api/products/:slug` returns `{ product }`, or `404`.

## Checkout

`POST /api/checkout/create-session` (user with a verified email)

```json
{ "items": [{ "productId": 1, "quantity": 2 }] }
```

Up to 50 lines, quantity 1–99 per product after merging repeated lines. Prices come from the database, never from the client. On success the stock is reserved and the response is `{ url, orderId }`: redirect the browser to `url` (Stripe Checkout). Errors: `OUT_OF_STOCK` (nothing was reserved), `PAYMENT_PROVIDER_ERROR` (the order was cancelled and its stock returned).

`POST /api/webhooks/stripe` is called by Stripe only. It needs a valid `Stripe-Signature`. Event ids are de-duplicated, and every handler is idempotent anyway. Handled events: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired` and `checkout.session.async_payment_failed`.

## Orders

| Method & path | Auth | Response |
|---|---|---|
| `GET /api/orders` | user | `{ orders: [{ id, status, total_cents, created_at, items: [...] }] }`, own orders only |
| `GET /api/orders/:id` | user | `{ order, history }`; another user's order is `404` |

`history` is the order's audit trail, oldest first: `[{ type, from_status, to_status, created_at }]`.

## Admin

Every route needs an admin session.

| Method & path | Body / query | Response |
|---|---|---|
| `GET /api/admin/products` | – | `{ products }` |
| `GET /api/admin/products/:id` | – | `{ product }` |
| `POST /api/admin/products` | `{ name, slug, description?, price_cents, image_url?, stock }` | `201 { product }` |
| `PUT /api/admin/products/:id` | same | `{ product }` |
| `DELETE /api/admin/products/:id` | – | `204`; `409 CONFLICT` if orders reference it |
| `GET /api/admin/orders` | `?status=&page=&pageSize=` (≤100) | `{ orders: [{ …, user_email, next_statuses }], pagination }` |
| `PATCH /api/admin/orders/:id` | `{ status }` | `{ order }`; `409 INVALID_TRANSITION` outside the allowed moves |
| `GET /api/admin/orders/:id/history` | – | `{ history: [{ type, from_status, to_status, actor, actor_email, data, created_at }] }` |

Allowed admin moves: `pending → cancelled` and `paid → shipped | cancelled`. `paid` is only ever set by a confirmed Stripe payment.

### Order event types

| Type | Actor | Meaning |
|---|---|---|
| `created` | customer | Order placed and stock reserved |
| `checkout_session_created` | system | Stripe session opened |
| `paid` | stripe / system | Payment confirmed (`system` when the sweeper found a missed webhook) |
| `stock_reacquired` | stripe / system | Late payment re-reserved stock that had been released |
| `stock_released` | any | Reserved stock returned to the shelf |
| `refunded` | stripe / system | Paid after the stock was gone, so it was refunded automatically and cancelled |
| `cancelled` | stripe / system / admin | Cancelled; `data.reason` says why (`expired`, `reservation_expired`, `payment_provider_error`, `admin`…) |
| `shipped` | admin | Marked shipped |
