-- =============================================================================
-- 12_profitability.sql
-- Revenue is not profit. Which products, categories and markets actually make
-- money once discounts, refunds, cost of goods and shipping are counted?
--
--   Gross profit   = net revenue - COGS - outbound shipping
--   Gross margin % = gross profit / net revenue
-- (defined once in clean.order_summary / clean.sales_lines, see 00_schema.sql)
-- =============================================================================

-- Q12.1 | Revenue-to-profit bridge: where does each euro of list-price sales go?
WITH y AS (
    SELECT COALESCE(extract(year FROM order_date)::text, 'Total') AS period,
           sum(gross_amount) FILTER (WHERE is_fulfilled)            AS gross_sales,
           sum(discount_amount) FILTER (WHERE is_fulfilled)         AS discounts,
           sum(refund_amount)                                       AS refunds,
           sum(net_revenue)                                         AS net_revenue,
           sum(cogs) FILTER (WHERE is_fulfilled)                    AS cogs,
           sum(shipping_cost)                                       AS shipping,
           sum(gross_profit)                                        AS gross_profit
    FROM clean.order_summary
    GROUP BY ROLLUP (extract(year FROM order_date))
)
SELECT period,
       round(gross_sales, 0)  AS gross_sales,
       round(discounts, 0)    AS discounts,
       round(refunds, 0)      AS refunds,
       round(net_revenue, 0)  AS net_revenue,
       round(cogs, 0)         AS cogs,
       round(shipping, 0)     AS shipping_cost,
       round(gross_profit, 0) AS gross_profit,
       round(100 * gross_profit / net_revenue, 1) AS gross_margin_pct,
       round(100 * discounts / gross_sales, 1)    AS discount_pct_of_sales,
       round(100 * refunds / gross_sales, 1)      AS refund_pct_of_sales,
       round(100 * cogs / net_revenue, 1)         AS cogs_pct_of_revenue,
       round(100 * shipping / net_revenue, 1)     AS shipping_pct_of_revenue
FROM y
ORDER BY period;

-- Q12.2 | Quarterly gross margin and what moved it (each component as % of net revenue).
SELECT to_char(order_date, 'YYYY-"Q"Q')                                        AS quarter,
       round(sum(net_revenue), 0)                                              AS net_revenue,
       round(sum(gross_profit), 0)                                             AS gross_profit,
       round(100 * sum(gross_profit) / sum(net_revenue), 1)                    AS gross_margin_pct,
       round(100 * sum(cogs) FILTER (WHERE is_fulfilled) / sum(net_revenue), 1) AS cogs_pct,
       round(100 * sum(shipping_cost) / sum(net_revenue), 1)                   AS shipping_pct,
       round(100 * sum(discount_amount) FILTER (WHERE is_fulfilled)
                 / sum(gross_amount) FILTER (WHERE is_fulfilled), 1)           AS discount_rate_pct,
       round(100 * (sum(gross_profit) / sum(net_revenue)
             - lag(sum(gross_profit) / sum(net_revenue)) OVER (ORDER BY to_char(order_date, 'YYYY-"Q"Q'))), 1)
                                                                               AS margin_change_pp
FROM clean.order_summary
GROUP BY 1
ORDER BY 1;

-- Q12.3 | Category profitability in 2025: revenue rank vs gross-profit rank.
WITH c AS (
    SELECT category,
           sum(net_revenue)   AS net_revenue,
           sum(gross_profit)  AS gross_profit,
           sum(shipping_cost) AS shipping_cost,
           sum(cogs)          AS cogs
    FROM clean.sales_lines
    WHERE order_date >= '2025-01-01'
    GROUP BY category
)
SELECT category,
       round(net_revenue, 0)                                 AS net_revenue,
       round(gross_profit, 0)                                AS gross_profit,
       round(100 * gross_profit / net_revenue, 1)            AS gross_margin_pct,
       round(100 * cogs / net_revenue, 1)                    AS cogs_pct,
       round(100 * shipping_cost / net_revenue, 1)           AS shipping_pct,
       rank() OVER (ORDER BY net_revenue DESC)               AS revenue_rank,
       rank() OVER (ORDER BY gross_profit DESC)              AS profit_rank
