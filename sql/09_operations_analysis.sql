-- =============================================================================
-- 09_operations_analysis.sql
-- Brief questions 1 and 5: how well do we fulfil orders, and what operational
-- changes would move revenue and retention?
-- Delivery promise: 4 days in Greece, 7 days abroad (order date to delivery).
-- =============================================================================

-- Q09.1 | How long does fulfilment take, month by month?
SELECT date_trunc('month', order_date)::date                                          AS month,
       count(*)                                                                        AS shipped_orders,
       round(avg(ship_date - order_date), 2)                                          AS avg_days_to_ship,
       round(avg(delivery_date - ship_date), 2)                                       AS avg_days_in_transit,
       round(avg(delivery_date - order_date), 2)                                      AS avg_days_to_deliver,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY delivery_date - order_date)        AS p90_days_to_deliver,
       round(100.0 * count(*) FILTER (WHERE NOT is_late) / count(*), 1)               AS on_time_pct
FROM clean.order_summary
WHERE is_fulfilled
GROUP BY 1
ORDER BY 1;

-- Q09.2 | Did the courier switch (15 May 2025) improve on-time delivery, and where?
SELECT country,
       courier,
       count(*)                                                          AS orders,
       round(avg(delivery_date - order_date), 2)                        AS avg_days_to_deliver,
       round(100.0 * count(*) FILTER (WHERE NOT is_late) / count(*), 1) AS on_time_pct
FROM clean.order_summary
WHERE is_fulfilled
GROUP BY country, courier
ORDER BY country = 'Greece' DESC, country, courier;

-- Q09.3 | Are late deliveries refunded more often?
SELECT CASE WHEN is_late THEN 'Late' ELSE 'On time' END                         AS delivery,
       count(*)                                                                  AS orders,
       count(*) FILTER (WHERE status = 'refunded')                               AS refunded,
       round(100.0 * count(*) FILTER (WHERE status = 'refunded') / count(*), 2)  AS refund_rate_pct,
       round(sum(refund_amount), 0)                                              AS refunded_value
FROM clean.order_summary
WHERE is_fulfilled
GROUP BY 1
ORDER BY 1;

-- Q09.4 | Does a weekend order wait longer to ship?
SELECT to_char(order_date, 'ID Day')                     AS order_weekday,
       count(*)                                          AS orders,
       round(avg(ship_date - order_date), 2)             AS avg_days_to_ship,
       round(100.0 * count(*) FILTER (WHERE ship_date - order_date >= 2) / count(*), 1) AS shipped_after_2_plus_days_pct
FROM clean.order_summary
WHERE is_fulfilled
GROUP BY 1
ORDER BY 1;

-- Q09.5 | When do orders arrive? (staffing the warehouse and customer service)
SELECT extract(hour FROM order_ts)::int                               AS hour_of_day,
       count(*)                                                       AS orders,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1)             AS pct_of_orders
FROM clean.orders
WHERE order_ts::time <> '00:00'          -- date-only source records have no time of day
GROUP BY 1
ORDER BY 1;

-- Q09.6 | How is the payment mix shifting, and what does COD cost us in cancellations?
SELECT to_char(date_trunc('quarter', order_date), 'YYYY-"Q"Q')                         AS quarter,
       round(100.0 * count(*) FILTER (WHERE payment_method = 'Card') / count(*), 1)     AS card_pct,
       round(100.0 * count(*) FILTER (WHERE payment_method = 'PayPal') / count(*), 1)   AS paypal_pct,
       round(100.0 * count(*) FILTER (WHERE payment_method = 'Cash on Delivery') / count(*), 1) AS cod_pct,
       round(100.0 * count(*) FILTER (WHERE payment_method NOT IN ('Card', 'PayPal', 'Cash on Delivery')) / count(*), 1) AS other_pct,
       round(sum(net_before_refund) FILTER (WHERE status = 'cancelled' AND payment_method = 'Cash on Delivery'), 0) AS cod_cancelled_value
FROM clean.order_summary
GROUP BY date_trunc('quarter', order_date)
ORDER BY date_trunc('quarter', order_date);
