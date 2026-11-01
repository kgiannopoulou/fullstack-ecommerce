"""Transform: build the analytical datasets every report reads.

1. Runs every business question in sql/ (run_sql.py) -> reports/output/<Q>.csv
2. Exports the reporting star schema to data/cleaned/ for Power BI and Excel
   (Power Query imports these files; the SQL views stay the single definition)
3. Writes a small sample of every table to data/sample/ (committed, so the
   repository can be explored without running the pipeline)
4. write_alerts(): the management alerts on the executive dashboard page
   (pipeline.py calls it after anomaly detection and the forecast)

    python src/transform.py
"""
from __future__ import annotations

import pandas as pd

import config
import db
import run_sql

AS_OF = pd.Timestamp(config.AS_OF)

# table name in Power BI / Excel -> SQL
STAR = {
    "DimDate": "SELECT * FROM reporting.dim_date",
    "DimProduct": """SELECT product_id, sku, product_name, category, list_price, unit_cost, parcel_size,
                            supplier_lead_time_days, abc_class FROM reporting.dim_product""",
    "DimCustomer": """SELECT customer_id, country, acquisition_channel, signup_date, first_order_date, cohort_month,
                             orders, round(lifetime_revenue, 2) AS lifetime_revenue, recency_days, r_score, f_score,
                             rfm_segment FROM reporting.dim_customer""",
    "DimChannel": "SELECT * FROM reporting.dim_channel",
    "DimGeography": "SELECT * FROM reporting.dim_geography",
    "FactSales": """SELECT transaction_id, order_id, customer_id, order_date, product_id, country, channel_id,
                           customer_type, is_discounted, quantity, gross_amount, discount_amount,
                           round(refund_amount, 4) AS refund_amount, round(net_revenue, 4) AS net_revenue, cogs,
                           round(shipping_cost, 4) AS shipping_cost, round(gross_profit, 4) AS gross_profit, is_bulk
                    FROM reporting.fact_sales""",
    "FactOrders": """SELECT order_id, customer_id, order_date, status, payment_method, channel_id, country, courier,
                            customer_type, discount_pct, units, gross_amount, discount_amount, refund_amount,
                            net_revenue, cogs, shipping_cost, gross_profit, days_to_ship, days_to_deliver,
                            is_late, is_fulfilled, has_bulk FROM reporting.fact_orders""",
    "CohortRetention": "SELECT * FROM reporting.cohort_retention",
    "MonthlyKPIs": "SELECT * FROM reporting.monthly_kpis ORDER BY month",
    # Stockout day = no stock and nothing sold. Estimated lost units on such a day = the product's
    # average daily sales on in-stock days that year (same definition as Q08.3/Q08.4).
    "FactInventoryDaily": """
        WITH d AS (
            SELECT i.*, (i.stock_on_hand = 0 AND i.units_sold = 0) AS is_stockout,
                   extract(year FROM snapshot_date)::int AS yr
            FROM clean.inventory_daily i
        ),
        rate AS (
            SELECT product_id, yr, avg(units_sold) FILTER (WHERE NOT is_stockout) AS units_per_day
            FROM d GROUP BY 1, 2
        ),
        price AS (
            SELECT product_id, extract(year FROM order_date)::int AS yr, sum(net_revenue) / sum(quantity) AS net_price
            FROM clean.sales_lines GROUP BY 1, 2
        )
        SELECT d.snapshot_date, d.product_id, d.stock_on_hand, d.units_received, d.units_sold,
               round(d.stock_on_hand * p.unit_cost, 2) AS stock_value_at_cost, d.is_stockout,
               round(CASE WHEN d.is_stockout THEN COALESCE(r.units_per_day, 0) ELSE 0 END, 3) AS est_lost_units,
               round(CASE WHEN d.is_stockout THEN COALESCE(r.units_per_day, 0) * COALESCE(pr.net_price, 0) ELSE 0 END, 2)
                   AS est_lost_revenue
        FROM d
        JOIN clean.products p USING (product_id)
        LEFT JOIN rate r USING (product_id, yr)
        LEFT JOIN price pr USING (product_id, yr)""",
    # Pre-aggregated for the Excel pivot tables (the workbook stays small and fast).
    "SalesSummary": """
        SELECT date_trunc('month', s.order_date)::date AS month, extract(year FROM s.order_date)::int AS year,
               to_char(s.order_date, 'MM-Mon') AS month_name, s.country, p.category, s.customer_type, s.channel,
               count(DISTINCT s.order_id) AS orders, sum(s.quantity) AS units,
               round(sum(s.gross_amount), 2) AS gross_sales, round(sum(s.discount_amount), 2) AS discounts,
               round(sum(s.refund_amount), 2) AS refunds, round(sum(s.net_revenue), 2) AS net_revenue,
               round(sum(s.cogs), 2) AS cogs, round(sum(s.shipping_cost), 2) AS shipping_cost,
               round(sum(s.gross_profit), 2) AS gross_profit
        FROM reporting.fact_sales s JOIN clean.products p USING (product_id)
        GROUP BY 1, 2, 3, 4, 5, 6, 7""",
    "CustomerSegments": """
        SELECT rfm_segment AS segment, count(*) AS customers,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct_customers,
               round(sum(lifetime_revenue), 2) AS revenue,
               round(100 * sum(lifetime_revenue) / sum(sum(lifetime_revenue)) OVER (), 1) AS pct_revenue,
               round(avg(orders), 2) AS avg_orders, round(avg(recency_days), 0) AS avg_recency_days
        FROM reporting.dim_customer WHERE rfm_segment <> 'No purchase'
        GROUP BY 1 ORDER BY revenue DESC""",
    "CustomerTypeMonthly": """
        SELECT date_trunc('month', order_date)::date AS month, customer_type,
               count(*) FILTER (WHERE is_fulfilled) AS orders,
               count(DISTINCT customer_id) FILTER (WHERE is_fulfilled) AS customers,
               round(sum(net_revenue), 2) AS net_revenue, round(sum(gross_profit), 2) AS gross_profit
        FROM reporting.fact_orders GROUP BY 1, 2 ORDER BY 1, 2""",
    "ProductPerformance": """
        SELECT p.product_id, p.sku, p.product_name, p.category, p.abc_class,
               sum(s.quantity) FILTER (WHERE s.order_date >= '2025-01-01')                        AS units_2025,
               round(sum(s.net_revenue) FILTER (WHERE s.order_date >= '2025-01-01'), 2)           AS net_revenue_2025,
               round(sum(s.net_revenue) FILTER (WHERE s.order_date <  '2025-01-01'), 2)           AS net_revenue_2024,
               round(sum(s.gross_profit) FILTER (WHERE s.order_date >= '2025-01-01'), 2)          AS gross_profit_2025,
               round(sum(s.discount_amount) FILTER (WHERE s.order_date >= '2025-01-01'), 2)       AS discounts_2025,
               round(sum(s.shipping_cost) FILTER (WHERE s.order_date >= '2025-01-01'), 2)         AS shipping_cost_2025
        FROM reporting.dim_product p LEFT JOIN reporting.fact_sales s USING (product_id)
        GROUP BY 1, 2, 3, 4, 5""",
}
COPIED = {  # produced by other pipeline steps
    "DataQualityRules": config.REPORTS_DIR / "data_quality_rules.csv",
    "DataQualityScorecard": config.REPORTS_DIR / "data_quality_scorecard.csv",
}


