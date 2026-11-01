-- Stock is now reserved (decremented) when the checkout session is created,
-- not when payment succeeds, so two customers can no longer both pay for the
-- last unit. These columns track that reservation per order.

-- TRUE while this order is holding stock (i.e. the products' stock column
-- has been decremented for its items and not yet given back). Every stock
-- movement checks-and-flips this flag in the same transaction, which is what
-- makes reserve/release idempotent no matter how the order's status is
-- changed afterwards (webhook retries, admin edits, the expiry sweeper...).
ALTER TABLE orders ADD COLUMN stock_reserved BOOLEAN NOT NULL DEFAULT FALSE;

-- When a still-pending order's reservation lapses. The sweeper
-- (features/checkout/reservations.ts) cancels pending orders past this time
-- and returns their stock.
ALTER TABLE orders ADD COLUMN reserved_until TIMESTAMPTZ;

ALTER TABLE orders ADD COLUMN paid_at TIMESTAMPTZ;

-- Paid / shipped orders created before this migration already had their
-- stock decremented by the old webhook, so they count as holding stock.
-- Old pending orders never reserved anything; the sweeper will cancel them.
UPDATE orders SET stock_reserved = TRUE WHERE status IN ('paid', 'shipped');
UPDATE orders SET reserved_until = now() WHERE status = 'pending';

CREATE INDEX orders_pending_reserved_until_idx ON orders(reserved_until) WHERE status = 'pending';
