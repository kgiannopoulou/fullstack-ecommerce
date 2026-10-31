-- =============================================================================
-- 11_reporting_views.sql
-- The reporting layer: a small star schema that Excel (Power Query) and
-- Power BI read, so every report uses the same definitions as the SQL
-- analysis. Recreated by run_sql.py before its questions run.
--
--   fact_sales  (one row per sold line)   fact_orders (one row per order)
--   dim_date    dim_product (ABC class)   dim_customer (cohort, RFM segment)
--   monthly_kpis   inventory_status   cohort_retention   data_quality
-- =============================================================================

DROP SCHEMA IF EXISTS reporting CASCADE;
CREATE SCHEMA reporting;

CREATE VIEW reporting.dim_date AS
SELECT d::date                                  AS date,
       extract(year FROM d)::int                AS year,
       extract(quarter FROM d)::int             AS quarter,
       to_char(d, 'YYYY-"Q"Q')                  AS year_quarter,
       extract(month FROM d)::int               AS month,
       to_char(d, 'YYYY-MM')                    AS year_month,
       to_char(d, 'Mon')                        AS month_name,
       extract(isodow FROM d)::int              AS weekday_number,
       to_char(d, 'Dy')                         AS weekday_name,
       extract(isodow FROM d) IN (6, 7)         AS is_weekend
FROM generate_series('2024-01-01'::date, '2025-12-31'::date, '1 day') d;

CREATE VIEW reporting.dim_product AS
WITH rev AS (
    SELECT product_id, sum(net_revenue) AS net_revenue
    FROM clean.sales_lines GROUP BY 1
)
SELECT p.product_id, p.sku, p.product_name, p.category, p.list_price, p.unit_cost,
       p.supplier_lead_time_days,
       COALESCE(r.net_revenue, 0) AS lifetime_net_revenue,
       CASE WHEN sum(r.net_revenue) OVER (ORDER BY r.net_revenue DESC NULLS LAST, p.product_id) - COALESCE(r.net_revenue, 0)
                 < 0.80 * sum(r.net_revenue) OVER () THEN 'A'
            WHEN sum(r.net_revenue) OVER (ORDER BY r.net_revenue DESC NULLS LAST, p.product_id) - COALESCE(r.net_revenue, 0)
                 < 0.95 * sum(r.net_revenue) OVER () THEN 'B'
            ELSE 'C' END AS abc_class
FROM clean.products p
LEFT JOIN rev r USING (product_id);

CREATE VIEW reporting.dim_customer AS
WITH c AS (
    SELECT customer_id,
           min(order_date)                     AS first_order_date,
           max(order_date)                     AS last_order_date,
           count(*)                            AS orders,
           sum(net_revenue)                    AS lifetime_revenue,
           '2026-01-01'::date - max(order_date) AS recency_days
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
    GROUP BY 1
),
scored AS (
    SELECT *, ntile(5) OVER (ORDER BY recency_days DESC, customer_id) AS r, LEAST(orders, 5) AS f
    FROM c
)
SELECT cu.customer_id, cu.country, cu.acquisition_channel, cu.signup_date,
       s.first_order_date,
       date_trunc('month', s.first_order_date)::date AS cohort_month,
       s.last_order_date, s.orders, s.lifetime_revenue, s.recency_days,
       s.r AS r_score, s.f AS f_score,
       CASE WHEN s.customer_id IS NULL THEN 'No purchase'
            WHEN r >= 4 AND f >= 4 THEN 'Champions'
            WHEN r >= 3 AND f >= 3 THEN 'Loyal'
            WHEN r >= 4 AND f = 2  THEN 'Potential Loyalists'
            WHEN r = 5 AND f = 1   THEN 'New Customers'
            WHEN r = 4 AND f = 1   THEN 'Promising'
            WHEN r = 3 AND f <= 2  THEN 'Need Attention'
            WHEN r <= 2 AND f >= 3 THEN 'Cannot Lose Them'
            WHEN r <= 2 AND f = 2  THEN 'At Risk'
            WHEN r = 2 AND f = 1   THEN 'Hibernating'
            ELSE 'Lost' END AS rfm_segment
