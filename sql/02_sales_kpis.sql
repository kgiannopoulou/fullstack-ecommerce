-- =============================================================================
-- 02_sales_kpis.sql
-- Brief question 1: How is the business performing?
-- Headline KPIs as defined in docs/kpi_dictionary.md.
-- =============================================================================

-- Q02.1 | What are the headline KPIs for each year and for the whole period?
SELECT COALESCE(extract(year FROM order_date)::text, 'Total')                  AS period,
       round(sum(gross_amount) FILTER (WHERE is_fulfilled), 0)                 AS gross_revenue,
       round(sum(discount_amount) FILTER (WHERE is_fulfilled), 0)              AS discounts,
       round(sum(refund_amount), 0)                                            AS refunds,
       round(sum(net_revenue), 0)                                              AS net_revenue,
       count(*)                                                                AS orders_placed,
       count(*) FILTER (WHERE is_fulfilled)                                    AS fulfilled_orders,
       sum(units) FILTER (WHERE is_fulfilled)                                  AS units_sold,
       round(sum(net_revenue) / count(*) FILTER (WHERE is_fulfilled), 2)       AS avg_order_value,
       round(100.0 * count(*) FILTER (WHERE status = 'refunded')
                   / count(*) FILTER (WHERE is_fulfilled), 2)                  AS refund_rate_pct,
       round(100.0 * count(*) FILTER (WHERE status = 'cancelled') / count(*), 2) AS cancellation_rate_pct,
       round(sum(gross_profit), 0)                                             AS gross_profit,
       round(100.0 * sum(gross_profit) / sum(net_revenue), 1)                 AS gross_margin_pct,
       count(DISTINCT customer_id) FILTER (WHERE is_fulfilled)                 AS active_customers
FROM clean.order_summary
GROUP BY ROLLUP (extract(year FROM order_date))
ORDER BY period;

-- Q02.2 | Are we actually growing? Every headline KPI, 2025 vs 2024.
WITH y AS (
    SELECT extract(year FROM order_date)::int                       AS yr,
           sum(net_revenue)                                         AS net_revenue,
           count(*) FILTER (WHERE is_fulfilled)                     AS fulfilled_orders,
           sum(units) FILTER (WHERE is_fulfilled)                   AS units_sold,
           sum(net_revenue) / count(*) FILTER (WHERE is_fulfilled)  AS aov,
           count(DISTINCT customer_id) FILTER (WHERE is_fulfilled)  AS active_customers,
           100.0 * count(*) FILTER (WHERE status = 'refunded') / count(*) FILTER (WHERE is_fulfilled) AS refund_rate,
           100.0 * count(*) FILTER (WHERE status = 'cancelled') / count(*) AS cancellation_rate
    FROM clean.order_summary
    GROUP BY 1
),
pivot AS (
    SELECT m.metric, m.ord,
           max(m.value) FILTER (WHERE y.yr = 2024) AS y2024,
           max(m.value) FILTER (WHERE y.yr = 2025) AS y2025
    FROM y
    CROSS JOIN LATERAL (VALUES
        (1, 'Net revenue (EUR)',      y.net_revenue),
        (2, 'Fulfilled orders',       y.fulfilled_orders),
        (3, 'Units sold',             y.units_sold),
        (4, 'Average order value',    y.aov),
        (5, 'Active customers',       y.active_customers),
        (6, 'Refund rate %',          y.refund_rate),
        (7, 'Cancellation rate %',    y.cancellation_rate)
    ) AS m(ord, metric, value)
    GROUP BY m.metric, m.ord
)
SELECT metric,
       round(y2024, 2) AS y2024,
       round(y2025, 2) AS y2025,
       CASE WHEN metric LIKE '%rate%' THEN round(y2025 - y2024, 2) END     AS change_pp,
       CASE WHEN metric NOT LIKE '%rate%' THEN round(100 * (y2025 - y2024) / y2024, 1) END AS change_pct
FROM pivot
ORDER BY ord;

-- Q02.3 | How much do bulk (B2B-size) orders distort the average order value?
SELECT 'All fulfilled orders' AS order_set,
       count(*) AS orders,
       round(avg(net_revenue), 2) AS mean_aov,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY net_revenue)::numeric, 2) AS median_order_value
FROM clean.order_summary WHERE is_fulfilled
UNION ALL
SELECT 'Excluding bulk orders', count(*), round(avg(net_revenue), 2),
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY net_revenue)::numeric, 2)
FROM clean.order_summary WHERE is_fulfilled AND NOT has_bulk
UNION ALL
SELECT 'Bulk orders only', count(*), round(avg(net_revenue), 2),
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY net_revenue)::numeric, 2)
FROM clean.order_summary WHERE is_fulfilled AND has_bulk;

-- Q02.4 | Which payment methods lose the most orders to cancellation?
SELECT payment_method,
       count(*)                                                        AS orders_placed,
       count(*) FILTER (WHERE status = 'cancelled')                    AS cancelled,
       round(100.0 * count(*) FILTER (WHERE status = 'cancelled') / count(*), 2) AS cancellation_rate_pct,
       round(sum(net_before_refund) FILTER (WHERE status = 'cancelled'), 0)      AS cancelled_value
FROM clean.order_summary
GROUP BY payment_method
ORDER BY cancellation_rate_pct DESC;

-- Q02.5 | How does each market perform?
SELECT country,
       count(*) FILTER (WHERE is_fulfilled)                                  AS fulfilled_orders,
       round(sum(net_revenue), 0)                                            AS net_revenue,
       round(100.0 * sum(net_revenue) / sum(sum(net_revenue)) OVER (), 1)    AS revenue_share_pct,
       round(sum(net_revenue) / count(*) FILTER (WHERE is_fulfilled), 2)     AS avg_order_value,
       round(100.0 * sum(net_revenue) FILTER (WHERE order_date >= '2025-01-01')
             / NULLIF(sum(net_revenue) FILTER (WHERE order_date < '2025-01-01'), 0) - 100, 1) AS yoy_growth_pct
FROM clean.order_summary
GROUP BY country
ORDER BY net_revenue DESC;
