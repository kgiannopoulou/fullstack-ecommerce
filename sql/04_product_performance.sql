-- =============================================================================
-- 04_product_performance.sql
-- Brief question 2: Which products and categories drive (or hurt) revenue?
-- =============================================================================

-- Q04.1 | How does each category perform, and which are growing?
SELECT category,
       round(sum(net_revenue), 0)                                                 AS net_revenue,
       round(100.0 * sum(net_revenue) / sum(sum(net_revenue)) OVER (), 1)         AS revenue_share_pct,
       sum(quantity)                                                              AS units_sold,
       round(sum(net_revenue) / sum(quantity), 2)                                 AS avg_selling_price,
       round(100.0 * (sum(net_revenue) - sum(cogs)) / sum(net_revenue), 1)        AS gross_margin_pct,
       round(100.0 * sum(refund_amount) / sum(net_amount), 2)                     AS refund_value_pct,
       round(100 * (sum(net_revenue) FILTER (WHERE order_date >= '2025-01-01')
                  / sum(net_revenue) FILTER (WHERE order_date <  '2025-01-01') - 1), 1) AS yoy_growth_pct
FROM clean.sales_lines
GROUP BY category
ORDER BY net_revenue DESC;

-- Q04.2 | Which 20 products earn the most, and how concentrated is revenue?
WITH p AS (
    SELECT product_id, product_name, category,
           sum(net_revenue) AS net_revenue, sum(quantity) AS units
    FROM clean.sales_lines
    GROUP BY 1, 2, 3
)
SELECT rank() OVER (ORDER BY net_revenue DESC)                                     AS rank,
       product_name, category,
       round(net_revenue, 0)                                                       AS net_revenue,
       units,
       round(100 * net_revenue / sum(net_revenue) OVER (), 2)                      AS share_pct,
       round(100 * sum(net_revenue) OVER (ORDER BY net_revenue DESC)
                 / sum(net_revenue) OVER (), 1)                                    AS cumulative_share_pct
FROM p
ORDER BY net_revenue DESC
LIMIT 20;

-- Q04.3 | ABC analysis: what share of SKUs produces 80% of revenue?
WITH p AS (
    SELECT product_id, sum(net_revenue) AS net_revenue
    FROM clean.sales_lines GROUP BY 1
),
ranked AS (
    SELECT product_id, net_revenue,
           sum(net_revenue) OVER (ORDER BY net_revenue DESC, product_id) / sum(net_revenue) OVER () AS cum_share
    FROM p
),
classed AS (
    -- A product belongs to the class in which its revenue *starts*, so the
    -- product that crosses 80% is still an A item.
    SELECT *, CASE WHEN cum_share - net_revenue / sum(net_revenue) OVER () < 0.80 THEN 'A'
                   WHEN cum_share - net_revenue / sum(net_revenue) OVER () < 0.95 THEN 'B'
                   ELSE 'C' END AS abc_class
    FROM ranked
)
SELECT abc_class,
       count(*)                                                       AS skus,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1)             AS pct_of_skus,
       round(sum(net_revenue), 0)                                     AS net_revenue,
       round(100 * sum(net_revenue) / sum(sum(net_revenue)) OVER (), 1) AS pct_of_revenue,
       round(avg(net_revenue), 0)                                     AS avg_revenue_per_sku
FROM classed
GROUP BY abc_class
ORDER BY abc_class;

-- Q04.4 | Which products had declining sales for three consecutive months in 2025?
WITH monthly AS (
    SELECT p.product_id, p.product_name, p.category, m::date AS month,
           COALESCE(sum(s.net_revenue), 0) AS revenue
    FROM clean.products p
    CROSS JOIN generate_series('2025-01-01'::date, '2025-12-01'::date, '1 month') m
    LEFT JOIN clean.sales_lines s
           ON s.product_id = p.product_id AND date_trunc('month', s.order_date) = m
    GROUP BY 1, 2, 3, 4
),
flags AS (
    SELECT *,
           revenue < lag(revenue) OVER w AS down,
           lag(revenue) OVER w           AS prev_revenue
    FROM monthly
    WINDOW w AS (PARTITION BY product_id ORDER BY month)
),
streaks AS (
    -- down three months running: this month, last month and the one before
    SELECT *, down AND lag(down) OVER w AND lag(down, 2) OVER w AS third_decline,
           lag(revenue, 3) OVER w AS revenue_before_streak
    FROM flags
    WINDOW w AS (PARTITION BY product_id ORDER BY month)
)
SELECT product_name, category,
       max(month) FILTER (WHERE third_decline)          AS latest_streak_end,
       count(*) FILTER (WHERE third_decline)            AS months_ending_a_3m_decline,
       round(sum(revenue) FILTER (WHERE month < '2025-07-01'), 0)  AS h1_2025_revenue,
       round(sum(revenue) FILTER (WHERE month >= '2025-07-01'), 0) AS h2_2025_revenue,
       round(100 * (sum(revenue) FILTER (WHERE month >= '2025-07-01')
                  / NULLIF(sum(revenue) FILTER (WHERE month < '2025-07-01'), 0) - 1), 1) AS h2_vs_h1_pct
