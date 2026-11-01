-- Email verification, password reset, session revocation, an order audit
-- trail and webhook event de-duplication.

-- NULL until the user clicks the link in their verification email. Accounts
-- that existed before this migration are treated as verified so nobody is
-- locked out of checkout.
ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMPTZ;
UPDATE users SET email_verified_at = created_at;

-- Copied into every session JWT. Bumping it (on password reset) makes every
-- previously issued session token invalid.
ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 1;

-- Single-use tokens sent by email. Only a SHA-256 hash of the token is
-- stored, so a database leak doesn't hand out working reset links.
CREATE TABLE auth_tokens (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL CHECK (purpose IN ('verify_email', 'reset_password')),
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX auth_tokens_user_purpose_idx ON auth_tokens(user_id, purpose);

-- Append-only history of everything that happened to an order: who did it
-- (the customer, Stripe, the sweeper, an admin) and what changed. Rows are
-- written in the same transaction as the change they describe, so the
-- history can't disagree with the order row.
CREATE TABLE order_events (
  id BIGSERIAL PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT,
  actor TEXT NOT NULL CHECK (actor IN ('customer', 'stripe', 'system', 'admin')),
  actor_user_id INTEGER REFERENCES users(id),
  data JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX order_events_order_id_idx ON order_events(order_id, id);

-- Stripe event ids that have been fully handled. A replayed delivery of the
-- same event is acknowledged without being processed again. (The order
-- lifecycle is idempotent on its own; this is a second layer and a record of
-- what was received.)
CREATE TABLE stripe_webhook_events (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Catalog filtering/sorting.
CREATE INDEX products_price_idx ON products(price_cents);
CREATE INDEX products_created_at_idx ON products(created_at DESC, id DESC);

-- Login and signup look emails up case-insensitively.
CREATE INDEX users_email_lower_idx ON users (lower(email));
