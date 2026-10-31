-- =============================================================================
-- 07_cohort_retention.sql
-- Brief question 3 (continued): is retention improving for newer customers,
-- and why?  Observation -> investigation -> explanation -> recommendation.
--
-- Cohort = month of a customer's first fulfilled order.
-- Month N retention = share of the cohort that ordered again in calendar
-- month N after the first-order month. Cells without a full month of data
-- are left empty rather than shown as 0%.
-- =============================================================================

-- Q07.1 | Cohort retention matrix (Month 1 - Month 12).
WITH o AS (
    SELECT customer_id, date_trunc('month', order_date)::date AS order_month
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
),
firsts AS (
    SELECT customer_id, min(order_month) AS cohort FROM o GROUP BY 1
),
activity AS (
    SELECT DISTINCT f.cohort, o.customer_id,
           (extract(year FROM age(o.order_month, f.cohort)) * 12
            + extract(month FROM age(o.order_month, f.cohort)))::int AS month_n
    FROM o JOIN firsts f USING (customer_id)
),
sizes AS (SELECT cohort, count(*) AS cohort_size FROM firsts GROUP BY 1)
SELECT a.cohort,
       s.cohort_size,
       -- retention for month N exists only if cohort + N <= Dec 2025
       round(100.0 * count(*) FILTER (WHERE month_n = 1) / s.cohort_size, 1) AS m1,
       CASE WHEN a.cohort <= '2025-10-01' THEN round(100.0 * count(*) FILTER (WHERE month_n = 2) / s.cohort_size, 1) END AS m2,
       CASE WHEN a.cohort <= '2025-09-01' THEN round(100.0 * count(*) FILTER (WHERE month_n = 3) / s.cohort_size, 1) END AS m3,
       CASE WHEN a.cohort <= '2025-08-01' THEN round(100.0 * count(*) FILTER (WHERE month_n = 4) / s.cohort_size, 1) END AS m4,
       CASE WHEN a.cohort <= '2025-07-01' THEN round(100.0 * count(*) FILTER (WHERE month_n = 5) / s.cohort_size, 1) END AS m5,
       CASE WHEN a.cohort <= '2025-06-01' THEN round(100.0 * count(*) FILTER (WHERE month_n = 6) / s.cohort_size, 1) END AS m6,
       CASE WHEN a.cohort <= '2025-03-01' THEN round(100.0 * count(*) FILTER (WHERE month_n = 9) / s.cohort_size, 1) END AS m9,
       CASE WHEN a.cohort <= '2024-12-01' THEN round(100.0 * count(*) FILTER (WHERE month_n = 12) / s.cohort_size, 1) END AS m12
FROM activity a
JOIN sizes s USING (cohort)
WHERE a.cohort <= '2025-11-01'
GROUP BY a.cohort, s.cohort_size
ORDER BY a.cohort;

