-- =============================================================================
-- 03_revenue_trends.sql
-- Brief question 1 (continued): Is growth real and steady, or seasonal noise?
-- Daily -> weekly -> monthly -> quarterly -> yearly, with MoM / YoY growth
-- and rolling windows that smooth out the weekly cycle.
-- =============================================================================

-- Q03.1 | Monthly revenue with month-over-month and year-over-year growth.
WITH m AS (
    SELECT date_trunc('month', order_date)::date                  AS month,
           sum(net_revenue)                                       AS net_revenue,
           count(*) FILTER (WHERE is_fulfilled)                   AS orders,
           sum(net_revenue) / count(*) FILTER (WHERE is_fulfilled) AS aov
    FROM clean.order_summary
    GROUP BY 1
)
SELECT month,
       round(net_revenue, 0)                                                   AS net_revenue,
       orders,
       round(aov, 2)                                                           AS aov,
       round(100 * (net_revenue / lag(net_revenue) OVER w - 1), 1)            AS mom_growth_pct,
       round(100 * (net_revenue / lag(net_revenue, 12) OVER w - 1), 1)        AS yoy_growth_pct,
       round(100 * (orders::numeric / lag(orders, 12) OVER w - 1), 1)         AS yoy_order_growth_pct
FROM m
WINDOW w AS (ORDER BY month)
ORDER BY month;

-- Q03.2 | Quarterly revenue, quarter-over-quarter and year-over-year.
WITH q AS (
    SELECT date_trunc('quarter', order_date)::date AS quarter_start,
           sum(net_revenue) AS net_revenue,
           count(*) FILTER (WHERE is_fulfilled) AS orders
    FROM clean.order_summary
    GROUP BY 1
)
SELECT to_char(quarter_start, 'YYYY-"Q"Q')                                  AS quarter,
       round(net_revenue, 0)                                                AS net_revenue,
       orders,
       round(100 * (net_revenue / lag(net_revenue) OVER w - 1), 1)         AS qoq_growth_pct,
       round(100 * (net_revenue / lag(net_revenue, 4) OVER w - 1), 1)      AS yoy_growth_pct
FROM q
WINDOW w AS (ORDER BY quarter_start)
ORDER BY quarter_start;

