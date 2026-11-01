-- =============================================================================
-- 00_schema.sql — warehouse layout
--
--   raw.*      the legacy export exactly as received: every column is TEXT,
--              nothing is trusted, nothing is fixed. Loaded by load_raw.py.
--   clean.*    typed, de-duplicated, standardised data produced by clean.py,
--              plus a log of every data-quality decision.
--   reporting.* views for Excel / Power BI (created by 11_reporting_views.sql).
-- =============================================================================

DROP SCHEMA IF EXISTS reporting CASCADE;
DROP SCHEMA IF EXISTS clean CASCADE;
DROP SCHEMA IF EXISTS raw CASCADE;
CREATE SCHEMA raw;
CREATE SCHEMA clean;
CREATE SCHEMA reporting;

-- ---------------------------------------------------------------- raw layer --
CREATE TABLE raw.products (
    product_id TEXT, sku TEXT, product_name TEXT, category TEXT,
    list_price TEXT, unit_cost TEXT, launch_date TEXT, supplier_lead_time_days TEXT,
    parcel_size TEXT
);

CREATE TABLE raw.customers (
    customer_id TEXT, signup_date TEXT, country TEXT, acquisition_channel TEXT
);

-- One row per order line ("transaction record"); order attributes repeat.
CREATE TABLE raw.transactions (
    transaction_id TEXT, order_id TEXT, order_date TEXT, customer_id TEXT,
    customer_country TEXT, product_id TEXT, sku TEXT, product_name TEXT,
    category TEXT, quantity TEXT, unit_price TEXT, discount_pct TEXT,
    payment_method TEXT, order_status TEXT, refund_amount TEXT, channel TEXT,
    courier TEXT, ship_date TEXT, delivery_date TEXT, shipping_cost TEXT
);

CREATE TABLE raw.inventory (
    snapshot_date TEXT, product_id TEXT, stock_on_hand TEXT,
    units_received TEXT, units_sold TEXT
);

-- -------------------------------------------------------------- clean layer --
CREATE TABLE clean.products (
    product_id      INTEGER PRIMARY KEY,
    sku             TEXT NOT NULL UNIQUE,
    product_name    TEXT NOT NULL,
    category        TEXT NOT NULL,
    list_price      NUMERIC(10,2) NOT NULL CHECK (list_price > 0),
    unit_cost       NUMERIC(10,2) NOT NULL CHECK (unit_cost >= 0),
    launch_date     DATE NOT NULL,
    supplier_lead_time_days INTEGER NOT NULL,
    parcel_size     TEXT NOT NULL CHECK (parcel_size IN ('S', 'M', 'L'))
);

CREATE TABLE clean.customers (
    customer_id         INTEGER PRIMARY KEY,
    signup_date         DATE NOT NULL,
    country             TEXT NOT NULL,
    acquisition_channel TEXT NOT NULL
);

CREATE TABLE clean.orders (
    order_id        INTEGER PRIMARY KEY,
    customer_id     INTEGER REFERENCES clean.customers(customer_id),  -- NULL = guest checkout
    is_guest        BOOLEAN NOT NULL,
    order_ts        TIMESTAMP NOT NULL,
    order_date      DATE NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('completed', 'refunded', 'cancelled')),
    payment_method  TEXT NOT NULL,              -- 'Unknown' when the source lost it
    discount_pct    NUMERIC(4,2) NOT NULL,
    channel         TEXT NOT NULL,
    country         TEXT NOT NULL,
    courier         TEXT,
    ship_date       DATE,
    delivery_date   DATE,
    refund_amount   NUMERIC(12,2) NOT NULL DEFAULT 0,
    shipping_cost   NUMERIC(8,2) NOT NULL DEFAULT 0,   -- carrier cost paid by the shop (0 if never shipped)
    shipping_cost_imputed BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE clean.order_items (
    transaction_id  TEXT PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES clean.orders(order_id),
    product_id      INTEGER NOT NULL REFERENCES clean.products(product_id),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(10,2) NOT NULL CHECK (unit_price > 0),
    unit_cost       NUMERIC(10,2) NOT NULL,
    gross_amount    NUMERIC(12,2) NOT NULL,     -- quantity * unit_price
    discount_amount NUMERIC(12,2) NOT NULL,
    net_amount      NUMERIC(12,2) NOT NULL,     -- gross - discount (before refunds)
    is_bulk         BOOLEAN NOT NULL            -- quantity outlier, kept but flagged
);

CREATE TABLE clean.inventory_daily (
    snapshot_date   DATE NOT NULL,
    product_id      INTEGER NOT NULL REFERENCES clean.products(product_id),
    stock_on_hand   INTEGER NOT NULL CHECK (stock_on_hand >= 0),
    units_received  INTEGER NOT NULL,
    units_sold      INTEGER NOT NULL,
    stock_corrected BOOLEAN NOT NULL,           -- negative count set to 0
    PRIMARY KEY (product_id, snapshot_date)
);

