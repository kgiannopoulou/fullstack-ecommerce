# KPI Dictionary

One definition per metric, used by every SQL file, the Excel report and the Power BI measures.
Revenue is defined once in the views `clean.order_summary` and `clean.sales_lines`
([`sql/00_schema.sql`](../sql/00_schema.sql)) so no query can define it differently.

**Order states.** *Placed* = every order. *Fulfilled* = `completed` or `refunded` (the goods were shipped).
*Cancelled* = never shipped, never paid. *Registered customer* = order has a `customer_id` (guest checkouts excluded).

## Sales

| KPI | Definition | Formula | Where |
|---|---|---|---|
| **Gross Revenue** | Value of goods sold at the price paid, before discounts and refunds | Σ quantity × unit price, fulfilled orders | `Q02.1` |
| **Discounts** | Promo-code reductions | Σ gross amount × discount %, fulfilled orders | `Q02.1` |
| **Refunds** | Money returned to customers (full or partial) | Σ refund amount | `Q02.1` |
| **Net Revenue** | The revenue figure used everywhere in this project | Gross Revenue − Discounts − Refunds (cancelled orders contribute 0) | all |
| **Orders (fulfilled)** | Orders that were shipped | count of orders with status completed or refunded | `Q02.1` |
| **Units Sold** | | Σ quantity, fulfilled orders | `Q02.1` |
| **Average Order Value (AOV)** | Net revenue per fulfilled order | Net Revenue ÷ Fulfilled Orders | `Q02.1`, `Q03.1` |
| **Median Order Value** | Typical order, robust to bulk orders | 50th percentile of order net revenue | `Q02.3` |
| **Average Selling Price** | Net revenue per unit | Net Revenue ÷ Units Sold | `Q04.1` |
| **Gross Margin %** | Share of net revenue left after the cost of goods | (Net Revenue − COGS) ÷ Net Revenue × 100 | `Q02.1`, `Q04.7` |
| **COGS** | Cost of goods sold | Σ quantity × unit cost, fulfilled orders | `Q04.7`, `Q08.5` |
| **Revenue Share** | A product's or category's part of the total | Item Net Revenue ÷ Total Net Revenue × 100 | `Q04.1`, `Q04.2` |
| **Refund Rate** | Share of shipped orders that were (partly) refunded | Refunded Orders ÷ Fulfilled Orders × 100 | `Q02.1` |
| **Refund Value %** | Share of sold value that was paid back | Refunds ÷ (Gross − Discounts) × 100 | `Q04.1` |
| **Cancellation Rate** | Share of placed orders that were cancelled | Cancelled Orders ÷ Orders Placed × 100 | `Q02.1`, `Q02.4` |

## Growth

| KPI | Formula | Where |
|---|---|---|
| **Month-over-Month Growth %** | (Revenue this month − Revenue last month) ÷ Revenue last month × 100 | `Q03.1` |
| **Year-over-Year Growth %** | (Revenue this period − same period last year) ÷ same period last year × 100 | `Q02.2`, `Q03.1`, `Q03.2` |
| **Quarter-over-Quarter Growth %** | as MoM, by calendar quarter | `Q03.2` |
| **Rolling 30 / 90-day Revenue** | Σ Net Revenue over the last 30 / 90 calendar days (days without orders count as 0) | `Q03.4`, `Q03.5` |

MoM growth mostly measures seasonality (December vs November). Use YoY or rolling 90-day growth to judge whether the business is growing.

## Customers

