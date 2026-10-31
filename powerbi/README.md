# Power BI management dashboard

The dashboard reads the `reporting` schema built by [`sql/11_reporting_views.sql`](../sql/11_reporting_views.sql),
so it uses the same KPI definitions as the SQL analysis and the Excel report.

| File | Contents |
|---|---|
| [`queries.pq`](queries.pq) | Power Query (M) for each table: connects to the analytics Postgres and sets column types |
| [`measures.dax`](measures.dax) | DAX measures (net revenue, AOV, growth, retention, on-time delivery, stock risk) mirroring [docs/kpi_dictionary.md](../docs/kpi_dictionary.md) |

The `.pbix` file is not in the repository yet. It has to be built in Power BI Desktop
(Windows) from these two files, following the layout below.

## Model

Star schema: `fact_orders` and `fact_sales` joined to `dim_date` (marked as the date table),
`dim_product` and `dim_customer`. `inventory_status` and `cohort_retention` are stand-alone
tables for their own pages.

## Pages

1. **Performance**: KPI cards (Net Revenue, Orders, AOV, YoY Growth %, Refund Rate %), monthly revenue line with the previous year, rolling 90-day revenue, revenue by country.
2. **Products**: revenue by category (bar), ABC class donut, top/bottom products table with YoY change, slicer on category.
3. **Customers**: repeat customer rate, RFM segment matrix (customers %, revenue %, Value Index), revenue by acquisition channel.
4. **Retention**: cohort matrix (cohort × month_n, retention % with a colour scale), 90-day repeat rate before/after the loyalty programme.
5. **Inventory & Operations**: products at risk, overstock value, stock-status table with the recommended action, on-time delivery % by courier and month.

## Refresh

```sh
docker compose up -d analytics-db
python analytics/run_pipeline.py      # rebuilds the data and the reporting views
```

Then *Refresh* in Power BI or Excel.