FROM c
ORDER BY net_revenue DESC;

-- Q12.4 | Products whose revenue rank overstates their contribution (2025, top 50 by revenue).
WITH p AS (
    SELECT product_id, product_name, category,
           sum(net_revenue) AS net_revenue, sum(gross_profit) AS gross_profit,
           sum(discount_amount) / NULLIF(sum(gross_amount), 0) AS discount_rate,
           sum(shipping_cost) / NULLIF(sum(net_revenue), 0)    AS shipping_share,
           sum(cogs) / NULLIF(sum(net_revenue), 0)             AS cogs_share
    FROM clean.sales_lines
    WHERE order_date >= '2025-01-01'
    GROUP BY 1, 2, 3
),
r AS (
    SELECT *, rank() OVER (ORDER BY net_revenue DESC)  AS revenue_rank,
              rank() OVER (ORDER BY gross_profit DESC) AS profit_rank
    FROM p
)
SELECT revenue_rank, profit_rank, profit_rank - revenue_rank AS rank_drop,
       product_name, category,
       round(net_revenue, 0)                       AS net_revenue,
       round(gross_profit, 0)                      AS gross_profit,
       round(100 * gross_profit / net_revenue, 1)  AS gross_margin_pct,
       round(100 * cogs_share, 1)                  AS cogs_pct,
       round(100 * shipping_share, 1)              AS shipping_pct,
       round(100 * discount_rate, 1)               AS discount_pct,
       CASE WHEN cogs_share >= 0.55 THEN 'Low markup (high unit cost)'
            WHEN shipping_share >= 0.08 THEN 'Bulky: shipping eats the margin'
            ELSE 'Mixed' END                       AS main_driver
FROM r
WHERE revenue_rank <= 50 AND profit_rank - revenue_rank >= 5
ORDER BY rank_drop DESC;

-- Q12.5 | Revenue vs margin quadrant for every active product in 2025 (feeds the scatter plot).
WITH p AS (
    SELECT product_id, product_name, category,
           sum(net_revenue) AS net_revenue, sum(gross_profit) AS gross_profit, sum(quantity) AS units
    FROM clean.sales_lines
    WHERE order_date >= '2025-01-01'
    GROUP BY 1, 2, 3
    HAVING sum(net_revenue) > 0
),
m AS (
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY net_revenue)                 AS med_revenue,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY gross_profit / net_revenue)  AS med_margin
    FROM p
)
SELECT p.product_id, p.product_name, p.category, p.units,
       round(p.net_revenue, 0)                          AS net_revenue,
       round(p.gross_profit, 0)                         AS gross_profit,
       round(100 * p.gross_profit / p.net_revenue, 1)   AS gross_margin_pct,
       CASE WHEN p.net_revenue >= m.med_revenue AND p.gross_profit / p.net_revenue >= m.med_margin THEN 'Stars: high revenue, high margin'
            WHEN p.net_revenue >= m.med_revenue THEN 'Volume traps: high revenue, low margin'
            WHEN p.gross_profit / p.net_revenue >= m.med_margin THEN 'Niche: low revenue, high margin'
            ELSE 'Review: low revenue, low margin' END AS quadrant
FROM p CROSS JOIN m
ORDER BY p.net_revenue DESC;