| KPI | Definition | Formula | Where |
|---|---|---|---|
| **Active Customers** | Registered customers with ≥ 1 fulfilled order in the period | count distinct customer_id | `Q02.1` |
| **New Customer** | Customer whose first-ever fulfilled order falls in the period | | `Q05.2` |
| **Returning Customer** | Customer ordering in the period after their first-order date | | `Q05.2` |
| **Repeat Customer Rate** | | Customers with > 1 fulfilled order ÷ Customers with ≥ 1 fulfilled order × 100 | `Q05.1` |
| **90-day Repeat Rate** | Share of first-time buyers who order again within 90 days (only cohorts with 90 days of data) | First buyers with a 2nd order ≤ 90 days later ÷ First buyers × 100 | `Q07.2`, `Q07.3` |
| **Orders per Customer** | | Fulfilled Orders ÷ Customers | `Q05.1` |
| **Revenue per Customer** | Historical (not predicted) customer value | Net Revenue ÷ Customers | `Q05.1` |
| **Days Between Purchases** | Gap between consecutive orders of the same customer | mean / median of order_date − previous order_date | `Q05.1` |
| **Cohort** | Customers grouped by the month of their first fulfilled order | | `Q07.1` |
| **Month-N Retention** | | Cohort customers ordering in calendar month N after the cohort month ÷ Cohort size × 100 | `Q07.1` |

### RFM segmentation (`Q06.1`)

Scored as of 2026-01-01, registered customers with ≥ 1 fulfilled order.

| Score | Recency (R) | Frequency (F) |
|---|---|---|
| 5 | most recent 20% | 5+ orders |
| 4 | next 20% | 4 orders |
| 3 | middle 20% | 3 orders |
| 2 | next 20% | 2 orders |
| 1 | least recent 20% | 1 order |

Frequency uses fixed bands because 66% of customers have exactly one order, so quintiles would be ties.

| Segment | Rule | Segment | Rule |
|---|---|---|---|
| Champions | R ≥ 4, F ≥ 4 | Need Attention | R = 3, F ≤ 2 |
| Loyal | R ≥ 3, F ≥ 3 | Cannot Lose Them | R ≤ 2, F ≥ 3 |
| Potential Loyalists | R ≥ 4, F = 2 | At Risk | R ≤ 2, F = 2 |
| New Customers | R = 5, F = 1 | Hibernating | R = 2, F = 1 |
| Promising | R = 4, F = 1 | Lost | R = 1, F = 1 |

**Value Index** = segment share of revenue ÷ segment share of customers (> 1 means the segment is worth more than its size, `Q06.2`).

## Products

| KPI | Definition | Where |
|---|---|---|
| **ABC Class** | Products ranked by net revenue. **A** = products whose revenue starts before 80% cumulative share, **B** = up to 95%, **C** = the rest | `Q04.3` |
| **3-month decline** | Monthly revenue lower than the previous month for three consecutive months | `Q04.4` |

## Inventory

| KPI | Definition | Formula | Where |
|---|---|---|---|
| **In-stock day** | Stock at end of day > 0, or units sold that day | | `Q08.*` |
| **Average Daily Demand** | Demand when the product could actually be bought | Units sold in the last 90 days ÷ in-stock days in the last 90 days | `Q08.1` |
| **Days of Cover** | How long current stock lasts | Stock on hand ÷ Average Daily Demand | `Q08.1` |
| **Stockout Rate** | | Days out of stock ÷ Days the SKU was active × 100 | `Q08.3` |
| **Stockout Episode** | A run of consecutive out-of-stock days (gaps-and-islands) | | `Q08.3`, `Q08.4` |
| **Estimated Lost Sales** | Upper bound: assumes no substitution | Stockout days × Demand on in-stock days × Average net price | `Q08.3`, `Q08.4` |
| **Inventory Turnover** | How many times stock is sold through per year | COGS ÷ Average inventory value at cost | `Q08.5` |
| **Days of Inventory** | | 365 ÷ Inventory Turnover | `Q08.5` |
| **Stock status** | **CRITICAL** cover < supplier lead time · **HIGH RISK** cover < lead time + 7 days · **OVERSTOCK** cover > 120 days · **DEAD STOCK** stock > 0 and no sales in 90 days · **HEALTHY** otherwise | | `Q08.1`, `Q08.2` |

## Operations

| KPI | Formula | Where |
|---|---|---|
| **Days to Ship** | ship_date − order_date | `Q09.1` |
| **Days to Deliver** | delivery_date − order_date | `Q09.1` |
| **On-time Delivery %** | Orders delivered within the promise (4 days Greece, 7 days abroad) ÷ Fulfilled Orders × 100 | `Q09.1`, `Q09.2` |
| **Late Order** | Days to Deliver > promise | `clean.order_summary.is_late` |