def export_star(conn) -> dict[str, int]:
    config.CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    config.SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, sql in STAR.items():
        df = db.query(conn, sql)
        df.to_csv(config.CLEAN_DIR / f"{name}.csv", index=False)
        sample = df if len(df) <= 500 else df.sample(500, random_state=config.SEED).sort_index()
        sample.to_csv(config.SAMPLE_DIR / f"{name}.csv", index=False)
        counts[name] = len(df)
    for name, path in COPIED.items():
        if path.exists():
            pd.read_csv(path).to_csv(config.CLEAN_DIR / f"{name}.csv", index=False)
    return counts


def quarter_metrics(conn) -> pd.DataFrame:
    return db.query(conn, """
        SELECT to_char(order_date, 'YYYY-"Q"Q') AS quarter,
               sum(net_revenue)::float                                      AS net_revenue,
               (sum(gross_profit) / sum(net_revenue))::float                AS margin,
               (count(*) FILTER (WHERE status = 'refunded')::float
                 / count(*) FILTER (WHERE is_fulfilled))                    AS refund_rate,
               (count(*) FILTER (WHERE status = 'cancelled')::float / count(*)) AS cancel_rate
        FROM clean.order_summary GROUP BY 1 ORDER BY 1""").set_index("quarter")


def management_alerts(conn) -> pd.DataFrame:
    """Rules that turn the numbers into the 4-6 sentences a manager reads first."""
    q = quarter_metrics(conn)
    cur, prev, ly = q.index[-1], q.index[-2], q.index[-5]
    alerts = []

    def add(kind, area, text, value):
        alerts.append({"severity": kind, "icon": {"warning": "⚠", "positive": "↑", "info": "ℹ"}[kind],
                       "area": area, "alert": text, "value": round(value, 2), "as_of": AS_OF.date()})

    d_qoq = 100 * (q.loc[cur, "margin"] - q.loc[prev, "margin"])
    d_yoy = 100 * (q.loc[cur, "margin"] - q.loc[ly, "margin"])
    # Judged year on year: Q4 margin always dips with Black Friday discounting, so a
    # quarter-on-quarter rule would raise a false alarm every winter.
    add("warning" if d_yoy < -0.3 else "positive" if d_yoy > 0.3 else "info", "Profitability",
        f"Gross margin {100 * q.loc[cur, 'margin']:.1f}% in {cur}: {d_yoy:+.1f}pp vs {ly} "
        f"({d_qoq:+.1f}pp vs {prev}, the usual Q4 discount dip)", d_yoy)

    fc = pd.read_csv(config.CLEAN_DIR / "InventoryForecast.csv")
    risk_a = fc[(fc["abc_class"] == "A") & fc["risk"].isin(["STOCKOUT BEFORE RESTOCK", "REORDER NOW"])]
    add("warning" if len(risk_a) else "info", "Inventory",
        f"{len(risk_a)} A-class products at stockout risk in the next 30 days "
        f"(EUR {risk_a['revenue_at_risk_30d'].sum():,.0f} of revenue at risk)", len(risk_a))

    r_now, r_ly = 100 * q.loc[cur, "refund_rate"], 100 * q.loc[ly, "refund_rate"]
    add("warning" if r_now > r_ly + 0.2 else "positive" if r_now < r_ly - 0.2 else "info", "Operations",
        f"Refund rate {r_ly:.1f}% -> {r_now:.1f}% ({ly} vs {cur})", r_now - r_ly)

    ret = db.query(conn, f"""
        SELECT extract(year FROM order_date)::int AS yr, sum(net_revenue)::float AS rev
        FROM reporting.fact_orders
        WHERE customer_type = 'Returning' AND extract(quarter FROM order_date) = {cur[-1]}
        GROUP BY 1 ORDER BY 1""").set_index("yr")["rev"]
    g = 100 * (ret.iloc[-1] / ret.iloc[-2] - 1)
    add("positive" if g > 0 else "warning", "Customers",
        f"Returning-customer revenue {'up' if g > 0 else 'down'} {abs(g):.0f}% year on year ({cur})", g)

    vt = pd.read_csv(config.OUTPUT_DIR / "Q12.6.csv").set_index("quadrant")
    if "Volume traps" in vt.index:
        v = vt.loc["Volume traps"]
        add("warning", "Profitability",
            f"{int(v.products)} high-revenue, low-margin products: {v.revenue_share_pct:.0f}% of revenue but "
            f"{v.profit_share_pct:.0f}% of gross profit", v.revenue_share_pct - v.profit_share_pct)

    an = pd.read_csv(config.REPORTS_DIR / "anomalies.csv")
    recent = an[(pd.to_datetime(an["date"]) > AS_OF - pd.Timedelta(days=30)) & an["event"].isna()]
    add("warning" if len(recent) else "info", "Monitoring",
        f"{len(recent)} unexplained anomalies in the last 30 days", len(recent))

    a = pd.DataFrame(alerts)
    a.insert(0, "alert_id", range(1, len(a) + 1))
    return a


def write_alerts() -> pd.DataFrame:
    """Run after anomaly_detection.py and forecast.py (the alerts read their output)."""
    with db.connect() as conn:
        alerts = management_alerts(conn)
    alerts.to_csv(config.CLEAN_DIR / "ManagementAlerts.csv", index=False)
    alerts.to_csv(config.SAMPLE_DIR / "ManagementAlerts.csv", index=False)
    print("\n".join(f"{r.icon} {r.alert}" for r in alerts.itertuples()))
    return alerts


def main():
    run_sql.main([])
    with db.connect() as conn:
        counts = export_star(conn)
    for k, v in counts.items():
        print(f"data/cleaned/{k}.csv  {v:>9,} rows")


if __name__ == "__main__":
    main()
