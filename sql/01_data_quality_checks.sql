-- =============================================================================
-- 01_data_quality_checks.sql
-- Business question: can we trust the export enough to report on it, and
-- what has to be fixed first?
--
-- Runs against raw.* (everything is TEXT). Each check counts transaction
-- records (order lines) unless stated otherwise. Checks after Q01.2 run on
-- the de-duplicated data so one defect is never counted twice.
-- clean.py applies the decisions; its log (clean.data_quality_log) must
-- reproduce these counts.
-- =============================================================================

-- Q01.1 | How much raw data did we receive?
SELECT 'raw.transactions' AS table_name, count(*) AS records FROM raw.transactions
UNION ALL SELECT 'raw.customers', count(*) FROM raw.customers
UNION ALL SELECT 'raw.products', count(*) FROM raw.products
UNION ALL SELECT 'raw.inventory', count(*) FROM raw.inventory;

-- Q01.2 | How many transaction records were delivered more than once?
SELECT count(*) - count(DISTINCT transaction_id) AS duplicate_records,
       count(DISTINCT transaction_id) AS unique_records
FROM raw.transactions;

-- Q01.3 | Which date formats does the order_date column contain?
WITH tx AS (SELECT DISTINCT ON (transaction_id) * FROM raw.transactions ORDER BY transaction_id)
SELECT CASE
         WHEN order_date ~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$' THEN 'YYYY-MM-DD HH:MM:SS (ISO)'
         WHEN order_date ~ '^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$'       THEN 'DD/MM/YYYY HH:MM'
         WHEN order_date ~ '^\d{4}/\d{2}/\d{2}$'                    THEN 'YYYY/MM/DD (no time)'
         WHEN order_date ~ '^\d{2}-[A-Za-z]{3}-\d{4}$'              THEN 'DD-Mon-YYYY (no time)'
         ELSE 'unrecognised'
       END AS date_format,
       count(*) AS records,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
FROM tx
GROUP BY 1
ORDER BY records DESC;

-- Q01.4 | Which country spellings are not in the standard list?
WITH tx AS (SELECT DISTINCT ON (transaction_id) * FROM raw.transactions ORDER BY transaction_id)
SELECT customer_country AS raw_value, count(*) AS records
FROM tx
WHERE customer_country NOT IN ('Greece','Cyprus','Germany','Italy','France','Netherlands','Spain','Bulgaria')
GROUP BY 1
ORDER BY records DESC;

-- Q01.5 | Which order_status values are used, and how often?
WITH tx AS (SELECT DISTINCT ON (transaction_id) * FROM raw.transactions ORDER BY transaction_id)
SELECT order_status, count(*) AS records
FROM tx
GROUP BY 1
ORDER BY records DESC;

-- Q01.6 | Are prices plausible compared with the product's list price?
WITH tx AS (SELECT DISTINCT ON (transaction_id) * FROM raw.transactions ORDER BY transaction_id)
SELECT CASE
         WHEN t.unit_price::numeric = 0 THEN 'zero price'
         WHEN t.unit_price::numeric < 0 THEN 'negative price'
         WHEN t.unit_price::numeric > 5 * p.list_price::numeric THEN 'more than 5x list price (entered in cents?)'
       END AS problem,
       count(*) AS records,
       round(avg(t.unit_price::numeric / p.list_price::numeric), 1) AS avg_ratio_to_list
FROM tx t
JOIN raw.products p USING (product_id)
WHERE t.unit_price::numeric <= 0 OR t.unit_price::numeric > 5 * p.list_price::numeric
GROUP BY 1;

-- Q01.7 | Do negative quantities mirror an existing sale (legacy return adjustments)?
WITH tx AS (SELECT DISTINCT ON (transaction_id) * FROM raw.transactions ORDER BY transaction_id),
neg AS (SELECT * FROM tx WHERE quantity::int < 0)
SELECT count(*) AS negative_records,
       count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM tx s
           WHERE s.order_id = neg.order_id AND s.product_id = neg.product_id
             AND s.quantity::int = -neg.quantity::int)) AS matching_original_sale,
       count(DISTINCT order_id) AS orders_affected
FROM neg;

-- Q01.8 | How large are the quantity outliers (median, P99, max)?
WITH tx AS (SELECT DISTINCT ON (transaction_id) * FROM raw.transactions ORDER BY transaction_id)
SELECT percentile_cont(0.5)  WITHIN GROUP (ORDER BY quantity::int) AS median_qty,
       percentile_cont(0.99) WITHIN GROUP (ORDER BY quantity::int) AS p99_qty,
       max(quantity::int) AS max_qty,
       count(*) FILTER (WHERE quantity::int >= 40) AS records_qty_40_plus,
       count(DISTINCT order_id) FILTER (WHERE quantity::int >= 40) AS orders_qty_40_plus
FROM tx
WHERE quantity::int > 0;

-- Q01.9 | Inventory snapshots: duplicated uploads and impossible stock counts.
SELECT
  (SELECT count(*) - count(DISTINCT (product_id, snapshot_date)) FROM raw.inventory) AS duplicate_snapshots,
  (SELECT count(*) FROM (SELECT DISTINCT * FROM raw.inventory) i WHERE stock_on_hand::int < 0) AS negative_stock_rows,
  (SELECT count(DISTINCT product_id) FROM raw.inventory WHERE stock_on_hand::int < 0) AS products_affected;

