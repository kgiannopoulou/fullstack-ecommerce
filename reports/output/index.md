# Query results

Every business question in `sql/`, with its answer saved as CSV in this folder.
Regenerate with `python src/run_sql.py`.


## [01_data_quality_checks.sql](../../sql/01_data_quality_checks.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q01.1](Q01.1.csv) | How much raw data did we receive? | 4 |
| [Q01.2](Q01.2.csv) | How many transaction records were delivered more than once? | 1 |
| [Q01.3](Q01.3.csv) | Which date formats does the order_date column contain? | 4 |
| [Q01.4](Q01.4.csv) | Which country spellings are not in the standard list? | 25 |
| [Q01.5](Q01.5.csv) | Which order_status values are used, and how often? | 9 |
| [Q01.6](Q01.6.csv) | Are prices plausible compared with the product's list price? | 3 |
| [Q01.7](Q01.7.csv) | Do negative quantities mirror an existing sale (legacy return adjustments)? | 1 |
| [Q01.8](Q01.8.csv) | How large are the quantity outliers (median, P99, max)? | 1 |
| [Q01.9](Q01.9.csv) | Inventory snapshots: duplicated uploads and impossible stock counts. | 1 |
| [Q01.10](Q01.10.csv) | Data-quality summary: one row per check (records affected and decision). | 16 |
| [Q01.11](Q01.11.csv) | How many transaction records have at least one defect (counted once)? | 1 |

## [02_sales_kpis.sql](../../sql/02_sales_kpis.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q02.1](Q02.1.csv) | What are the headline KPIs for each year and for the whole period? | 3 |
| [Q02.2](Q02.2.csv) | Are we actually growing? Every headline KPI, 2025 vs 2024. | 7 |
| [Q02.3](Q02.3.csv) | How much do bulk (B2B-size) orders distort the average order value? | 3 |
| [Q02.4](Q02.4.csv) | Which payment methods lose the most orders to cancellation? | 6 |
| [Q02.5](Q02.5.csv) | How does each market perform? | 8 |

## [03_revenue_trends.sql](../../sql/03_revenue_trends.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q03.1](Q03.1.csv) | Monthly revenue with month-over-month and year-over-year growth. | 24 |
| [Q03.2](Q03.2.csv) | Quarterly revenue, quarter-over-quarter and year-over-year. | 8 |
| [Q03.3](Q03.3.csv) | Weekly revenue and its 4-week moving average. | 105 |
| [Q03.4](Q03.4.csv) | Daily revenue with rolling 30-day and 90-day totals (calendar filled, no gaps). | 731 |
| [Q03.5](Q03.5.csv) | Rolling 90-day revenue at each year-end: underlying growth without seasonality noise. | 4 |
| [Q03.6](Q03.6.csv) | Which ten days earned the most, and what drove them? | 10 |
| [Q03.7](Q03.7.csv) | Which weekdays sell most (average per day)? | 7 |
| [Q03.8](Q03.8.csv) | Why did AOV fall while revenue grew? Price, basket size or product mix? | 2 |

## [04_product_performance.sql](../../sql/04_product_performance.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q04.1](Q04.1.csv) | How does each category perform, and which are growing? | 12 |
| [Q04.2](Q04.2.csv) | Which 20 products earn the most, and how concentrated is revenue? | 20 |
| [Q04.3](Q04.3.csv) | ABC analysis: what share of SKUs produces 80% of revenue? | 3 |
| [Q04.4](Q04.4.csv) | Which products had declining sales for three consecutive months in 2025? | 5 |
| [Q04.5](Q04.5.csv) | Which products grew fastest, and which collapsed (H2 2025 vs H2 2024, min EUR 5k base)? | 20 |
| [Q04.6](Q04.6.csv) | Which products are refunded unusually often (min 100 orders)? | 15 |
| [Q04.7](Q04.7.csv) | Where does the margin come from? Revenue vs gross profit (after COGS and shipping) by category. | 12 |

## [05_customer_analysis.sql](../../sql/05_customer_analysis.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q05.1](Q05.1.csv) | How large is the customer base and how often do customers come back? | 1 |
| [Q05.2](Q05.2.csv) | Each month: how much revenue comes from new vs returning customers? | 24 |
| [Q05.3](Q05.3.csv) | How many orders do customers place over their lifetime? | 5 |
| [Q05.4](Q05.4.csv) | How long does it take to win the second order? | 5 |
| [Q05.5](Q05.5.csv) | Which acquisition channels bring customers who come back? | 6 |
| [Q05.6](Q05.6.csv) | Does repeat purchasing differ by market? | 8 |
| [Q05.7](Q05.7.csv) | Does a late first delivery reduce the chance of a second order? | 2 |

## [06_rfm_segmentation.sql](../../sql/06_rfm_segmentation.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q06.1](Q06.1.csv) | How do RFM segments compare in size, value and recency? | 10 |
| [Q06.2](Q06.2.csv) | Which segments over-index on value? (revenue share / customer share) | 10 |
| [Q06.3](Q06.3.csv) | Win-back list: the 25 most valuable customers who have gone quiet. | 25 |

