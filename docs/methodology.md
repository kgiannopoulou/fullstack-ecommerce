# Methodology

How the numbers in this project were produced, and how far they can be trusted.

## 1. The workflow

```
business question → messy source data → validate → clean (documented decisions) → validate again (gate)
   → SQL analysis → statistics / anomalies / forecast → Excel + Power BI → written recommendations
```

`python src/pipeline.py` runs the whole chain in about four minutes and rebuilds every output.
`pytest tests` checks it: 20 unit tests on the rules and helpers, and 10 checks against the
database (SQL and Python agree on every data-quality count, no record is lost or invented,
every reporting view reconciles to the cent, and revenue and profit follow their definitions).

## 2. Data

The source data is **simulated** ([`src/generate_data.py`](../src/generate_data.py)), because real
e-commerce transaction data with costs, stock and customer IDs is not public. The simulation is
built to behave like a real business and to fail like a real export:

- customers as a repeat-purchase process, with seasonality, growth and Black Friday;
- products with life cycles (growing, declining, discontinued) and a long tail;
- daily inventory with supplier lead times, reorder points and lost sales when shelves are empty;
- events for the analysis to find without being told: a loyalty programme (March 2025) and a
  faster, more expensive courier for Greece (May 2025);
- the defects of a legacy export: duplicates, four date formats, 25 spellings of 8 countries,
  missing values, prices in cents, negative stock counts, missing courier invoices.

The analysis treats the data as unknown. The methods carry over to real data; the figures do not.

## 3. Cleaning

Every defect has a business decision (remove, repair, label or keep) and a written reason
([data_quality_report.md](data_quality_report.md)). Only three rules remove records (exact
duplicates, legacy return adjustments that would double-count refunds, impossible prices). The
rest keep the record, because deleting a row deletes real revenue or a real customer.

## 4. Definitions

Revenue and gross profit are defined once, in two database views, and every SQL file, the Excel
workbook and the Power BI measures read from them ([kpi_dictionary.md](kpi_dictionary.md)):

- **Net revenue** = gross sales − discounts − refunds, cancelled orders excluded.
- **Gross profit** = net revenue − cost of goods − outbound shipping.

Order-level amounts (refunds, shipping) are allocated to lines so that product-level profit is
possible: refunds in proportion to line value, shipping in proportion to quantity × parcel weight.
Reconciliation checks prove the allocations add back up to the order totals.

## 5. Methods

| Question type | Method | Why this one |
|---|---|---|
| KPIs, trends, rankings | SQL: CTEs, window functions (`lag`, `rank`, running totals, framed windows), `ROLLUP`, `FILTER` | transparent, reproducible, close to the data |
| Is a difference real? | two-proportion z-test, chi-square + odds ratio, Mann-Whitney U, Welch t-test, bootstrap CIs, Cochran-Mantel-Haenszel | chosen per data type: proportions, skewed values, stratified comparisons |
| Customer value | RFM segmentation, cohort retention | standard, explainable to marketing |
| Unusual days | same-weekday rolling mean and SD (8 weeks), z-score, plus a materiality threshold | explainable in one sentence; respects weekly seasonality |
| Stock decisions | in-stock-day demand × seasonal index, backtested against a naive forecast | simple enough to trust, tested before use |

**Statistics.** The data covers every order, not a sample, so p-values are small for almost any
effect. Effect sizes and confidence intervals are reported alongside them and matter more.

**Confounding.** Two examples handled explicitly:
- the loyalty programme and the courier change happened in the same year, so their effects are
  separated by re-testing among on-time deliveries only (`Q07.3`, `Q07.5`, test 2);
- discount codes cluster in November-December, so discounted and full-price orders are compared
  within the same month ([statistical_analysis.ipynb](../notebooks/statistical_analysis.ipynb)).

**Forecast.** A damped trend term was tested and removed because it made every backtest month worse.
Risk is judged against supplier lead time, not a fixed 30 days.

**Anomalies.** Thresholds were tuned to avoid alert fatigue: a first version flagged 691 days in
two years; requiring a full 8-week baseline, a minimum segment size, |z| ≥ 3.5 and labelling known
causes (Black Friday, bulk orders) brought it to a list someone can act on. One alert was then
investigated by hand in SQL (`Q10.6`–`Q10.8`).

## 6. Limitations

- Simulated data: realistic behaviour, but not a real company's numbers.
- Before/after comparisons are observational. A hold-out group would measure the loyalty
  programme and discount codes directly.
- No website-session data: the effect of discounts on conversion cannot be measured.
- Lost sales assume demand while out of stock equals demand when in stock (an upper bound).
- Purchase orders already in transit are not in the export, so the reorder list is a checklist
  for purchasing, not an automatic order.
- One year of history for seasonality: an unusual January last year would be repeated in the forecast.