FROM clean.customers cu
LEFT JOIN scored s USING (customer_id);

CREATE VIEW reporting.fact_sales AS
SELECT transaction_id, order_id, customer_id, order_date, product_id, country, channel, status,
       quantity, unit_price, gross_amount, discount_amount, refund_amount, net_revenue, cogs,
       net_revenue - cogs AS gross_profit, is_bulk
FROM clean.sales_lines;

CREATE VIEW reporting.fact_orders AS
SELECT order_id, customer_id, is_guest, order_date, status, payment_method, channel, country, courier,
       units, gross_amount, discount_amount, refund_amount, net_revenue, cogs,
       ship_date - order_date      AS days_to_ship,
       delivery_date - order_date  AS days_to_deliver,
       is_late, is_fulfilled, has_bulk
FROM clean.order_summary;

CREATE VIEW reporting.monthly_kpis AS
WITH m AS (
    SELECT date_trunc('month', order_date)::date                         AS month,
           sum(net_revenue)                                              AS net_revenue,
           sum(gross_amount) FILTER (WHERE is_fulfilled)                 AS gross_revenue,
           count(*)                                                      AS orders_placed,
           count(*) FILTER (WHERE is_fulfilled)                          AS fulfilled_orders,
           sum(units) FILTER (WHERE is_fulfilled)                        AS units_sold,
           count(DISTINCT customer_id) FILTER (WHERE is_fulfilled)       AS active_customers,
           count(*) FILTER (WHERE status = 'refunded')                   AS refunded_orders,
           count(*) FILTER (WHERE status = 'cancelled')                  AS cancelled_orders,
           count(*) FILTER (WHERE is_fulfilled AND NOT is_late)          AS on_time_orders,
           sum(cogs) FILTER (WHERE is_fulfilled)                         AS cogs
    FROM clean.order_summary
    GROUP BY 1
)
SELECT month, net_revenue, gross_revenue, orders_placed, fulfilled_orders, units_sold, active_customers,
       round(net_revenue / fulfilled_orders, 2)                                  AS avg_order_value,
       round(100.0 * refunded_orders / fulfilled_orders, 2)                      AS refund_rate_pct,
       round(100.0 * cancelled_orders / orders_placed, 2)                        AS cancellation_rate_pct,
       round(100.0 * on_time_orders / fulfilled_orders, 1)                       AS on_time_delivery_pct,
       round(100 * (net_revenue - cogs) / net_revenue, 1)                        AS gross_margin_pct,
       round(100 * (net_revenue / lag(net_revenue) OVER (ORDER BY month) - 1), 1)     AS mom_growth_pct,
       round(100 * (net_revenue / lag(net_revenue, 12) OVER (ORDER BY month) - 1), 1) AS yoy_growth_pct
FROM m;

CREATE VIEW reporting.inventory_status AS
WITH last90 AS (
    SELECT product_id, sum(units_sold) AS units_90d,
           count(*) FILTER (WHERE stock_on_hand > 0 OR units_sold > 0) AS in_stock_days
    FROM clean.inventory_daily WHERE snapshot_date > '2025-12-31'::date - 90 GROUP BY 1
),
pos AS (
    SELECT p.product_id, p.product_name, p.category, p.abc_class, p.unit_cost,
           p.supplier_lead_time_days AS lead_time, i.stock_on_hand AS stock,
           l.units_90d, round(l.units_90d::numeric / NULLIF(l.in_stock_days, 0), 2) AS avg_daily_demand
    FROM reporting.dim_product p
    JOIN clean.inventory_daily i ON i.product_id = p.product_id AND i.snapshot_date = '2025-12-31'
    JOIN last90 l ON l.product_id = p.product_id
)
SELECT *, round(stock / NULLIF(avg_daily_demand, 0), 1) AS days_cover,
       stock * unit_cost AS stock_value_at_cost,
       CASE WHEN stock > 0 AND units_90d = 0 THEN 'DEAD STOCK'
            WHEN units_90d = 0 THEN 'INACTIVE'
            WHEN stock / avg_daily_demand < lead_time THEN 'CRITICAL'
            WHEN stock / avg_daily_demand < lead_time + 7 THEN 'HIGH RISK'
            WHEN stock / avg_daily_demand > 120 THEN 'OVERSTOCK'
            ELSE 'HEALTHY' END AS stock_status
