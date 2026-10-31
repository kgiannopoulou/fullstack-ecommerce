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