-- Q07.2 | Observation: did 90-day repeat purchasing improve year over year?
-- Same calendar months a year apart, so seasonality cannot explain the difference.
WITH ranked AS (
    SELECT customer_id, order_date,
           row_number() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS n,
           lead(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS next_order
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
),
repeat AS (
    SELECT customer_id, order_date AS first_order,
           COALESCE(next_order - order_date <= 90, false) AS repeat_90d
    FROM ranked
    WHERE n = 1
)
SELECT to_char(first_order, 'Mon') AS cohort_month,
       round(100.0 * count(*) FILTER (WHERE repeat_90d AND first_order < '2025-01-01')
             / count(*) FILTER (WHERE first_order < '2025-01-01'), 1) AS repeat_90d_2024_pct,
       round(100.0 * count(*) FILTER (WHERE repeat_90d AND first_order >= '2025-01-01')
             / count(*) FILTER (WHERE first_order >= '2025-01-01'), 1) AS repeat_90d_2025_pct,
       round(100.0 * count(*) FILTER (WHERE repeat_90d AND first_order >= '2025-01-01')
             / count(*) FILTER (WHERE first_order >= '2025-01-01')
           - 100.0 * count(*) FILTER (WHERE repeat_90d AND first_order < '2025-01-01')
             / count(*) FILTER (WHERE first_order < '2025-01-01'), 1) AS change_pp
FROM repeat
WHERE extract(month FROM first_order) BETWEEN 1 AND 9      -- 90 days observable in both years
GROUP BY extract(month FROM first_order), to_char(first_order, 'Mon')
ORDER BY extract(month FROM first_order);

-- Q07.3 | Investigation: was it the loyalty programme or faster delivery?
-- Two things changed in 2025: the loyalty programme (1 Mar) and a faster
-- courier in Greece (15 May). Split first orders by period and by whether the
-- first delivery was late.
WITH ranked AS (
    SELECT customer_id, order_date, is_late, country,
           row_number() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS n,
           lead(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS next_order
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
)
SELECT CASE WHEN order_date < '2025-03-01' THEN '1) before loyalty programme'
            WHEN order_date < '2025-05-15' THEN '2) loyalty, old courier'
            ELSE '3) loyalty + new courier' END                                    AS period,
       CASE WHEN is_late THEN 'late' ELSE 'on time' END                            AS first_delivery,
       count(*)                                                                    AS customers,
       round(100.0 * count(*) FILTER (WHERE next_order - order_date <= 90) / count(*), 1) AS repeat_90d_pct
FROM ranked
WHERE n = 1 AND order_date <= '2025-10-02'          -- 90 days observable
GROUP BY 1, 2
ORDER BY 1, 2;

-- Q07.4 | Explanation: how did the share of late first deliveries change by quarter?
WITH firsts AS (
    SELECT DISTINCT ON (customer_id) customer_id, order_date, country, is_late
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
    ORDER BY customer_id, order_date, order_id
)
SELECT date_trunc('quarter', order_date)::date                                  AS quarter,
       round(100.0 * count(*) FILTER (WHERE is_late AND country = 'Greece')
             / count(*) FILTER (WHERE country = 'Greece'), 1)                   AS late_first_delivery_greece_pct,
       round(100.0 * count(*) FILTER (WHERE is_late AND country <> 'Greece')
             / count(*) FILTER (WHERE country <> 'Greece'), 1)                  AS late_first_delivery_abroad_pct
FROM firsts
GROUP BY 1
ORDER BY 1;

-- Q07.5 | How much of the improvement does each change explain? (decomposition)
-- Repeat rate = share_on_time * rate_on_time + share_late * rate_late.
-- Holding the late-delivery mix at the "before" level isolates the loyalty
-- effect; the rest is the delivery (courier) effect.
WITH ranked AS (
    SELECT customer_id, order_date, is_late,
           row_number() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS n,
           lead(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS next_order
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
),
f AS (
    SELECT CASE WHEN order_date < '2025-03-01' THEN 'before' ELSE 'after' END AS period,
           is_late, (next_order - order_date <= 90) AS repeated
    FROM ranked
    WHERE n = 1 AND order_date <= '2025-10-02'
      AND (order_date < '2025-03-01' OR order_date >= '2025-05-15')
),
cells AS (
    SELECT period, is_late,
           count(*)::numeric / sum(count(*)) OVER (PARTITION BY period) AS share,
           avg(CASE WHEN repeated THEN 1 ELSE 0 END)                     AS rate
    FROM f GROUP BY 1, 2
),
rates AS (
    SELECT (SELECT sum(share * rate) FROM cells WHERE period = 'before') AS before_rate,
           (SELECT sum(share * rate) FROM cells WHERE period = 'after')  AS after_rate,
           -- after-period repeat rates, weighted with the before-period delivery mix
           (SELECT sum(b.share * a.rate)
              FROM cells a JOIN cells b ON b.is_late = a.is_late AND b.period = 'before'
             WHERE a.period = 'after')                                   AS after_rates_before_mix
)
SELECT round(100 * before_rate, 1)                               AS repeat_90d_before_pct,
       round(100 * after_rate, 1)                                AS repeat_90d_after_pct,
       round(100 * (after_rate - before_rate), 1)                AS total_change_pp,
       round(100 * (after_rates_before_mix - before_rate), 1)    AS loyalty_effect_pp,
       round(100 * (after_rate - after_rates_before_mix), 1)     AS delivery_effect_pp
FROM rates;