FROM pos;

-- Long format (cohort, month_n, retention) is what a matrix visual wants.
CREATE VIEW reporting.cohort_retention AS
WITH o AS (
    SELECT DISTINCT customer_id, date_trunc('month', order_date)::date AS order_month
    FROM clean.order_summary WHERE is_fulfilled AND customer_id IS NOT NULL
),
f AS (SELECT customer_id, min(order_month) AS cohort FROM o GROUP BY 1),
a AS (
    SELECT f.cohort,
           (extract(year FROM age(o.order_month, f.cohort)) * 12
            + extract(month FROM age(o.order_month, f.cohort)))::int AS month_n,
           count(DISTINCT o.customer_id) AS customers
    FROM o JOIN f USING (customer_id)
    GROUP BY 1, 2
)
SELECT a.cohort, a.month_n, a.customers,
       first_value(a.customers) OVER (PARTITION BY a.cohort ORDER BY a.month_n) AS cohort_size,
       round(100.0 * a.customers / first_value(a.customers) OVER (PARTITION BY a.cohort ORDER BY a.month_n), 1) AS retention_pct
FROM a;

CREATE VIEW reporting.data_quality AS
SELECT check_id, check_name, table_name, records, action, rationale FROM clean.data_quality_log;

-- Q11.1 | Do the reporting views reconcile with the source tables?
SELECT 'fact_sales net revenue = order_summary net revenue' AS check_name,
       round((SELECT sum(net_revenue) FROM reporting.fact_sales), 2)  AS left_value,
       round((SELECT sum(net_revenue) FROM clean.order_summary), 2)   AS right_value,
       abs((SELECT sum(net_revenue) FROM reporting.fact_sales)
         - (SELECT sum(net_revenue) FROM clean.order_summary)) < 1    AS passes
UNION ALL
SELECT 'monthly_kpis net revenue = fact_orders net revenue',
       (SELECT round(sum(net_revenue), 2) FROM reporting.monthly_kpis),
       (SELECT round(sum(net_revenue), 2) FROM reporting.fact_orders),
       abs((SELECT sum(net_revenue) FROM reporting.monthly_kpis) - (SELECT sum(net_revenue) FROM reporting.fact_orders)) < 1
UNION ALL
SELECT 'every product has exactly one ABC class',
       (SELECT count(*) FROM reporting.dim_product), (SELECT count(*) FROM clean.products),
       (SELECT count(*) FROM reporting.dim_product) = (SELECT count(*) FROM clean.products)
UNION ALL
SELECT 'every customer appears once in dim_customer',
       (SELECT count(*) FROM reporting.dim_customer), (SELECT count(DISTINCT customer_id) FROM clean.customers),
       (SELECT count(*) FROM reporting.dim_customer) = (SELECT count(DISTINCT customer_id) FROM clean.customers);

-- Q11.2 | Monthly KPI table that feeds the dashboard's first page.
SELECT * FROM reporting.monthly_kpis ORDER BY month;

-- Q11.3 | Inventory status table that feeds the operations page.
SELECT stock_status, abc_class, count(*) AS products, round(sum(stock_value_at_cost), 0) AS stock_value_at_cost
FROM reporting.inventory_status
GROUP BY 1, 2
ORDER BY 1, 2;
