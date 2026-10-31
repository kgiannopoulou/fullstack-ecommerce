-- =============================================================================
-- 08_inventory_analysis.sql
-- Brief question 4: which products are at risk of stockout or overstock?
--
-- Position date: 2025-12-31 (last snapshot). A day counts as "in stock" if
-- the SKU had stock at the end of the day or sold something that day.
-- Demand is averaged over in-stock days only: a sold-out SKU sells 0, which
-- says nothing about how much customers wanted it.
-- No open purchase orders are in the data, so "days of cover" uses stock on
-- hand only; the actions below should be checked against open POs.
-- =============================================================================

-- Q08.1 | Stock position and recommended action for every active product.
WITH abc AS (
    SELECT product_id,
           CASE WHEN sum(rev) OVER (ORDER BY rev DESC, product_id) - rev < 0.80 * sum(rev) OVER () THEN 'A'
                WHEN sum(rev) OVER (ORDER BY rev DESC, product_id) - rev < 0.95 * sum(rev) OVER () THEN 'B'
                ELSE 'C' END AS abc_class
    FROM (SELECT product_id, sum(net_revenue) AS rev FROM clean.sales_lines GROUP BY 1) r
),
last90 AS (
    SELECT product_id,
           sum(units_sold)                                                   AS units_90d,
           count(*) FILTER (WHERE stock_on_hand > 0 OR units_sold > 0)       AS in_stock_days_90d
    FROM clean.inventory_daily
    WHERE snapshot_date > '2025-12-31'::date - 90
    GROUP BY 1
),
pos AS (
    SELECT p.product_id, p.product_name, p.category, p.supplier_lead_time_days AS lead_time,
           COALESCE(a.abc_class, 'C')                                         AS abc_class,
           i.stock_on_hand                                                    AS stock,
           l.units_90d,
           round(l.units_90d::numeric / NULLIF(l.in_stock_days_90d, 0), 2)   AS avg_daily_demand
    FROM clean.products p
    JOIN clean.inventory_daily i ON i.product_id = p.product_id AND i.snapshot_date = '2025-12-31'
    JOIN last90 l ON l.product_id = p.product_id
    LEFT JOIN abc a ON a.product_id = p.product_id
),
classified AS (
    SELECT *,
           round(stock / NULLIF(avg_daily_demand, 0), 1) AS days_cover,
           CASE WHEN stock > 0 AND units_90d = 0                               THEN 'DEAD STOCK'
                WHEN units_90d = 0                                            THEN 'INACTIVE'
                WHEN stock / avg_daily_demand < lead_time                     THEN 'CRITICAL'
                WHEN stock / avg_daily_demand < lead_time + 7                THEN 'HIGH RISK'
                WHEN stock / avg_daily_demand > 120                           THEN 'OVERSTOCK'
                ELSE 'HEALTHY' END AS stock_status
    FROM pos
)
SELECT product_name, category, abc_class, stock, avg_daily_demand, days_cover, lead_time,
       stock_status,
       CASE stock_status
         WHEN 'CRITICAL'   THEN CASE WHEN abc_class = 'A' THEN 'Reorder immediately (expedite)' ELSE 'Reorder immediately' END
         WHEN 'HIGH RISK'  THEN 'Reorder this week'
         WHEN 'OVERSTOCK'  THEN 'Pause purchasing; consider promotion'
         WHEN 'DEAD STOCK' THEN 'Clear: markdown, bundle or return to supplier'
         WHEN 'INACTIVE'   THEN 'No stock, no demand: confirm delisting'
         ELSE 'Monitor' END AS action
FROM classified
WHERE stock_status <> 'INACTIVE' OR abc_class <> 'C'
ORDER BY array_position(ARRAY['CRITICAL','HIGH RISK','DEAD STOCK','OVERSTOCK','HEALTHY','INACTIVE'], stock_status),
         abc_class, avg_daily_demand DESC;