-- Q01.10 | Data-quality summary: one row per check (records affected and decision).
WITH tx AS (SELECT DISTINCT ON (transaction_id) * FROM raw.transactions ORDER BY transaction_id),
std AS (
  SELECT t.*, p.list_price::numeric AS list_price
  FROM tx t JOIN raw.products p USING (product_id)
),
-- Checks 4+ describe the records that survive the three removal rules,
-- in the same order clean.py applies them.
valid AS (
  SELECT * FROM std
  WHERE quantity::int > 0 AND unit_price::numeric > 0 AND unit_price::numeric <= 5 * list_price
)
SELECT check_name, records, action FROM (
  SELECT 1 AS n, 'Duplicate transaction records' AS check_name,
         (SELECT count(*) - count(DISTINCT transaction_id) FROM raw.transactions) AS records,
         'Removed (kept first copy)' AS action
  UNION ALL SELECT 2, 'Negative quantity (legacy return adjustments)',
         count(*) FILTER (WHERE quantity::int < 0), 'Investigated, excluded (refund already on the order)' FROM std
  UNION ALL SELECT 3, 'Invalid unit price (zero, negative or >5x list)',
         count(*) FILTER (WHERE quantity::int > 0 AND (unit_price::numeric <= 0 OR unit_price::numeric > 5 * list_price)),
         'Excluded' FROM std
  UNION ALL SELECT 4, 'Missing customer ID (guest checkout)',
         count(*) FILTER (WHERE customer_id IS NULL), 'Retained as guest; excluded from customer metrics' FROM valid
  UNION ALL SELECT 5, 'Missing category',
         count(*) FILTER (WHERE category IS NULL), 'Mapped from product master' FROM valid
  UNION ALL SELECT 6, 'Missing payment method',
         count(*) FILTER (WHERE payment_method IS NULL), 'Classified as Unknown' FROM valid
  UNION ALL SELECT 7, 'Non-standard country name',
         count(*) FILTER (WHERE customer_country NOT IN ('Greece','Cyprus','Germany','Italy','France','Netherlands','Spain','Bulgaria')),
         'Standardised to English country name' FROM valid
  UNION ALL SELECT 8, 'Non-ISO date format',
         count(*) FILTER (WHERE order_date !~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'), 'Parsed with explicit format rules' FROM valid
  UNION ALL SELECT 9, 'Non-standard order status spelling',
         count(*) FILTER (WHERE order_status NOT IN ('completed','cancelled','refunded')), 'Normalised' FROM valid
  UNION ALL SELECT 10, 'Cancelled order lines',
         count(*) FILTER (WHERE lower(order_status) LIKE 'cancel%'), 'Kept for cancellation KPIs, excluded from revenue' FROM valid
  UNION ALL SELECT 11, 'Refunded order lines',
         count(*) FILTER (WHERE lower(order_status) = 'refunded'), 'Kept; refund deducted in Net Revenue' FROM valid
  UNION ALL SELECT 12, 'Quantity outliers (>= 40 units)',
         count(*) FILTER (WHERE quantity::int >= 40), 'Retained (verified bulk orders), flagged is_bulk' FROM valid
  UNION ALL SELECT 13, 'Duplicate inventory snapshots',
         (SELECT count(*) - count(DISTINCT (product_id, snapshot_date)) FROM raw.inventory), 'Removed'
  UNION ALL SELECT 14, 'Negative stock on hand',
         (SELECT count(*) FROM (SELECT DISTINCT * FROM raw.inventory) i WHERE stock_on_hand::int < 0), 'Set to 0, flagged stock_corrected'
  UNION ALL SELECT 15, 'Non-standard country name (customer master)',
         (SELECT count(*) FROM raw.customers
          WHERE country NOT IN ('Greece','Cyprus','Germany','Italy','France','Netherlands','Spain','Bulgaria')),
         'Standardised to English country name'
) s
ORDER BY n;

-- Q01.11 | How many transaction records have at least one defect (counted once)?
WITH t AS (
    SELECT r.*, p.list_price::numeric AS list_price,
           row_number() OVER (PARTITION BY transaction_id) AS copy_no
    FROM raw.transactions r JOIN raw.products p USING (product_id)
)
SELECT count(*)                                                                  AS raw_records,
       count(*) FILTER (WHERE
            copy_no > 1
         OR quantity::int < 0
         OR unit_price::numeric <= 0 OR unit_price::numeric > 5 * list_price
         OR customer_id IS NULL OR category IS NULL OR payment_method IS NULL
         OR customer_country NOT IN ('Greece','Cyprus','Germany','Italy','France','Netherlands','Spain','Bulgaria')
         OR order_date !~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'
         OR order_status NOT IN ('completed','cancelled','refunded'))           AS records_with_a_defect,
       count(*) FILTER (WHERE copy_no > 1 OR quantity::int < 0
         OR unit_price::numeric <= 0 OR unit_price::numeric > 5 * list_price)    AS records_removed,
       round(100.0 * count(*) FILTER (WHERE
            copy_no > 1
         OR quantity::int < 0
         OR unit_price::numeric <= 0 OR unit_price::numeric > 5 * list_price
         OR customer_id IS NULL OR category IS NULL OR payment_method IS NULL
         OR customer_country NOT IN ('Greece','Cyprus','Germany','Italy','France','Netherlands','Spain','Bulgaria')
         OR order_date !~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'
         OR order_status NOT IN ('completed','cancelled','refunded'))
         / count(*), 1)                                                          AS pct_with_a_defect
FROM t;
