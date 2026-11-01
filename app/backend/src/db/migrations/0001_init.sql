-- Prices are stored as integer cents (not decimals/floats) everywhere in
-- this schema to avoid floating-point rounding errors in money math.

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL, -- bcrypt hash, never the plaintext password
  role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE products (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE, -- used in product URLs, e.g. /products/wireless-headphones
  description TEXT NOT NULL DEFAULT '',
  price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
  image_url TEXT,
  stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  -- pending: created, waiting on Stripe payment.
  -- paid: Stripe webhook confirmed payment and stock was decremented.
  -- shipped / cancelled: set manually by an admin.
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
  total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
  stripe_session_id TEXT UNIQUE, -- links back to the Stripe Checkout Session for this order
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
  id SERIAL PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES products(id),
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  -- Snapshot of the product's price_cents at purchase time, so a later
  -- price change on the product never rewrites the price of past orders.
  price_cents INTEGER NOT NULL CHECK (price_cents >= 0)
);

CREATE INDEX orders_user_id_idx ON orders(user_id);
CREATE INDEX order_items_order_id_idx ON order_items(order_id);
