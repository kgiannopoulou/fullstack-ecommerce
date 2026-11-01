"""Extract: read tables out of PostgreSQL into pandas.

Every later step (validate, clean, transform, anomaly detection, forecast,
reports) gets its data through these functions, so there is one place that
knows where the data lives.

    python src/extract.py          # prints row counts per layer
"""
from __future__ import annotations

import pandas as pd

import db

RAW_TABLES = ["products", "customers", "transactions", "inventory"]
CLEAN_TABLES = ["products", "customers", "orders", "order_items", "inventory_daily", "data_quality_log"]


def raw_tables(conn) -> dict[str, pd.DataFrame]:
    """The legacy export exactly as landed: every column is text."""
    return {t: db.query(conn, f"SELECT * FROM raw.{t}") for t in RAW_TABLES}


def clean_tables(conn, tables: list[str] | None = None) -> dict[str, pd.DataFrame]:
    return {t: db.query(conn, f"SELECT * FROM clean.{t}") for t in (tables or CLEAN_TABLES)}


def reporting(conn, view: str, where: str = "") -> pd.DataFrame:
    return db.query(conn, f"SELECT * FROM reporting.{view} {where}")


def daily_sales(conn) -> pd.DataFrame:
    """Fulfilled sales per day x category x country, the input for anomaly detection."""
    return db.query(conn, """
        SELECT o.order_date, s.category, o.country,
               count(DISTINCT o.order_id)                    AS orders,
               sum(s.net_revenue)::float                     AS net_revenue,
               sum(s.gross_profit)::float                    AS gross_profit,
               COALESCE(sum(s.net_revenue) FILTER (WHERE s.is_bulk), 0)::float AS bulk_revenue,
               count(DISTINCT o.order_id) FILTER (WHERE o.status = 'refunded') AS refunded_orders
        FROM clean.sales_lines s
        JOIN clean.orders o USING (order_id)
        GROUP BY 1, 2, 3""")


def daily_orders_by_country(conn) -> pd.DataFrame:
    """Fulfilled orders per day x country (counted once, whatever they contain)."""
    return db.query(conn, """
        SELECT order_date, country, count(*) AS orders, 0.0::float AS bulk_revenue
        FROM clean.order_summary WHERE is_fulfilled
        GROUP BY 1, 2""")


def daily_inventory(conn) -> pd.DataFrame:
    return db.query(conn, """
        SELECT i.snapshot_date, i.product_id, p.sku, p.product_name, p.category, p.unit_cost::float,
               p.supplier_lead_time_days, i.stock_on_hand, i.units_received, i.units_sold
        FROM clean.inventory_daily i JOIN clean.products p USING (product_id)""")


def main():
    with db.connect() as conn:
        for schema, tables in (("raw", RAW_TABLES), ("clean", CLEAN_TABLES)):
            for t in tables:
                n = conn.execute(f"SELECT count(*) FROM {schema}.{t}").fetchone()[0]
                print(f"{schema}.{t:20s} {n:>10,}")


if __name__ == "__main__":
    main()