-- Q12.6 | How much revenue and profit sits in each quadrant?
WITH q AS (
    SELECT p.product_id, p.net_revenue, p.gross_profit,
           CASE WHEN p.net_revenue >= m.med_revenue AND p.gross_profit / p.net_revenue >= m.med_margin THEN 'Stars'
                WHEN p.net_revenue >= m.med_revenue THEN 'Volume traps'
                WHEN p.gross_profit / p.net_revenue >= m.med_margin THEN 'Niche'
                ELSE 'Review' END AS quadrant
    FROM (SELECT product_id, sum(net_revenue) AS net_revenue, sum(gross_profit) AS gross_profit
          FROM clean.sales_lines WHERE order_date >= '2025-01-01'
          GROUP BY 1 HAVING sum(net_revenue) > 0) p
    CROSS JOIN (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY net_revenue) AS med_revenue,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY gross_profit / net_revenue) AS med_margin
                FROM (SELECT sum(net_revenue) AS net_revenue, sum(gross_profit) AS gross_profit
                      FROM clean.sales_lines WHERE order_date >= '2025-01-01'
                      GROUP BY product_id HAVING sum(net_revenue) > 0) x) m
)
SELECT quadrant, count(*) AS products,
       round(sum(net_revenue), 0)                                        AS net_revenue,
       round(100 * sum(net_revenue) / sum(sum(net_revenue)) OVER (), 1)  AS revenue_share_pct,
       round(sum(gross_profit), 0)                                       AS gross_profit,
       round(100 * sum(gross_profit) / sum(sum(gross_profit)) OVER (), 1) AS profit_share_pct,
       round(100 * sum(gross_profit) / sum(net_revenue), 1)              AS gross_margin_pct
FROM q
GROUP BY quadrant
ORDER BY net_revenue DESC;

-- Q12.7 | Which products lose money on every sale (2025)?
SELECT product_name, category,
       sum(quantity)                                         AS units,
       round(sum(net_revenue), 0)                            AS net_revenue,
       round(sum(cogs), 0)                                   AS cogs,
       round(sum(shipping_cost), 0)                          AS shipping_cost,
       round(sum(gross_profit), 0)                           AS gross_profit,
       round(sum(gross_profit) / sum(quantity), 2)           AS profit_per_unit
FROM clean.sales_lines
WHERE order_date >= '2025-01-01'
GROUP BY product_name, category
HAVING sum(gross_profit) < 0
ORDER BY gross_profit;

-- Q12.8 | What does each discount level cost? (fulfilled orders, bulk excluded)
SELECT round(100 * discount_pct)::int || '%'                 AS discount_code,
       count(*)                                              AS orders,
       round(avg(units), 2)                                  AS units_per_order,
       round(avg(gross_amount), 2)                           AS avg_basket_before_discount,
       round(avg(net_revenue), 2)                            AS avg_net_order_value,
       round(avg(gross_profit), 2)                           AS avg_gross_profit_per_order,
       round(100 * sum(gross_profit) / sum(net_revenue), 1)  AS gross_margin_pct
FROM clean.order_summary
WHERE is_fulfilled AND NOT has_bulk
GROUP BY discount_pct
ORDER BY discount_pct;

-- Q12.9 | The courier switch in Greece: what did faster delivery cost per order?
SELECT courier,
       CASE WHEN order_date < '2025-05-15' THEN 'before switch' ELSE 'after switch' END AS period,
       count(*)                                                  AS shipped_orders,
       round(avg(shipping_cost), 2)                              AS avg_shipping_cost,
       round(100 * sum(shipping_cost) / sum(net_revenue), 1)     AS shipping_pct_of_revenue,
       round(100.0 * count(*) FILTER (WHERE NOT is_late) / count(*), 1) AS on_time_pct,
       round(avg(delivery_date - order_date), 2)                 AS avg_days_to_deliver
FROM clean.order_summary
WHERE is_fulfilled AND country = 'Greece'
GROUP BY 1, 2
ORDER BY min(order_date);

-- Q12.10 | Margin by market: does selling abroad pay once shipping is counted?
SELECT country,
       count(*) FILTER (WHERE is_fulfilled)                  AS orders,
       round(sum(net_revenue), 0)                            AS net_revenue,
       round(sum(net_revenue) / count(*) FILTER (WHERE is_fulfilled), 2) AS avg_order_value,
       round(sum(shipping_cost) / count(*) FILTER (WHERE is_fulfilled), 2) AS avg_shipping_cost,
       round(100 * sum(shipping_cost) / sum(net_revenue), 1) AS shipping_pct,
       round(100 * sum(gross_profit) / sum(net_revenue), 1)  AS gross_margin_pct
FROM clean.order_summary
WHERE order_date >= '2025-01-01'
GROUP BY country
ORDER BY net_revenue DESC;
