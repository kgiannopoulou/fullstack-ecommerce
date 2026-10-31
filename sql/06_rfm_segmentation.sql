-- =============================================================================
-- 06_rfm_segmentation.sql
-- Brief question 3 (continued): which customers matter most, and which are
-- slipping away? RFM = Recency, Frequency, Monetary, scored 1-5, as of the
-- day after the data ends (2026-01-01).
-- =============================================================================

-- Q06.1 | How do RFM segments compare in size, value and recency?
WITH c AS (
    SELECT customer_id,
           '2026-01-01'::date - max(order_date) AS recency_days,
           count(*)                            AS frequency,
           sum(net_revenue)                    AS monetary
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
    GROUP BY customer_id
),
scored AS (
    SELECT *,
           ntile(5) OVER (ORDER BY recency_days DESC, customer_id) AS r,
           -- most customers have 1 order, so quintiles would tie: fixed bands
           CASE WHEN frequency >= 5 THEN 5 WHEN frequency = 4 THEN 4 WHEN frequency = 3 THEN 3
                WHEN frequency = 2 THEN 2 ELSE 1 END AS f,
           ntile(5) OVER (ORDER BY monetary, customer_id) AS m
    FROM c
),
seg AS (
    SELECT *,
           CASE
             WHEN r >= 4 AND f >= 4                 THEN 'Champions'
             WHEN r >= 3 AND f >= 3                 THEN 'Loyal'
             WHEN r >= 4 AND f = 2                  THEN 'Potential Loyalists'
             WHEN r = 5 AND f = 1                   THEN 'New Customers'
             WHEN r = 4 AND f = 1                   THEN 'Promising'
             WHEN r = 3 AND f <= 2                  THEN 'Need Attention'
             WHEN r <= 2 AND f >= 3                 THEN 'Cannot Lose Them'
             WHEN r <= 2 AND f = 2                  THEN 'At Risk'
             WHEN r = 2 AND f = 1                   THEN 'Hibernating'
             ELSE 'Lost'
           END AS segment
    FROM scored
)
SELECT segment,
       count(*)                                                       AS customers,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1)             AS pct_customers,
       round(sum(monetary), 0)                                        AS revenue,
       round(100 * sum(monetary) / sum(sum(monetary)) OVER (), 1)     AS pct_revenue,
       round(sum(monetary) / sum(frequency), 2)                       AS avg_order_value,
       round(avg(frequency), 2)                                       AS avg_orders,
       round(avg(recency_days), 0)                                    AS avg_days_since_last_order,
       round(avg(monetary), 2)                                        AS revenue_per_customer
FROM seg
GROUP BY segment
ORDER BY revenue DESC;

-- Q06.2 | Which segments over-index on value? (revenue share / customer share)
WITH c AS (
    SELECT customer_id, '2026-01-01'::date - max(order_date) AS recency_days,
           count(*) AS frequency, sum(net_revenue) AS monetary
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
    GROUP BY customer_id
),
scored AS (
    SELECT *, ntile(5) OVER (ORDER BY recency_days DESC, customer_id) AS r,
           LEAST(frequency, 5) AS f          -- same bands as Q06.1
    FROM c
),
seg AS (
    SELECT *, CASE
             WHEN r >= 4 AND f >= 4 THEN 'Champions'
             WHEN r >= 3 AND f >= 3 THEN 'Loyal'
             WHEN r >= 4 AND f = 2  THEN 'Potential Loyalists'
             WHEN r = 5 AND f = 1   THEN 'New Customers'
             WHEN r = 4 AND f = 1   THEN 'Promising'
             WHEN r = 3 AND f <= 2  THEN 'Need Attention'
             WHEN r <= 2 AND f >= 3 THEN 'Cannot Lose Them'
             WHEN r <= 2 AND f = 2  THEN 'At Risk'
             WHEN r = 2 AND f = 1   THEN 'Hibernating'
             ELSE 'Lost' END AS segment
    FROM scored
)
SELECT segment,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1)                        AS pct_customers,
       round(100 * sum(monetary) / sum(sum(monetary)) OVER (), 1)                AS pct_revenue,
       round((sum(monetary) / sum(sum(monetary)) OVER ())
             / (count(*)::numeric / sum(count(*)) OVER ()), 2)                   AS value_index,
       CASE WHEN segment IN ('Cannot Lose Them', 'At Risk')       THEN 'Win-back now: high past value, going quiet'
            WHEN segment IN ('Champions', 'Loyal')                THEN 'Protect: loyalty perks, early access'
            WHEN segment IN ('Potential Loyalists', 'Need Attention') THEN 'Nurture: third-order incentive'
            WHEN segment IN ('New Customers', 'Promising')        THEN 'Onboard: second-order offer within 30 days'
            ELSE 'Low priority: occasional reactivation campaign' END             AS recommended_action
FROM seg
GROUP BY segment
ORDER BY value_index DESC;

-- Q06.3 | Win-back list: the 25 most valuable customers who have gone quiet.
WITH c AS (
    SELECT customer_id, '2026-01-01'::date - max(order_date) AS recency_days,
           count(*) AS frequency, sum(net_revenue) AS monetary, max(order_date) AS last_order
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT c.customer_id, cu.country, cu.acquisition_channel,
       c.frequency AS orders, round(c.monetary, 2) AS lifetime_revenue,
       c.last_order, c.recency_days
FROM c
JOIN clean.customers cu USING (customer_id)
WHERE c.frequency >= 3 AND c.recency_days > 180
ORDER BY c.monetary DESC
LIMIT 25;