## [07_cohort_retention.sql](../../sql/07_cohort_retention.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q07.1](Q07.1.csv) | Cohort retention matrix (Month 1 - Month 12). | 23 |
| [Q07.2](Q07.2.csv) | Observation: did 90-day repeat purchasing improve year over year? | 9 |
| [Q07.3](Q07.3.csv) | Investigation: was it the loyalty programme or faster delivery? | 6 |
| [Q07.4](Q07.4.csv) | Explanation: how did the share of late first deliveries change by quarter? | 8 |
| [Q07.5](Q07.5.csv) | How much of the improvement does each change explain? (decomposition) | 1 |

## [08_inventory_analysis.sql](../../sql/08_inventory_analysis.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q08.1](Q08.1.csv) | Stock position and recommended action for every active product. | 363 |
| [Q08.2](Q08.2.csv) | How many products (and how much stock value) sit in each risk class? | 6 |
| [Q08.3](Q08.3.csv) | Which products lost the most sales to stockouts in 2025? | 20 |
| [Q08.4](Q08.4.csv) | How much revenue do A-class products with repeated stockouts represent? | 3 |
| [Q08.5](Q08.5.csv) | Inventory turnover and days of inventory by category (2025). | 12 |
| [Q08.6](Q08.6.csv) | Investigation: did the two collapsing best-sellers lose demand, or stock? | 24 |

## [09_operations_analysis.sql](../../sql/09_operations_analysis.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q09.1](Q09.1.csv) | How long does fulfilment take, month by month? | 24 |
| [Q09.2](Q09.2.csv) | Did the courier switch (15 May 2025) improve on-time delivery, and where? | 9 |
| [Q09.3](Q09.3.csv) | Are late deliveries refunded more often? | 2 |
| [Q09.4](Q09.4.csv) | Does a weekend order wait longer to ship? | 7 |
| [Q09.5](Q09.5.csv) | When do orders arrive? (staffing the warehouse and customer service) | 24 |
| [Q09.6](Q09.6.csv) | How is the payment mix shifting, and what does COD cost us in cancellations? | 8 |

## [10_anomaly_investigation.sql](../../sql/10_anomaly_investigation.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q10.1](Q10.1.csv) | Which days were statistical outliers (|z| > 3 against the same weekday's last 8 weeks)? | 30 |
| [Q10.2](Q10.2.csv) | What explains the biggest spikes? Order volume, discount share and AOV vs a normal day. | 5 |
| [Q10.3](Q10.3.csv) | Which products' sales fell sharply while still in stock (last 12 weeks vs prior 12)? | 4 |
| [Q10.4](Q10.4.csv) | Were there weeks with unusually many refunds? | 1 |
| [Q10.5](Q10.5.csv) | Bulk orders: who places them and are they legitimate? | 20 |
| [Q10.6](Q10.6.csv) | Re-check the alert: Wearables daily revenue vs the same weekday over the previous 8 weeks. | 29 |
| [Q10.7](Q10.7.csv) | Which Wearables products explain the drop? Revenue 4 weeks before vs 4 weeks after 1 Jan 2025. | 8 |
| [Q10.8](Q10.8.csv) | The top SKU's stock story: when did it run out, and was anything reordered? | 1 |

## [11_reporting_views.sql](../../sql/11_reporting_views.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q11.1](Q11.1.csv) | Do the reporting views reconcile with the source tables? | 6 |
| [Q11.2](Q11.2.csv) | Monthly KPI table that feeds the dashboard's first page. | 24 |
| [Q11.3](Q11.3.csv) | Inventory status table that feeds the operations page. | 16 |

## [12_profitability.sql](../../sql/12_profitability.sql)

| ID | Question | Rows |
|---|---|---:|
| [Q12.1](Q12.1.csv) | Revenue-to-profit bridge: where does each euro of list-price sales go? | 3 |
| [Q12.2](Q12.2.csv) | Quarterly gross margin and what moved it (each component as % of net revenue). | 8 |
| [Q12.3](Q12.3.csv) | Category profitability in 2025: revenue rank vs gross-profit rank. | 12 |
| [Q12.4](Q12.4.csv) | Products whose revenue rank overstates their contribution (2025, top 50 by revenue). | 16 |
| [Q12.5](Q12.5.csv) | Revenue vs margin quadrant for every active product in 2025 (feeds the scatter plot). | 361 |
| [Q12.6](Q12.6.csv) | How much revenue and profit sits in each quadrant? | 4 |
| [Q12.7](Q12.7.csv) | Which products lose money on every sale (2025)? | 5 |
| [Q12.8](Q12.8.csv) | What does each discount level cost? (fulfilled orders, bulk excluded) | 5 |
| [Q12.9](Q12.9.csv) | The courier switch in Greece: what did faster delivery cost per order? | 2 |
| [Q12.10](Q12.10.csv) | Margin by market: does selling abroad pay once shipping is counted? | 8 |