-- Q08.2 | How many products (and how much stock value) sit in each risk class?
WITH last90 AS (
    SELECT product_id, sum(units_sold) AS units_90d,
           count(*) FILTER (WHERE stock_on_hand > 0 OR units_sold > 0) AS in_stock_days
    FROM clean.inventory_daily WHERE snapshot_date > '2025-12-31'::date - 90 GROUP BY 1
),
pos AS (
    SELECT p.product_id, p.unit_cost, p.supplier_lead_time_days AS lead_time, i.stock_on_hand AS stock,
           l.units_90d, l.units_90d::numeric / NULLIF(l.in_stock_days, 0) AS d
    FROM clean.products p
    JOIN clean.inventory_daily i ON i.product_id = p.product_id AND i.snapshot_date = '2025-12-31'
    JOIN last90 l ON l.product_id = p.product_id
),
c AS (
    SELECT *, CASE WHEN stock > 0 AND units_90d = 0 THEN 'DEAD STOCK'
                   WHEN units_90d = 0 THEN 'INACTIVE'
                   WHEN stock / d < lead_time THEN 'CRITICAL'
                   WHEN stock / d < lead_time + 7 THEN 'HIGH RISK'
                   WHEN stock / d > 120 THEN 'OVERSTOCK'
                   ELSE 'HEALTHY' END AS stock_status
    FROM pos
)
SELECT stock_status,
       count(*)                                                          AS products,
       sum(stock)                                                        AS units_on_hand,
       round(sum(stock * unit_cost), 0)                                  AS stock_value_at_cost,
       round(100 * sum(stock * unit_cost) / sum(sum(stock * unit_cost)) OVER (), 1) AS pct_of_stock_value
FROM c
GROUP BY 1
ORDER BY array_position(ARRAY['CRITICAL','HIGH RISK','DEAD STOCK','OVERSTOCK','HEALTHY','INACTIVE'], stock_status);

-- Q08.3 | Which products lost the most sales to stockouts in 2025?
WITH d AS (
    SELECT i.product_id, i.snapshot_date, i.stock_on_hand, i.units_sold,
           (i.stock_on_hand = 0 AND i.units_sold = 0) AS out_of_stock
    FROM clean.inventory_daily i
    WHERE i.snapshot_date >= '2025-01-01'
),
islands AS (
    -- gaps and islands: consecutive out-of-stock days share the same grp
    SELECT *, snapshot_date - (row_number() OVER (PARTITION BY product_id, out_of_stock ORDER BY snapshot_date))::int AS grp
    FROM d
),
episodes AS (
    SELECT product_id, count(*) AS days
    FROM islands WHERE out_of_stock
    GROUP BY product_id, grp
),
demand AS (
    SELECT product_id,
           sum(units_sold)::numeric / NULLIF(count(*) FILTER (WHERE NOT out_of_stock), 0) AS daily_demand,
           count(*) FILTER (WHERE out_of_stock) AS stockout_days,
           count(*) AS active_days
    FROM d GROUP BY 1
),
price AS (
    SELECT product_id, sum(net_revenue) / sum(quantity) AS net_price
    FROM clean.sales_lines WHERE order_date >= '2025-01-01' GROUP BY 1
)
SELECT p.product_name, p.category,
       m.stockout_days,
       round(100.0 * m.stockout_days / m.active_days, 1)               AS stockout_rate_pct,
       (SELECT count(*) FROM episodes e WHERE e.product_id = p.product_id) AS stockout_episodes,
       (SELECT max(days) FROM episodes e WHERE e.product_id = p.product_id) AS longest_episode_days,
       round(m.daily_demand, 2)                                        AS daily_demand_when_in_stock,
       round(m.stockout_days * m.daily_demand)                         AS est_lost_units,
       round(m.stockout_days * m.daily_demand * pr.net_price, 0)       AS est_lost_revenue,
       -- A months-long gap usually means the SKU was delisted, not that
       -- demand went unserved: check before counting it as lost sales.
       CASE WHEN (SELECT max(days) FROM episodes e WHERE e.product_id = p.product_id) > 90
            THEN 'Verify: out of stock >90 days in a row - delisted?' ELSE 'Repeated stockouts' END AS note
FROM demand m
JOIN clean.products p USING (product_id)
JOIN price pr USING (product_id)
WHERE m.stockout_days > 0
ORDER BY est_lost_revenue DESC
LIMIT 20;

