-- =============================================================================
-- 10_anomaly_investigation.sql
-- Which days, weeks and products behaved unusually, and why?
-- A day is an anomaly when its revenue is more than 3 standard deviations
-- from the same weekday's average over the previous 8 weeks (comparing
-- Saturdays with Saturdays removes the weekly cycle).
-- =============================================================================

-- Q10.1 | Which days were statistical outliers (|z| > 3 against the same weekday's last 8 weeks)?
WITH daily AS (
    SELECT d::date AS day, COALESCE(sum(o.net_revenue), 0) AS revenue
    FROM generate_series('2024-01-01'::date, '2025-12-31'::date, '1 day') d
    LEFT JOIN clean.order_summary o ON o.order_date = d::date
    GROUP BY 1
),
baseline AS (
    SELECT day, revenue,
           avg(revenue)        OVER w AS mean_12w,
           stddev_samp(revenue) OVER w AS sd_12w
    FROM daily
    WINDOW w AS (PARTITION BY extract(isodow FROM day) ORDER BY day ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING)
)
SELECT day, to_char(day, 'Dy') AS weekday,
       round(revenue, 0)                          AS revenue,
       round(mean_12w, 0)                          AS expected_revenue,
       round((revenue - mean_12w) / sd_12w, 1)      AS z_score,
       CASE WHEN revenue > mean_12w THEN 'spike' ELSE 'dip' END AS direction
FROM baseline
WHERE day >= '2024-03-01'                      -- needs 8 weeks of history
  AND abs((revenue - mean_12w) / NULLIF(sd_12w, 0)) > 3
ORDER BY day;

-- Q10.2 | What explains the biggest spikes? Order volume, discount share and AOV vs a normal day.
WITH spike_days AS (
    SELECT unnest(ARRAY['2024-11-29','2024-12-02','2025-11-28','2025-12-01']::date[]) AS day
),
by_day AS (
    SELECT o.order_date AS day,
           count(*) FILTER (WHERE o.is_fulfilled)                                        AS orders,
           round(100.0 * count(*) FILTER (WHERE o.discount_pct > 0 AND o.is_fulfilled)
                 / count(*) FILTER (WHERE o.is_fulfilled), 1)                           AS discounted_orders_pct,
           round(avg(o.discount_pct) FILTER (WHERE o.discount_pct > 0) * 100, 1)         AS avg_discount_pct,
           round(sum(o.net_revenue) / count(*) FILTER (WHERE o.is_fulfilled), 2)         AS aov
    FROM clean.order_summary o
    GROUP BY 1
)
SELECT CASE WHEN s.day IS NOT NULL THEN to_char(b.day, 'YYYY-MM-DD') ELSE 'Average other day' END AS day,
       round(avg(b.orders), 0)                AS orders,
       round(avg(b.discounted_orders_pct), 1) AS discounted_orders_pct,
       round(avg(b.avg_discount_pct), 1)      AS avg_discount_pct,
       round(avg(b.aov), 2)                   AS aov
FROM by_day b
LEFT JOIN spike_days s ON s.day = b.day
GROUP BY 1
ORDER BY 1;

-- Q10.3 | Which products' sales fell sharply while still in stock (last 12 weeks vs prior 12)?
WITH w AS (
    SELECT i.product_id,
           sum(i.units_sold) FILTER (WHERE i.snapshot_date >  '2025-12-31'::date - 84)  AS units_last_12w,
           sum(i.units_sold) FILTER (WHERE i.snapshot_date <= '2025-12-31'::date - 84
                                       AND i.snapshot_date >  '2025-12-31'::date - 168) AS units_prior_12w,
           min(i.stock_on_hand) FILTER (WHERE i.snapshot_date > '2025-12-31'::date - 84) AS min_stock_last_12w
    FROM clean.inventory_daily i
    GROUP BY 1
)
SELECT p.product_name, p.category, w.units_prior_12w, w.units_last_12w,
       round(100 * (w.units_last_12w::numeric / w.units_prior_12w - 1), 1) AS change_pct,
       w.min_stock_last_12w
FROM w JOIN clean.products p USING (product_id)
WHERE w.units_prior_12w >= 40
  AND w.units_last_12w < 0.6 * w.units_prior_12w
  AND w.min_stock_last_12w > 0               -- had stock: this is demand, not supply
ORDER BY w.units_prior_12w DESC;

-- Q10.4 | Were there weeks with unusually many refunds?
WITH wk AS (
    SELECT date_trunc('week', order_date)::date AS week,
           100.0 * count(*) FILTER (WHERE status = 'refunded') / count(*) FILTER (WHERE is_fulfilled) AS refund_rate
    FROM clean.order_summary
    GROUP BY 1
),
z AS (
    SELECT week, refund_rate,
           (refund_rate - avg(refund_rate) OVER ()) / stddev_samp(refund_rate) OVER () AS z
    FROM wk
)
SELECT week, round(refund_rate, 2) AS refund_rate_pct, round(z, 1) AS z_score
FROM z
WHERE abs(z) > 2.5
ORDER BY week;

-- Q10.5 | Bulk orders: who places them and are they legitimate?
SELECT o.order_id, o.order_date, o.customer_id IS NULL AS is_guest, o.country, o.payment_method,
       p.product_name, i.quantity, i.unit_price,
       round(i.unit_price / p.list_price, 2) AS price_vs_list, o.status
FROM clean.order_items i
JOIN clean.orders o USING (order_id)
JOIN clean.products p USING (product_id)
WHERE i.is_bulk
ORDER BY i.quantity DESC
LIMIT 20;

-- -----------------------------------------------------------------------------
-- Manual follow-up of an automated alert (src/anomaly_detection.py):
--   2025-01-06  Net revenue | Wearables | -83.9% vs expected (z = -5.7)
-- An alert is a question. These three queries answer it.
-- -----------------------------------------------------------------------------

-- Q10.6 | Re-check the alert: Wearables daily revenue vs the same weekday over the previous 8 weeks.
WITH d AS (
    SELECT g.day::date AS day, COALESCE(sum(s.net_revenue), 0) AS revenue
    FROM generate_series('2024-11-01'::date, '2025-01-31'::date, '1 day') g(day)
    LEFT JOIN clean.sales_lines s ON s.order_date = g.day AND s.category = 'Wearables'
    GROUP BY 1
),
w AS (
    SELECT day, revenue,
           avg(revenue) OVER (PARTITION BY extract(isodow FROM day) ORDER BY day
                              ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING) AS expected
    FROM d
)
SELECT day, to_char(day, 'Dy') AS weekday, round(revenue, 0) AS revenue, round(expected, 0) AS expected,
       round(100 * (revenue / NULLIF(expected, 0) - 1), 1) AS deviation_pct
FROM w
WHERE day BETWEEN '2024-12-22' AND '2025-01-19'
ORDER BY day;

-- Q10.7 | Which Wearables products explain the drop? Revenue 4 weeks before vs 4 weeks after 1 Jan 2025.
WITH r AS (
    SELECT product_id, product_name,
           sum(net_revenue) FILTER (WHERE order_date BETWEEN '2024-12-04' AND '2024-12-31') AS rev_before,
           sum(net_revenue) FILTER (WHERE order_date BETWEEN '2025-01-01' AND '2025-01-28') AS rev_after
    FROM clean.sales_lines
    WHERE category = 'Wearables'
    GROUP BY 1, 2
),
s AS (
    SELECT product_id,
           count(*) FILTER (WHERE stock_on_hand = 0 AND snapshot_date BETWEEN '2025-01-01' AND '2025-01-28') AS days_out_of_stock_after
    FROM clean.inventory_daily GROUP BY 1
)
SELECT r.product_name,
       round(COALESCE(rev_before, 0), 0)                              AS revenue_4w_before,
       round(COALESCE(rev_after, 0), 0)                               AS revenue_4w_after,
       round(COALESCE(rev_after, 0) - COALESCE(rev_before, 0), 0)     AS change,
       round(100 * (COALESCE(rev_after, 0) - COALESCE(rev_before, 0))
             / sum(COALESCE(rev_after, 0) - COALESCE(rev_before, 0)) OVER (), 1) AS share_of_category_change_pct,
       s.days_out_of_stock_after
FROM r JOIN s USING (product_id)
WHERE COALESCE(rev_before, 0) + COALESCE(rev_after, 0) > 0
ORDER BY change
LIMIT 8;

-- Q10.8 | The top SKU's stock story: when did it run out, and was anything reordered?
WITH p AS (
    SELECT product_id FROM clean.products WHERE product_name = 'Fitness Band O174'
),
inv AS (
    SELECT i.* FROM clean.inventory_daily i JOIN p USING (product_id)
)
SELECT (SELECT max(snapshot_date) FROM inv WHERE units_received > 0)                       AS last_delivery,
       (SELECT min(snapshot_date) FROM inv WHERE stock_on_hand = 0 AND snapshot_date >= '2024-12-01') AS sold_out_on,
       (SELECT round(avg(units_sold), 1) FROM inv
         WHERE snapshot_date BETWEEN '2024-12-01' AND '2024-12-31')                         AS units_per_day_in_december,
       (SELECT count(*) FROM inv WHERE snapshot_date >= '2025-01-01' AND stock_on_hand = 0)  AS days_at_zero_in_2025,
       (SELECT COALESCE(sum(units_received), 0) FROM inv WHERE snapshot_date >= '2025-01-01') AS units_received_in_2025,
       (SELECT round(sum(net_revenue), 0) FROM clean.sales_lines JOIN p USING (product_id)
         WHERE order_date BETWEEN '2024-01-01' AND '2024-12-31')                            AS revenue_2024;
