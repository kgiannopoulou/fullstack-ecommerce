# E-Commerce Sales, Profitability & Operations Analytics

**SQL · PostgreSQL · Python · pandas · Excel (Power Query, Power Pivot) · Power BI · DAX · Statistics · Git**

[![CI](https://github.com/kgiannopoulou/fullstack-ecommerce/actions/workflows/ci.yml/badge.svg)](https://github.com/kgiannopoulou/fullstack-ecommerce/actions/workflows/ci.yml)

An end-to-end data analyst project: **340,000+ messy e-commerce transaction records** turned into
management reporting. It starts with a business question, works through data quality, SQL analysis,
statistics, anomaly detection and a demand forecast, and ends with an Excel workbook, a Power BI
dashboard and a written report with recommendations.

![Executive Overview](reports/figures/dashboard_executive_overview.png)
<sub>Executive Overview page, rendered from the pipeline's data by `src/generate_report.py`. The interactive version is the Power BI project in [`powerbi/`](powerbi/).</sub>

**Start here:** [Executive Analysis Report (PDF, 6 pages)](reports/Executive_Analysis_Report.pdf) ·
[Excel workbook](excel/Monthly_Business_Performance.xlsx) · [Power BI dashboard](powerbi/) ·
[Full findings](reports/findings.md) · [SQL](sql/) · [Notebooks](notebooks/)

## Skills demonstrated

| Area | Demonstrated in this project |
|---|---|
| **SQL** | 79 business questions in 12 files: CTEs, joins, window functions (`lag`, `lead`, `rank`, `ntile`, running totals, framed windows), `ROLLUP`, `FILTER`, gaps-and-islands, cohort pivots, a reporting star schema |
| **Python** | pandas, data cleaning, a rule-based validation framework, automated pipeline (`python src/pipeline.py`), 30 pytest tests |
| **Power BI** | Star-schema data model, 51 DAX measures (time intelligence, `RANKX`, `DIVIDE`), five management pages |
| **Excel** | Power Query, Power Pivot data model with DAX, PivotTables with slicers, XLOOKUP, SUMIFS, COUNTIFS, INDEX/MATCH, IF/IFERROR |
| **Data analysis** | Revenue, **profitability**, customers (RFM, cohorts), products, inventory, operations |
| **Statistics** | Hypothesis tests (z, chi-square, Mann-Whitney, Welch t, Cochran-Mantel-Haenszel), bootstrap CIs, anomaly detection (z-scores), backtested demand forecast |
| **Business intelligence** | KPI definitions, management alerts, written recommendations for non-technical readers |
| **Data quality** | 28 validation rules in code, completeness / validity / duplicate scoring, reconciliation checks, a pipeline gate |
| **Git** | Versioned, documented, reproducible workflow with CI |

## Key findings

| | |
|---|---|
| 💶 | **€12.46M net revenue in 2025 (+29.2%)** and **€4.92M gross profit (+30.0%)**, from 338,182 valid transaction records. Gross margin held at **39.5%** even though shipping costs rose from 4.9% to 5.7% of revenue. |
| 📦 | **Revenue overstates what some products are worth.** 72 high-revenue, low-margin products are 25.5% of revenue but only 18.1% of gross profit. Duffel Bag Plus F951 is #20 by revenue but #44 by profit. |
| 🏷️ | **Discount codes did not pay for themselves.** Discounted baskets hold the same number of items (difference +0.008, 95% CI −0.017 to +0.034), customers are not more loyal, and about **€656k of gross profit** was given away. |
| 🔁 | **The loyalty programme works.** 90-day repeat purchasing rose from 27.8% to 41.3%: +11.3 pp from the programme, +2.1 pp from faster delivery. |
| 👥 | **At Risk and Cannot Lose Them customers** are 10.4% of customers but 16.8% of revenue. |
| ⚠️ | **Stockouts:** 12 A-class products ran out 3+ times in 2025 (~€133k lost sales). On 31 Dec, **47 products must be reordered today**, 9 of them A-class, with €64k of January revenue at risk. |
| 🔎 | **An automated alert, explained:** Wearables revenue −84% on 6 Jan 2025 was traced in SQL to one best-seller (€956k in 2024) that sold out and was never restocked. |

### Recommendations

1. **Reorder the 47 at-risk products now** and raise safety stock on the 12 A-class products that keep running out.
2. **Rank products by gross profit, not revenue.** Re-price or re-source the volume traps; add a minimum order value or shipping charge for bulky low-price items.
3. **Stop blanket discount codes.** Test targeted offers against a hold-out group before rolling them out.
4. **Keep the loyalty programme** and run a win-back campaign for At Risk / Cannot Lose Them customers.
5. **Alert on stock, not just on revenue:** a daily check when an A-class product's stock falls below lead-time demand.

> *"Initially I ranked products by revenue. After adding cost, discount, refund and shipping data, the ranking
> turned out to be misleading, so I changed the KPI used for product decisions to gross profit."*

---

## The business brief

The company has grown quickly. Its data sits in PostgreSQL, but there is no reliable reporting.
The Head of Operations asks:

1. **How is the business performing,** in revenue *and* profit?
2. **Which products and categories make money,** not just revenue?
3. **Are customers coming back** after their first purchase?
4. **Which products will run out of stock,** and which are overstocked?
5. **Did our discounts work?**
6. **What should we do next?**

## Deliverables

| Deliverable | What it is | For |
|---|---|---|
| [**Executive_Analysis_Report.pdf**](reports/Executive_Analysis_Report.pdf) | 6 pages: summary, performance, products & profitability, customers, inventory, recommendations, methodology | Management |
| [**Monthly_Business_Performance.xlsx**](excel/Monthly_Business_Performance.xlsx) | Executive Summary, Sales Analysis, Product Performance, Inventory, Customer Analysis, Raw Data, Data Dictionary | Managers who live in Excel |
| [**Power BI dashboard**](powerbi/) | Executive Overview · Sales & Product · Customer Analytics · Inventory & Operations · Data Quality | Self-service reporting |
| [findings.md](reports/findings.md) | Observation → investigation → explanation → recommendation, for every question | Analysts, reviewers |
| [Notebooks](notebooks/) | [Exploratory analysis](notebooks/exploratory_analysis.ipynb) · [Discount investigation](notebooks/statistical_analysis.ipynb) | Analysts |
| [Reorder list](reports/forecast_report.md) · [Anomaly report](reports/anomaly_report.md) · [Statistical tests](reports/statistical_tests.md) | Generated on every run | Operations |
| [Data quality](docs/data_quality.md) · [KPI dictionary](docs/kpi_dictionary.md) · [Data dictionary](docs/data_dictionary.md) · [Methodology](docs/methodology.md) | Documentation | Everyone |

## How it works

```
python src/pipeline.py

 0  generate_data.py      two years of orders, customers, stock: with the defects of a real export
 1  load_raw.py           raw.*  (every column TEXT, loaded exactly as received)
 2  clean.py              a documented decision per defect -> clean.* + data_quality_log
 3  validate.py           28 rules, raw vs clean; a critical failure on clean data STOPS the run
 4  transform.py          79 SQL questions -> reports/output/*.csv ; star schema -> data/cleaned/
 5  anomaly_detection.py  same-weekday z-scores: revenue by category, orders by country, refund rate
 6  forecast.py           30-day demand per SKU vs stock -> reorder list (backtested)
 7  stats_analysis.py     significance tests, incl. the discount investigation
 8  generate_report.py    management alerts, charts, Executive_Analysis_Report.pdf
 9  build_powerbi.py      Power BI project: TMDL model + report pages
10  build_excel.py        Excel workbook built through Excel: Power Query, Power Pivot, pivots, slicers
```

`pytest tests` then checks the result: SQL and Python agree on every data-quality count, no record
is lost or invented, the reporting layer reconciles to the cent, revenue and profit follow their
definitions, and the validation rules, anomaly maths and forecast behave on hand-made cases.

## Messy data, on purpose

Each defect gets a business decision, because deleting a row can delete real revenue or a real customer
([why each decision](docs/data_quality_report.md)):

| Check | Records | Action |
|---|---:|---|
| Duplicate transaction records | 2,435 | Removed |
| Negative quantity (legacy return adjustments) | 134 | Investigated, excluded: the refund is already on the order |
| Invalid unit price (zero, negative, entered in cents) | 44 | Excluded |
| Missing customer ID | 5,469 | Kept as guest checkout, excluded from customer metrics |
| Missing shipping cost (no matched courier invoice) | 2,862 | Imputed from courier and country, flagged |
| Missing category / payment method | 689 / 864 | Mapped from product master / labelled Unknown |
| Inconsistent country names (`GR`, `Hellas`, `Ελλάδα`…) | 40,499 | Standardised |
| Four different date formats | 115,031 | Parsed with an explicit rule per format |
| Duplicate / negative inventory snapshots | 513 / 378 | Removed / set to 0 and flagged |

| Data quality | Raw export | Clean warehouse |
|---|---:|---:|
| Completeness | 97.9% | 98.1% |
| Validity | 54.0% | 100.0% |
| Duplicates | 0.71% | 0.00% |
| Failed checks | 12 of 13 | 0 of 15 |

## SQL: one file per business question

| File | Answers | Techniques |
|---|---|---|
| [`01_data_quality_checks.sql`](sql/01_data_quality_checks.sql) | Can the export be trusted? | regex profiling, `DISTINCT ON` |
| [`02_sales_kpis.sql`](sql/02_sales_kpis.sql) | Headline KPIs, 2025 vs 2024, by market and payment method | `ROLLUP`, `FILTER`, `LATERAL VALUES` unpivot |
| [`03_revenue_trends.sql`](sql/03_revenue_trends.sql) | MoM / YoY, rolling 30/90-day, why AOV fell | `LAG`, framed windows, `generate_series` |
| [`04_product_performance.sql`](sql/04_product_performance.sql) | Categories, ABC analysis, declining products | running totals, `LAG` streaks, `rank()` |
| [`05_customer_analysis.sql`](sql/05_customer_analysis.sql) | Repeat rate, new vs returning, time to 2nd order | `row_number`, `lead` |
| [`06_rfm_segmentation.sql`](sql/06_rfm_segmentation.sql) | RFM segments, win-back list | `NTILE`, rule-based segmentation |
| [`07_cohort_retention.sql`](sql/07_cohort_retention.sql) | Cohort matrix, loyalty vs courier decomposition | cohort pivots, mix decomposition |
| [`08_inventory_analysis.sql`](sql/08_inventory_analysis.sql) | Days of cover, stockout episodes, lost sales, turnover | gaps-and-islands |
| [`09_operations_analysis.sql`](sql/09_operations_analysis.sql) | Fulfilment speed, on-time delivery, refunds | date arithmetic, percentiles |
| [`10_anomaly_investigation.sql`](sql/10_anomaly_investigation.sql) | Outlier days, and a manual investigation of an automated alert | same-weekday rolling windows |
| [`11_reporting_views.sql`](sql/11_reporting_views.sql) | Star schema for Excel / Power BI + reconciliation | views, window functions |
| [`12_profitability.sql`](sql/12_profitability.sql) | Revenue-to-profit bridge, revenue rank vs profit rank, volume traps, cost of discounts and courier | `rank()`, `percentile_cont`, quadrant analysis |

Revenue and gross profit are defined once, in the views `clean.order_summary` and `clean.sales_lines`
([`00_schema.sql`](sql/00_schema.sql)), so no two reports can disagree. Every answer is saved as a CSV:
[reports/output/index.md](reports/output/index.md).

## Excel workbook

[`Monthly_Business_Performance.xlsx`](excel/Monthly_Business_Performance.xlsx) is built by
[`src/build_excel.py`](src/build_excel.py), which drives Excel itself, so the workbook contains the real
features, refreshable in Excel:

- **Power Query**: one query per pipeline output, typed and renamed, with the folder as a single parameter.
- **Power Pivot**: a data model (sales + Calendar + Geography), relationships and 10 DAX measures, including prior-year and YoY growth.
- **PivotTables** on the model, all filtered by five **slicers**: Year, Month, Country, Category, Customer Type.
- **Formulas**: the Executive Summary follows a month picker with INDEX/MATCH, XLOOKUP (same month last year), SUMIFS (year to date, category revenue), COUNTIFS (stock risk), IF/IFERROR; product ranks with RANK.EQ; a cohort matrix built with SUMIFS and a colour scale.

## Power BI dashboard

[`powerbi/`](powerbi/) holds the dashboard as a Power BI project (PBIP: open it in Power BI Desktop):
a star schema (FactSales, FactOrders, FactInventoryDaily → DimDate, DimProduct, DimCustomer, DimChannel,
DimGeography) and **51 DAX measures**, so the report computes KPIs instead of reading pre-calculated
numbers. Pages: **Executive Overview** (KPIs with YoY, trends, management alerts), **Sales & Product**
(revenue vs margin scatter, revenue rank vs profit rank), **Customer Analytics** (RFM, cohort heatmap),
**Inventory & Operations** (the reorder table), **Data Quality**.

## Statistics, anomalies and forecasting

- **[Statistical tests](reports/statistical_tests.md)**: ten claims tested, including controls for the two
  things that changed in 2025, and the discount investigation stratified by month. Effect sizes and
  confidence intervals, not just p-values.
- **[Anomaly detection](reports/anomaly_report.md)**: same-weekday rolling mean and SD; tuned from 691
  flags to a short list by requiring a full baseline, a material gap and labelling known causes (Black
  Friday, bulk orders). One alert investigated by hand in SQL.
- **[30-day stockout forecast](reports/forecast_report.md)**: in-stock-day demand × seasonal index. It beat a
  naive forecast in all four backtest months (WAPE 12.7–17.7% vs 14.3–23.9%). A trend term was tested and
  dropped because it made the backtest worse.

## How this maps to a data analyst role

| Requirement | Evidence here |
|---|---|
| Work with complex datasets | 340k raw records across orders, customers, products and daily stock |
| SQL | 79 analytical queries, reporting views, reconciliation |
| Python, analytical workflows, automation | `src/pipeline.py`: extract, validate, clean, transform, detect, forecast, report |
| Dashboards and data products | Power BI dashboard, Excel workbook, reporting views |
| Statistics and advanced analysis | hypothesis tests, anomaly detection, backtested forecast |
| Communicate findings | executive PDF and findings written for managers |
| Operational needs | reorder list, stockout and courier analysis |
| Data governance and documentation | validation rules in code, data / KPI dictionaries, methodology |
| Excel | Power Query, Power Pivot, PivotTables, slicers, lookup formulas |
| Clean code, version control | modular Python, 30 tests, CI on every push |

## Running it

Requirements: Docker, Python 3.11+. Excel workbook build: Windows with Microsoft Excel.

```sh
docker compose up -d analytics-db          # PostgreSQL 16 on localhost:5439
pip install -r requirements.txt
python src/pipeline.py                     # ~4 min: everything above
python src/pipeline.py --notebooks         # ... and re-execute the notebooks
pytest tests                               # 30 checks
python src/run_sql.py 12                   # re-run one SQL file
```

Connect any SQL client to `postgresql://analyst:analyst@localhost:5439/analytics` to explore
`raw`, `clean` and `reporting`. The data is generated with a fixed seed, so every run gives the same numbers.

## About the data

The data is **simulated** ([`src/generate_data.py`](src/generate_data.py)), because real transaction data
with costs, stock and customer IDs is not public. It models customers as a repeat-purchase process,
daily inventory with lead times and lost sales, free shipping paid by the shop, and business events
(a loyalty programme, a courier change, products that rise and fall), then writes it all out with the
defects of a real export. The analysis treats the data as unknown and finds those events from the data
alone. The methods carry over to real data; the numbers do not.

## Repository layout

```
sql/          00 schema · 01 data quality · 02–10 analysis · 11 reporting views · 12 profitability
src/          pipeline.py and its steps (extract, clean, validate, transform, anomaly_detection, forecast, ...)
tests/        test_validation.py (unit) · test_pipeline.py (against the database)
notebooks/    exploratory_analysis.ipynb · statistical_analysis.ipynb
reports/      Executive_Analysis_Report.pdf · findings.md · figures/ · output/ (one CSV per SQL question)
excel/        Monthly_Business_Performance.xlsx
powerbi/      Power BI project (PBIP: TMDL model + report) · measures.dax
docs/         data_dictionary · kpi_dictionary · methodology · data_quality · data_quality_report
data/         raw/ and cleaned/ are generated (git-ignored) · sample/ is committed
app/          the storefront application the data comes from
```

## The source application

The repository started as the shop itself: a Next.js storefront and admin panel, an Express/TypeScript
API, PostgreSQL and Stripe Checkout, with a 62-test suite proving stock can't be oversold and payments
can't be processed twice. The analytics schema extends its `orders`, `order_items` and `products` tables
with the history an analyst needs. App documentation: [docs/APP.md](docs/APP.md).