-- Q08.4 | How much revenue do A-class products with repeated stockouts represent?
WITH abc AS (
    SELECT product_id, rev,
           CASE WHEN sum(rev) OVER (ORDER BY rev DESC, product_id) - rev < 0.80 * sum(rev) OVER () THEN 'A'
                WHEN sum(rev) OVER (ORDER BY rev DESC, product_id) - rev < 0.95 * sum(rev) OVER () THEN 'B'
                ELSE 'C' END AS abc_class,
           rev / sum(rev) OVER () AS rev_share
    FROM (SELECT product_id, sum(net_revenue) AS rev FROM clean.sales_lines
          WHERE order_date >= '2025-01-01' GROUP BY 1) r
),
d AS (
    SELECT product_id, snapshot_date, (stock_on_hand = 0 AND units_sold = 0) AS oos, units_sold
    FROM clean.inventory_daily WHERE snapshot_date >= '2025-01-01'
),
ep AS (
    SELECT product_id, count(DISTINCT grp) AS episodes, count(*) AS stockout_days
    FROM (SELECT product_id, snapshot_date - (row_number() OVER (PARTITION BY product_id ORDER BY snapshot_date))::int AS grp
          FROM d WHERE oos) x
    GROUP BY 1
),
price AS (
    SELECT product_id, sum(net_revenue) / sum(quantity) AS net_price
    FROM clean.sales_lines WHERE order_date >= '2025-01-01' GROUP BY 1
),
lost AS (
    -- stockout days x demand on in-stock days x average net price
    SELECT d.product_id,
           count(*) FILTER (WHERE d.oos) * sum(d.units_sold)::numeric
             / NULLIF(count(*) FILTER (WHERE NOT d.oos), 0) * max(pr.net_price) AS lost_revenue
    FROM d JOIN price pr USING (product_id)
    GROUP BY d.product_id
)
SELECT abc.abc_class,
       count(*)                                                           AS products,
       count(*) FILTER (WHERE ep.episodes >= 3)                           AS with_3plus_stockout_episodes,
       round(100 * sum(abc.rev_share) FILTER (WHERE ep.episodes >= 3), 1) AS their_share_of_2025_revenue_pct,
       round(sum(lost.lost_revenue) FILTER (WHERE ep.episodes >= 3), 0)   AS their_est_lost_revenue,
       round(avg(ep.stockout_days) FILTER (WHERE ep.episodes >= 3), 0)    AS their_avg_stockout_days
FROM abc
LEFT JOIN ep USING (product_id)
LEFT JOIN lost USING (product_id)
GROUP BY abc.abc_class
ORDER BY abc.abc_class;

-- Q08.5 | Inventory turnover and days of inventory by category (2025).
WITH cogs AS (
    SELECT category, sum(cogs) AS cogs
    FROM clean.sales_lines WHERE order_date >= '2025-01-01' GROUP BY 1
),
inv AS (
    SELECT p.category, avg(daily_value) AS avg_inventory_value
    FROM (SELECT i.snapshot_date, p.category, sum(i.stock_on_hand * p.unit_cost) AS daily_value
          FROM clean.inventory_daily i JOIN clean.products p USING (product_id)
          WHERE i.snapshot_date >= '2025-01-01'
          GROUP BY 1, 2) x
    JOIN (SELECT DISTINCT category FROM clean.products) p USING (category)
    GROUP BY 1
)
SELECT category,
       round(cogs, 0)                              AS cogs_2025,
       round(avg_inventory_value, 0)               AS avg_inventory_value,
       round(cogs / avg_inventory_value, 1)        AS inventory_turnover,
       round(365 / (cogs / avg_inventory_value), 0) AS days_of_inventory
FROM cogs JOIN inv USING (category)
ORDER BY inventory_turnover;

-- Q08.6 | Investigation: did the two collapsing best-sellers lose demand, or stock?
-- Monthly revenue next to days out of stock for A-class products whose
-- revenue fell by more than 30% from H1 to H2 2025.
WITH h AS (
    SELECT product_id,
           sum(net_revenue) FILTER (WHERE order_date BETWEEN '2025-01-01' AND '2025-06-30') AS h1,
           sum(net_revenue) FILTER (WHERE order_date BETWEEN '2025-07-01' AND '2025-12-31') AS h2
    FROM clean.sales_lines GROUP BY 1
),
fallers AS (
    SELECT product_id FROM h WHERE h1 > 100000 AND h2 < 0.7 * h1
)
SELECT p.product_name,
       date_trunc('month', i.snapshot_date)::date                                   AS month,
       sum(i.units_sold)                                                            AS units_sold,
       count(*) FILTER (WHERE i.stock_on_hand = 0 AND i.units_sold = 0)             AS days_out_of_stock,
       round(avg(i.stock_on_hand), 0)                                               AS avg_stock_on_hand
FROM clean.inventory_daily i
JOIN fallers f USING (product_id)
JOIN clean.products p USING (product_id)
WHERE i.snapshot_date >= '2025-01-01'
GROUP BY p.product_name, 2
ORDER BY p.product_name, 2;
