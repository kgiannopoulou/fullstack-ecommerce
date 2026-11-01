# Data Dictionary

Three layers in PostgreSQL ([`sql/00_schema.sql`](../sql/00_schema.sql), [`sql/11_reporting_views.sql`](../sql/11_reporting_views.sql)),
and the CSV exports that Power BI and Excel read ([`data/cleaned/`](../data), samples committed in [`data/sample/`](../data/sample)).
KPI definitions are in [kpi_dictionary.md](kpi_dictionary.md).

| Layer | Purpose |
|---|---|
| `raw.*` | The legacy export exactly as received. Every column is `TEXT`; nothing is trusted or fixed. |
| `clean.*` | Typed, de-duplicated, standardised data written by [`src/clean.py`](../src/clean.py), plus a log of every data-quality decision. |
| `reporting.*` | Star schema views for Excel and Power BI. Same definitions as the SQL analysis. |

## Source export (`raw`)

| Table | Grain | Notes |
|---|---|---|
| `raw.transactions` | one row per order line, order attributes repeated | 340,795 records incl. duplicates, return adjustments, 4 date formats, misspelt countries, missing values |
| `raw.products` | one row per SKU | product master: price, unit cost, supplier lead time, parcel size |
| `raw.customers` | one row per registered customer | sign-up date, country, acquisition channel |
| `raw.inventory` | one row per SKU per day | stock on hand, units received, units sold; duplicate uploads and negative counts |

## Clean warehouse (`clean`)

### `clean.orders` — one row per order

| Column | Type | Description |
|---|---|---|
| `order_id` | integer, PK | |
| `customer_id` | integer, FK, nullable | `NULL` = guest checkout (kept for sales KPIs, excluded from customer KPIs) |
| `is_guest` | boolean | |
| `order_ts`, `order_date` | timestamp, date | parsed from four source formats |
| `status` | text | `completed`, `refunded` or `cancelled` |
| `payment_method` | text | `Unknown` when the source lost it |
| `discount_pct` | numeric | promo code applied to the whole order (0, 0.10 … 0.25) |
| `channel` | text | acquisition channel of the customer |
| `country` | text | one of 8 standard English names |
| `courier`, `ship_date`, `delivery_date` | text, date | empty for cancelled orders |
| `refund_amount` | numeric | full or partial refund |
| `shipping_cost` | numeric | carrier cost paid by the shop; 0 if never shipped |
| `shipping_cost_imputed` | boolean | cost was missing in the export and imputed |

### `clean.order_items` — one row per order line

| Column | Description |
|---|---|
| `transaction_id` (PK), `order_id`, `product_id` | |
| `quantity`, `unit_price`, `unit_cost` | unit cost copied from the product master |
| `gross_amount` | quantity × unit price |
| `discount_amount` | gross × order discount % |
| `net_amount` | gross − discount (before refunds) |
| `is_bulk` | quantity ≥ 40 (genuine B2B order, kept and flagged) |

### Other clean tables

| Table | Key | Description |
|---|---|---|
| `clean.products` | `product_id` | SKU, name, category, list price, unit cost, launch date, supplier lead time, parcel size (S/M/L) |
| `clean.customers` | `customer_id` | sign-up date, country, acquisition channel |
| `clean.inventory_daily` | `product_id, snapshot_date` | stock on hand (≥ 0), units received, units sold, `stock_corrected` flag |
| `clean.data_quality_log` | `check_id` | every cleaning decision: records affected, action, rationale |

### Base views (one definition of revenue and profit)

| View | Grain | Adds |
|---|---|---|
| `clean.order_summary` | order | lines, units, gross, discount, net before refund, COGS, `net_revenue`, `gross_profit`, `is_fulfilled`, `is_late` |
| `clean.sales_lines` | fulfilled order line | refund and shipping allocated to the line, `net_revenue`, `cogs`, `gross_profit` |

## Reporting star schema (`reporting`, exported to `data/cleaned/`)

```
                     DimDate
                        |
   DimCustomer — FactSales / FactOrders — DimProduct
                        |
              DimChannel · DimGeography
```

| Table | Grain | Key columns | Measures / attributes |
|---|---|---|---|
| **FactSales** | fulfilled order line | `order_date`, `product_id`, `customer_id`, `channel_id`, `country` | quantity, gross, discount, refund, net revenue, COGS, shipping, gross profit; `customer_type` (New / Returning / Guest), `is_discounted`, `is_bulk` |
| **FactOrders** | order (incl. cancelled) | `order_date`, `customer_id`, `channel_id`, `country` | status, payment method, courier, units, revenue, profit, days to ship / deliver, `is_late`, `is_fulfilled` |
| **FactInventoryDaily** | product × day | `snapshot_date`, `product_id` | stock, received, sold, stock value at cost, `is_stockout`, estimated lost units / revenue |
| **DimDate** | day, 2024-2025 | `date` | year, quarter, month, month name, weekday, weekend flag (marked as date table) |
| **DimProduct** | SKU | `product_id` | SKU, name, category, prices, lead time, parcel size, ABC class |
| **DimCustomer** | customer | `customer_id` | country, channel, sign-up, first order, cohort month, orders, lifetime revenue, recency, R and F scores, RFM segment |
| **DimChannel** | acquisition channel | `channel_id` | channel, channel group (Paid / Owned-organic) |
| **DimGeography** | country | `country` | market (Domestic / EU export), delivery promise |

Analysis tables (no relationships, or to `DimProduct` only):

| Table | Written by | Description |
|---|---|---|
| `InventoryForecast` | `src/forecast.py` | stock vs 30-day forecast, days of cover, risk, reorder quantity, recommended action |
| `CohortRetention` | `reporting.cohort_retention` | cohort × months since first order × retention % |
| `ManagementAlerts` | `src/transform.py` | the 6 rule-based alerts on the executive page |
| `Anomalies` | `src/anomaly_detection.py` | every flagged day / week with expected value, deviation, z-score and known cause |
| `DataQualityRules`, `DataQualityScorecard` | `src/validate.py` | rule results and headline scores, raw vs clean |
| `SalesSummary`, `ProductPerformance`, `CustomerSegments`, `CustomerTypeMonthly`, `MonthlyKPIs` | `src/transform.py` | small aggregates for the Excel workbook |