-- Q03.3 | Weekly revenue and its 4-week moving average.
WITH w AS (
    SELECT date_trunc('week', order_date)::date AS week_start,
           sum(net_revenue) AS net_revenue,
           count(*) FILTER (WHERE is_fulfilled) AS orders
    FROM clean.order_summary
    GROUP BY 1
)
SELECT week_start,
       round(net_revenue, 0) AS net_revenue,
       orders,
       round(avg(net_revenue) OVER (ORDER BY week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 0) AS moving_avg_4w
FROM w
ORDER BY week_start;

-- Q03.4 | Daily revenue with rolling 30-day and 90-day totals (calendar filled, no gaps).
WITH days AS (
    SELECT d::date AS day FROM generate_series('2024-01-01'::date, '2025-12-31'::date, '1 day') d
),
daily AS (
    SELECT order_date AS day, sum(net_revenue) AS net_revenue, count(*) FILTER (WHERE is_fulfilled) AS orders
    FROM clean.order_summary GROUP BY 1
)
SELECT d.day,
       round(COALESCE(x.net_revenue, 0), 0)                                    AS net_revenue,
       COALESCE(x.orders, 0)                                                   AS orders,
       round(sum(COALESCE(x.net_revenue, 0)) OVER (ORDER BY d.day ROWS BETWEEN 29 PRECEDING AND CURRENT ROW), 0) AS rolling_30d_revenue,
       round(sum(COALESCE(x.net_revenue, 0)) OVER (ORDER BY d.day ROWS BETWEEN 89 PRECEDING AND CURRENT ROW), 0) AS rolling_90d_revenue
FROM days d
LEFT JOIN daily x USING (day)
ORDER BY d.day;

-- Q03.5 | Rolling 90-day revenue at each year-end: underlying growth without seasonality noise.
WITH daily AS (
    SELECT d::date AS day, COALESCE(sum(o.net_revenue), 0) AS net_revenue
    FROM generate_series('2024-01-01'::date, '2025-12-31'::date, '1 day') d
    LEFT JOIN clean.order_summary o ON o.order_date = d::date
    GROUP BY 1
),
rolling AS (
    SELECT day, sum(net_revenue) OVER (ORDER BY day ROWS BETWEEN 89 PRECEDING AND CURRENT ROW) AS r90
    FROM daily
)
SELECT day, round(r90, 0) AS rolling_90d_revenue,
       round(100 * (r90 / lag(r90, 2) OVER (ORDER BY day) - 1), 1) AS yoy_growth_pct
FROM rolling
WHERE day IN ('2024-06-30', '2024-12-31', '2025-06-30', '2025-12-31')
ORDER BY day;

-- Q03.6 | Which ten days earned the most, and what drove them?
SELECT order_date,
       to_char(order_date, 'Dy') AS weekday,
       round(sum(net_revenue), 0) AS net_revenue,
       count(*) FILTER (WHERE is_fulfilled) AS orders,
       round(100.0 * count(*) FILTER (WHERE discount_pct > 0 AND is_fulfilled)
             / count(*) FILTER (WHERE is_fulfilled), 0) AS pct_orders_discounted
FROM clean.order_summary
GROUP BY order_date
ORDER BY net_revenue DESC
LIMIT 10;

-- Q03.7 | Which weekdays sell most (average per day)?
SELECT extract(isodow FROM order_date)::int AS iso_weekday,
       to_char(min(order_date), 'Day')     AS weekday,
       round(sum(net_revenue) / count(DISTINCT order_date), 0) AS avg_daily_revenue,
       round(count(*) FILTER (WHERE is_fulfilled)::numeric / count(DISTINCT order_date), 1) AS avg_daily_orders
FROM clean.order_summary
GROUP BY 1
ORDER BY 1;

-- Q03.8 | Why did AOV fall while revenue grew? Price, basket size or product mix?
WITH y AS (
    SELECT extract(year FROM order_date)::int AS yr,
           sum(net_revenue) / count(DISTINCT order_id)              AS aov,
           sum(quantity)::numeric / count(DISTINCT order_id)        AS units_per_order,
           sum(net_revenue) / sum(quantity)                         AS revenue_per_unit,
           100.0 * sum(net_revenue) FILTER (WHERE category IN ('Phone Accessories', 'Office', 'Home & Kitchen'))
                 / sum(net_revenue)                                 AS low_price_category_share
    FROM clean.sales_lines
    GROUP BY 1
),
discounts AS (
    SELECT extract(year FROM order_date)::int AS yr,
           100.0 * sum(discount_amount) / sum(gross_amount) AS discount_rate
    FROM clean.sales_lines GROUP BY 1
),
prices AS (
    -- Like-for-like: each product's 2025 price against its own 2024 price,
    -- averaged over products sold in both years (mix cannot move this).
    SELECT round(100 * (avg(p25 / p24) - 1), 2) AS like_for_like_price_change_pct
    FROM (SELECT product_id,
                 avg(unit_price) FILTER (WHERE order_date <  '2025-01-01') AS p24,
                 avg(unit_price) FILTER (WHERE order_date >= '2025-01-01') AS p25
          FROM clean.sales_lines GROUP BY product_id) per_product
    WHERE p24 IS NOT NULL AND p25 IS NOT NULL
)
SELECT y.yr,
       round(y.aov, 2)                         AS aov,
       round(y.units_per_order, 3)             AS units_per_order,
       round(y.revenue_per_unit, 2)            AS revenue_per_unit,
       round(y.low_price_category_share, 1)    AS low_price_category_share_pct,
       round(d.discount_rate, 2)               AS discount_rate_pct,
       p.like_for_like_price_change_pct
FROM y JOIN discounts d USING (yr) CROSS JOIN prices p
ORDER BY y.yr;
