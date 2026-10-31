# E-Commerce Sales, Customer & Operations Analytics

**Tools:** SQL · PostgreSQL · Python · pandas · Excel · Power Query · Power BI · DAX · Git

[![CI](https://github.com/kgiannopoulou/fullstack-ecommerce/actions/workflows/ci.yml/badge.svg)](https://github.com/kgiannopoulou/fullstack-ecommerce/actions/workflows/ci.yml)

End-to-end data analytics project analysing **340,000+ simulated e-commerce transactions** to identify
revenue trends, customer retention patterns, product performance and inventory risks. Includes SQL
analysis, Python data cleaning and automation, statistical analysis, Excel reporting and an
interactive Power BI management dashboard model.

| | |
|---|---:|
| Raw dataset | **340,795** transaction records (Jan 2024 – Dec 2025) |
| Valid transactions after cleaning | **338,182** |
| Records with at least one data-quality defect | **161,918** (47.5%), only 2,613 of them removed |
| Business questions answered in SQL | **66** across 11 files |
| Orders · customers · products | 144,790 · 87,654 buyers · 371 SKUs |

**Start here:** [Findings & recommendations](reports/findings.md) ·
[Excel management report](reports/ecommerce_management_report.xlsx) ·
[Data quality report](docs/data_quality_report.md) · [KPI dictionary](docs/kpi_dictionary.md) ·
[All query results](reports/output/index.md)

---

## The assignment

The company has grown quickly. Its data sits in PostgreSQL, but there is no reliable reporting
process. The Head of Operations asks five questions:

1. **How is the business performing?**
2. **Which products and categories are driving or hurting revenue?**
3. **Are customers returning after their first purchase?**
4. **Which products are at risk of stockout or overstock?**
5. **What should management do next?**

Everything in this repository exists to answer one of them.

## What the analysis found

| Question | Finding | Evidence |
|---|---|---|
| Performance | Net revenue **+29.2%** (€9.64M → €12.46M). The growth is underlying (rolling 90-day revenue +26–28% YoY in both halves of 2025), not just Black Friday | [`Q02.2`](reports/output/Q02.2.csv), [`Q03.5`](reports/output/Q03.5.csv) |
| Performance | Average order value **−7.9%**, caused by **product mix**, not discounting: like-for-like prices rose 2.2%, while cheaper categories went from 10.9% to 14.5% of revenue | [`Q03.8`](reports/output/Q03.8.csv) |
| Products | **18.9% of SKUs produce 80.2% of revenue**. Two former best-sellers lost €678k between H2 2024 and H2 2025 *while in stock every day*, so this is lost demand, not a supply problem | [`Q04.3`](reports/output/Q04.3.csv), [`Q04.5`](reports/output/Q04.5.csv), [`Q08.6`](reports/output/Q08.6.csv) |
| Customers | 90-day repeat purchasing rose from **27.8% to ~41%** the month the loyalty programme launched. Decomposition: **+11.3 pp loyalty, +2.1 pp faster delivery** | [`Q07.2`](reports/output/Q07.2.csv), [`Q07.5`](reports/output/Q07.5.csv) |
| Customers | A late first delivery cuts the chance of a second order from 38.2% to 25.9% (odds ratio 1.77). At Risk + Cannot Lose Them customers are **10.4% of customers but 16.8% of revenue** | [tests](reports/statistical_tests.md), [`Q06.2`](reports/output/Q06.2.csv) |
| Inventory | **12 A-class products** had 3+ stockout episodes in 2025: 8.2% of revenue and ~€133k of estimated lost sales. **€158k** (19% of stock value) sits in 32 overstocked SKUs | [`Q08.4`](reports/output/Q08.4.csv), [`Q08.2`](reports/output/Q08.2.csv) |
| Operations | The courier switch raised on-time delivery in Greece from **36.6% to 67.9%**. Weekend orders wait a day longer to ship. Cash-on-delivery orders are cancelled **2.3×** as often | [`Q09.2`](reports/output/Q09.2.csv), [`Q09.4`](reports/output/Q09.4.csv), [`Q02.4`](reports/output/Q02.4.csv) |

The full write-up follows **observation → investigation → explanation → recommendation** for each
question and ends with a ranked action plan: [reports/findings.md](reports/findings.md).

## How it works

```
analytics/generate_data.py      two years of orders, customers, stock — with realistic defects
        │  raw_*.csv
        ▼
analytics/load_raw.py           raw.*      every column TEXT, loaded exactly as received
        │
        ▼
sql/01_data_quality_checks.sql  profile every defect in SQL
analytics/clean.py              apply a documented decision per defect → clean.* + data_quality_log
        │
        ▼
sql/02 … 10                     one file per business area, every answer saved to reports/output/<Q>.csv
sql/11_reporting_views.sql      reporting.* star schema for Excel / Power BI (+ reconciliation checks)
        │
        ├─► analytics/stats_analysis.py     are the differences real? (z-tests, chi-square, Mann-Whitney, bootstrap)
        ├─► analytics/build_excel_report.py 9-sheet management workbook with native charts
        └─► powerbi/                        Power Query + DAX measures for the dashboard
```

`python analytics/run_pipeline.py` runs every step (about 2 minutes), and
`pytest analytics/test_pipeline.py` checks the result: SQL and Python agree on every
data-quality count, no record is lost or invented, the reporting layer reconciles to the cent,
and the net revenue definition holds.

## Messy data, on purpose

The source export contains the defects a real legacy system produces. Each one gets a decision,
because deleting a row can delete real revenue or a real customer:

| Check | Records | Action |
|---|---:|---|
| Duplicate transaction records | 2,435 | Removed |
| Negative quantity (legacy return adjustments) | 134 | Investigated, excluded: the refund is already on the order |
| Invalid unit price (zero, negative, entered in cents) | 44 | Excluded |
| Missing customer ID | 5,469 | Kept as guest checkout, excluded from customer metrics |
| Missing category | 689 | Mapped from the product master |
| Missing payment method | 864 | Classified as Unknown |
| Inconsistent country names (`GR`, `Hellas`, `Ελλάδα`…) | 40,499 | Standardised |
| Four different date formats | 115,031 | Parsed with an explicit rule per format |
| Cancelled orders | 18,401 lines | Kept for cancellation KPIs, excluded from revenue |
| Quantity outliers (40–160 units) | 41 | Kept as genuine bulk orders, flagged |
| Duplicate / negative inventory snapshots | 513 / 378 | Removed / set to 0 and flagged |

Why each decision was made: [docs/data_quality_report.md](docs/data_quality_report.md).

## SQL: one file per business question

| File | Answers | Techniques |
|---|---|---|
| [`01_data_quality_checks.sql`](sql/01_data_quality_checks.sql) | Can the export be trusted? | regex profiling, `DISTINCT ON`, correlated checks |
| [`02_sales_kpis.sql`](sql/02_sales_kpis.sql) | Headline KPIs, 2025 vs 2024, by market and payment method | `ROLLUP`, `FILTER`, `LATERAL VALUES` unpivot, percentiles |
| [`03_revenue_trends.sql`](sql/03_revenue_trends.sql) | Daily → yearly trends, MoM / YoY, rolling 30/90-day, why AOV fell | `LAG`, framed windows, `generate_series` calendar |
| [`04_product_performance.sql`](sql/04_product_performance.sql) | Categories, ABC analysis, products declining 3 months in a row, winners/losers | running totals, `LAG` streaks, `rank()` |
| [`05_customer_analysis.sql`](sql/05_customer_analysis.sql) | Repeat rate, new vs returning, time to 2nd order, channels, late deliveries | `row_number`, `lead`, conditional aggregation |
| [`06_rfm_segmentation.sql`](sql/06_rfm_segmentation.sql) | RFM segments, value index, win-back list | `NTILE`, rule-based segmentation |
| [`07_cohort_retention.sql`](sql/07_cohort_retention.sql) | Cohort matrix, did retention improve, loyalty vs courier decomposition | cohort pivots with `age()`, mix decomposition |
| [`08_inventory_analysis.sql`](sql/08_inventory_analysis.sql) | Days of cover, risk classes, stockout episodes, lost sales, turnover | gaps-and-islands, `array_position` ordering |
| [`09_operations_analysis.sql`](sql/09_operations_analysis.sql) | Fulfilment speed, on-time delivery by courier, refunds, staffing hours | date arithmetic, percentiles |
| [`10_anomaly_investigation.sql`](sql/10_anomaly_investigation.sql) | Which days were outliers and why, sudden product drops, refund spikes | same-weekday rolling z-scores |
| [`11_reporting_views.sql`](sql/11_reporting_views.sql) | Star schema for BI tools + reconciliation | views, `first_value` |

Revenue is defined once, in the views `clean.order_summary` and `clean.sales_lines`
([`00_schema.sql`](sql/00_schema.sql)), so no two queries can disagree about what "revenue" means.
The reconciliation in `Q11.1` caught a €4.07 rounding leak in an early version of the refund
allocation, which is why refunds are no longer rounded per line.

## Reports

- **[findings.md](reports/findings.md)**: the management write-up and ranked action plan.
- **[ecommerce_management_report.xlsx](reports/ecommerce_management_report.xlsx)**: Summary, Revenue Trend, Products, Customers, Cohorts (colour-scaled matrix), Inventory (action list with status colours), Operations, Data Quality and Statistical Tests. Built by Python with native Excel charts, so it stays editable.
- **[statistical_tests.md](reports/statistical_tests.md)**: six claims tested, including a control showing the loyalty effect holds with delivery speed held constant.
- **[powerbi/](powerbi/)**: Power Query (M) for each reporting view, DAX measures and the dashboard layout. The `.pbix` itself is still to be built in Power BI Desktop.

## Running it

Requirements: Docker, Python 3.11+.

```sh
docker compose up -d analytics-db                 # PostgreSQL 16 on localhost:5439
pip install -r analytics/requirements.txt
python analytics/run_pipeline.py                  # ~2 min: data, cleaning, SQL, stats, Excel
pytest analytics/test_pipeline.py                 # trust checks
python analytics/run_sql.py 07                    # re-run one SQL file
```

Connect any SQL client to `postgresql://analyst:analyst@localhost:5439/analytics` to explore
`raw`, `clean` and `reporting`. The data is generated with a fixed seed, so every run gives the
same numbers.

## About the data

The data is simulated. [`analytics/generate_data.py`](analytics/generate_data.py) models customers as a
repeat-purchase process, daily inventory with supplier lead times and reorder points, and lost
sales when shelves are empty. It builds in the events the analysis is meant to uncover (a
loyalty programme, a courier change, products that rise and fall, under- and over-stocked SKUs),
then writes everything out with the defects of a real export. The analysis treats the data as
unknown and finds those events from the data alone.

## The storefront application

The repository started as the shop itself: a Next.js storefront and admin panel, Express/TypeScript API,
PostgreSQL and Stripe Checkout, with a 62-test suite proving stock can't be oversold and payments
can't be processed twice. The analytics schema extends its tables (`orders`, `order_items`,
`products`) with the history an analyst needs. Documentation: **[docs/APP.md](docs/APP.md)**.

## Repository layout

```
sql/                 00 schema · 01 data quality · 02–10 analysis · 11 reporting views
analytics/           generate · load · clean · run_sql · stats · Excel · pipeline · tests
reports/             findings.md · statistical_tests.md · management report (.xlsx) · output/ (one CSV per question)
docs/                kpi_dictionary.md · data_quality_report.md · APP.md · API.md · DEPLOY.md
powerbi/             Power Query (M) · DAX measures · dashboard layout
backend/ frontend/   the storefront application
```
