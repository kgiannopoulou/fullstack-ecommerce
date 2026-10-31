-- =============================================================================
-- 05_customer_analysis.sql
-- Brief question 3: Are customers returning after their first purchase?
-- Registered customers only (guest checkouts have no customer_id).
-- =============================================================================

-- Q05.1 | How large is the customer base and how often do customers come back?
WITH c AS (
    SELECT customer_id,
           count(*)          AS orders,
           sum(net_revenue)  AS revenue,
           min(order_date)   AS first_order,
           max(order_date)   AS last_order
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
    GROUP BY customer_id
),
gaps AS (
    SELECT order_date - lag(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS gap
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
)
SELECT count(*)                                                        AS customers_with_purchase,
       count(*) FILTER (WHERE orders > 1)                              AS repeat_customers,
       round(100.0 * count(*) FILTER (WHERE orders > 1) / count(*), 1) AS repeat_customer_rate_pct,
       round(avg(orders), 2)                                           AS orders_per_customer,
       round(avg(revenue), 2)                                          AS revenue_per_customer,
       round(avg(revenue) FILTER (WHERE orders > 1)
             / avg(revenue) FILTER (WHERE orders = 1), 1)              AS repeat_vs_one_time_value_ratio,
       round(100 * sum(revenue) FILTER (WHERE orders > 1) / sum(revenue), 1) AS revenue_from_repeat_customers_pct,
       (SELECT round(avg(gap), 1) FROM gaps WHERE gap IS NOT NULL)     AS avg_days_between_purchases,
       (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY gap) FROM gaps WHERE gap IS NOT NULL) AS median_days_between_purchases
FROM c;

-- Q05.2 | Each month: how much revenue comes from new vs returning customers?
WITH o AS (
    SELECT s.*, min(order_date) OVER (PARTITION BY customer_id) AS first_order
    FROM clean.order_summary s
    WHERE is_fulfilled AND customer_id IS NOT NULL
)
SELECT date_trunc('month', order_date)::date                                       AS month,
       count(DISTINCT customer_id) FILTER (WHERE order_date = first_order)          AS new_customers,
       count(DISTINCT customer_id) FILTER (WHERE order_date > first_order)          AS returning_customers,
       round(sum(net_revenue) FILTER (WHERE order_date = first_order), 0)          AS new_customer_revenue,
       round(sum(net_revenue) FILTER (WHERE order_date > first_order), 0)          AS returning_customer_revenue,
       round(100 * sum(net_revenue) FILTER (WHERE order_date > first_order) / sum(net_revenue), 1) AS returning_share_pct
FROM o
GROUP BY 1
ORDER BY 1;

-- Q05.3 | How many orders do customers place over their lifetime?
WITH c AS (
    SELECT customer_id, count(*) AS orders, sum(net_revenue) AS revenue
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
    GROUP BY 1
)
SELECT CASE WHEN orders >= 5 THEN '5+' ELSE orders::text END        AS orders_per_customer,
       count(*)                                                     AS customers,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1)           AS pct_customers,
       round(sum(revenue), 0)                                       AS revenue,
       round(100 * sum(revenue) / sum(sum(revenue)) OVER (), 1)     AS pct_revenue
FROM c
GROUP BY 1
ORDER BY 1;

-- Q05.4 | How long does it take to win the second order?
WITH ranked AS (
    SELECT customer_id, order_date,
           row_number() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS n
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
),
second AS (
    SELECT f.customer_id, s.order_date - f.order_date AS days_to_second
    FROM ranked f JOIN ranked s ON s.customer_id = f.customer_id AND s.n = 2
    WHERE f.n = 1
)
SELECT CASE WHEN days_to_second <= 30 THEN '1) within 30 days'
            WHEN days_to_second <= 60 THEN '2) 31-60 days'
            WHEN days_to_second <= 90 THEN '3) 61-90 days'
            WHEN days_to_second <= 180 THEN '4) 91-180 days'
            ELSE '5) over 180 days' END                                       AS time_to_second_order,
       count(*)                                                                 AS customers,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1)                       AS pct,
       round(100.0 * sum(count(*)) OVER (ORDER BY min(days_to_second)) / sum(count(*)) OVER (), 1) AS cumulative_pct
FROM second
GROUP BY 1
ORDER BY 1;

-- Q05.5 | Which acquisition channels bring customers who come back?
WITH c AS (
    SELECT o.customer_id, cu.acquisition_channel, count(*) AS orders, sum(o.net_revenue) AS revenue
    FROM clean.order_summary o
    JOIN clean.customers cu USING (customer_id)
    WHERE o.is_fulfilled
    GROUP BY 1, 2
)
SELECT acquisition_channel,
       count(*)                                                        AS customers,
       round(100.0 * count(*) FILTER (WHERE orders > 1) / count(*), 1) AS repeat_rate_pct,
       round(avg(orders), 2)                                           AS orders_per_customer,
       round(avg(revenue), 2)                                          AS revenue_per_customer
FROM c
GROUP BY 1
ORDER BY repeat_rate_pct DESC;

-- Q05.6 | Does repeat purchasing differ by market?
WITH c AS (
    SELECT o.customer_id, cu.country, count(*) AS orders, sum(o.net_revenue) AS revenue
    FROM clean.order_summary o
    JOIN clean.customers cu USING (customer_id)
    WHERE o.is_fulfilled
    GROUP BY 1, 2
)
SELECT country,
       count(*)                                                        AS customers,
       round(100.0 * count(*) FILTER (WHERE orders > 1) / count(*), 1) AS repeat_rate_pct,
       round(avg(revenue), 2)                                          AS revenue_per_customer
FROM c
GROUP BY 1
ORDER BY repeat_rate_pct DESC;

-- Q05.7 | Does a late first delivery reduce the chance of a second order?
-- Customers whose first order was placed at least 180 days before the end of
-- the data, so everyone had the same time to come back.
WITH ranked AS (
    SELECT customer_id, order_date, is_late,
           row_number() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS n,
           lead(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS next_order
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
)
SELECT CASE WHEN is_late THEN 'Late first delivery' ELSE 'On-time first delivery' END AS first_delivery,
       count(*)                                                                         AS customers,
       round(100.0 * count(*) FILTER (WHERE next_order - order_date <= 180) / count(*), 1) AS repeat_within_180d_pct
FROM ranked
WHERE n = 1 AND order_date <= '2025-07-04'
GROUP BY 1
ORDER BY 1;