CREATE TABLE clean.data_quality_log (
    check_id    INTEGER PRIMARY KEY,
    check_name  TEXT NOT NULL,
    table_name  TEXT NOT NULL,
    records     INTEGER NOT NULL,
    action      TEXT NOT NULL,
    rationale   TEXT NOT NULL
);

-- ---------------------------------------------------- analysis base views --
-- Relative carrier space per unit, from the courier's per-unit tariff
-- (S 0.25, M 0.70, L 2.10 EUR): used to allocate an order's shipping cost.
CREATE VIEW clean.parcel_weights AS
SELECT product_id,
       CASE parcel_size WHEN 'S' THEN 1.0 WHEN 'M' THEN 2.8 ELSE 8.4 END AS parcel_weight
FROM clean.products;

-- Every analysis file builds on these two views so revenue is defined in
-- exactly one place (see docs/kpi_dictionary.md).

-- One row per order with its totals. Cancelled orders keep their line
-- values (for cancellation KPIs) but contribute 0 net revenue.
CREATE VIEW clean.order_summary AS
SELECT o.*,
       i.lines,
       i.units,
       i.gross_amount,
       i.discount_amount,
       i.net_before_refund,
       i.cogs,
       i.has_bulk,
       CASE WHEN o.status = 'cancelled' THEN 0
            ELSE i.net_before_refund - o.refund_amount END                 AS net_revenue,
       -- Gross profit = net revenue - cost of goods - outbound shipping
       -- (delivery is free for the customer, so the shop pays the carrier).
       CASE WHEN o.status = 'cancelled' THEN 0
            ELSE i.net_before_refund - o.refund_amount - i.cogs - o.shipping_cost END AS gross_profit,
       o.status <> 'cancelled'                                             AS is_fulfilled,
       -- Promise shown at checkout: 4 days in Greece, 7 days abroad.
       CASE WHEN o.delivery_date IS NULL THEN NULL
            ELSE (o.delivery_date - o.order_date)
                 > CASE WHEN o.country = 'Greece' THEN 4 ELSE 7 END END   AS is_late
FROM clean.orders o
JOIN (
    SELECT order_id,
           count(*)                    AS lines,
           sum(quantity)               AS units,
           sum(gross_amount)           AS gross_amount,
           sum(discount_amount)        AS discount_amount,
           sum(net_amount)             AS net_before_refund,
           sum(quantity * unit_cost)   AS cogs,
           sum(quantity * parcel_weight) AS parcel_weight,
           bool_or(is_bulk)            AS has_bulk
    FROM clean.order_items
    JOIN clean.parcel_weights USING (product_id)
    GROUP BY order_id
) i USING (order_id);

-- One row per sold line of a fulfilled (completed or refunded) order. The
-- order's refund is spread over its lines in proportion to their value.
CREATE VIEW clean.sales_lines AS
SELECT i.transaction_id,
       i.order_id,
       o.customer_id,
       o.order_date,
       o.status,
       o.country,
       o.channel,
       i.product_id,
       p.product_name,
       p.category,
       i.quantity,
       i.unit_price,
       i.unit_cost,
       i.gross_amount,
       i.discount_amount,
       i.net_amount,
       -- Not rounded per line: rounding each share to cents leaks a few euros
       -- across 300k lines (caught by the reconciliation in Q11.1).
       COALESCE(o.refund_amount * i.net_amount
             / NULLIF(sum(i.net_amount) OVER (PARTITION BY i.order_id), 0), 0)  AS refund_amount,
       i.net_amount - COALESCE(o.refund_amount * i.net_amount
             / NULLIF(sum(i.net_amount) OVER (PARTITION BY i.order_id), 0), 0)  AS net_revenue,
       i.quantity * i.unit_cost                                                AS cogs,
       -- The order's carrier cost is spread over its lines by parcel weight
       -- (an L item takes ~8x the space of an S item).
       o.shipping_cost * i.quantity * w.parcel_weight
           / sum(i.quantity * w.parcel_weight) OVER (PARTITION BY i.order_id)  AS shipping_cost,
       i.net_amount - COALESCE(o.refund_amount * i.net_amount
             / NULLIF(sum(i.net_amount) OVER (PARTITION BY i.order_id), 0), 0)
         - i.quantity * i.unit_cost
         - o.shipping_cost * i.quantity * w.parcel_weight
           / sum(i.quantity * w.parcel_weight) OVER (PARTITION BY i.order_id)  AS gross_profit,
       i.is_bulk
FROM clean.order_items i
JOIN clean.orders o   USING (order_id)
JOIN clean.products p USING (product_id)
JOIN clean.parcel_weights w USING (product_id)
WHERE o.status <> 'cancelled';