FROM streaks
GROUP BY product_id, product_name, category
HAVING count(*) FILTER (WHERE third_decline) > 0
   AND sum(revenue) FILTER (WHERE month < '2025-07-01') > 5000
   -- a dip inside a rising year is noise; keep products that ended lower
   AND sum(revenue) FILTER (WHERE month >= '2025-07-01') < sum(revenue) FILTER (WHERE month < '2025-07-01')
ORDER BY h1_2025_revenue DESC
LIMIT 25;

-- Q04.5 | Which products grew fastest, and which collapsed (H2 2025 vs H2 2024, min EUR 5k base)?
WITH h AS (
    SELECT product_name, category,
           sum(net_revenue) FILTER (WHERE order_date BETWEEN '2024-07-01' AND '2024-12-31')              AS h2_2024,
           COALESCE(sum(net_revenue) FILTER (WHERE order_date BETWEEN '2025-07-01' AND '2025-12-31'), 0) AS h2_2025
    FROM clean.sales_lines
    GROUP BY product_id, product_name, category
    HAVING sum(net_revenue) FILTER (WHERE order_date BETWEEN '2024-07-01' AND '2024-12-31') > 5000
),
ranked AS (
    SELECT *, 100 * (h2_2025 / h2_2024 - 1) AS growth_pct,
           rank() OVER (ORDER BY h2_2025 / h2_2024 DESC) AS top,
           rank() OVER (ORDER BY h2_2025 - h2_2024)      AS worst
    FROM h
)
SELECT CASE WHEN top <= 10 THEN 'Fastest growing' ELSE 'Largest revenue loss' END AS list,
       product_name, category,
       round(h2_2024, 0) AS h2_2024, round(h2_2025, 0) AS h2_2025,
       round(h2_2025 - h2_2024, 0) AS change_eur,
       round(growth_pct, 1) AS growth_pct
FROM ranked
WHERE top <= 10 OR worst <= 10
ORDER BY list, CASE WHEN top <= 10 THEN top ELSE worst END;

-- Q04.6 | Which products are refunded unusually often (min 100 orders)?
WITH p AS (
    SELECT s.product_id, s.product_name, s.category,
           count(DISTINCT s.order_id)                                     AS orders,
           count(DISTINCT s.order_id) FILTER (WHERE s.status = 'refunded') AS refunded_orders,
           sum(s.refund_amount)                                           AS refunded_value
    FROM clean.sales_lines s
    GROUP BY 1, 2, 3
    HAVING count(DISTINCT s.order_id) >= 100
)
SELECT product_name, category, orders, refunded_orders,
       round(100.0 * refunded_orders / orders, 2)                               AS refund_rate_pct,
       round(100.0 * refunded_orders / orders
             - 100.0 * sum(refunded_orders) OVER () / sum(orders) OVER (), 2)   AS pp_above_average,
       round(refunded_value, 0)                                                 AS refunded_value
FROM p
ORDER BY refund_rate_pct DESC
LIMIT 15;

-- Q04.7 | Where does the margin come from? Revenue vs gross profit by category.
SELECT category,
       round(sum(net_revenue), 0)                                           AS net_revenue,
       round(sum(net_revenue) - sum(cogs), 0)                               AS gross_profit,
       round(100 * (sum(net_revenue) - sum(cogs)) / sum(sum(net_revenue) - sum(cogs)) OVER (), 1) AS share_of_profit_pct,
       round(100 * sum(net_revenue) / sum(sum(net_revenue)) OVER (), 1)     AS share_of_revenue_pct
FROM clean.sales_lines
GROUP BY category
ORDER BY gross_profit DESC;
