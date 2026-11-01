"""Checks that the numbers in the reports can be trusted.

Run after the pipeline (needs the analytics database):  pytest tests/test_pipeline.py
"""
import pytest

import config
import db


@pytest.fixture(scope="module")
def conn():
    with db.connect() as c:
        yield c


def one(conn, sql):
    return conn.execute(sql).fetchone()[0]


def test_sql_data_quality_checks_match_python_cleaning(conn):
    """The SQL profiling (Q01.10) and clean.py must agree on every count."""
    q = dict((qid, sql) for qid, _, sql in db.questions(config.SQL_DIR / "01_data_quality_checks.sql"))
    sql_counts = db.query(conn, q["Q01.10"])["records"].tolist()
    py_counts = db.query(conn, "SELECT records FROM clean.data_quality_log ORDER BY check_id")["records"].tolist()
    assert sql_counts == py_counts


def test_no_records_lost_or_invented(conn):
    raw_unique = one(conn, "SELECT count(DISTINCT transaction_id) FROM raw.transactions")
    removed = one(conn, """SELECT sum(records) FROM clean.data_quality_log
                           WHERE check_name LIKE 'Negative quantity%' OR check_name LIKE 'Invalid unit price%'""")
    assert one(conn, "SELECT count(*) FROM clean.order_items") == raw_unique - removed


def test_reporting_layer_reconciles(conn):
    db.run_file(conn, config.SQL_DIR / "11_reporting_views.sql")
    q = dict((qid, sql) for qid, _, sql in db.questions(config.SQL_DIR / "11_reporting_views.sql"))
    checks = db.query(conn, q["Q11.1"])
    assert checks["passes"].all(), checks[~checks["passes"]].to_string()


def test_net_revenue_definition(conn):
    """Net revenue = gross - discounts - refunds on fulfilled orders (KPI dictionary)."""
    gross, disc, refunds, net = conn.execute("""
        SELECT sum(gross_amount) FILTER (WHERE is_fulfilled), sum(discount_amount) FILTER (WHERE is_fulfilled),
               sum(refund_amount), sum(net_revenue) FROM clean.order_summary""").fetchone()
    assert abs((gross - disc - refunds) - net) < 0.01


def test_gross_profit_definition(conn):
    """Gross profit = net revenue - COGS - shipping, on fulfilled orders only (KPI dictionary)."""
    net, cogs, ship, gp = conn.execute("""
        SELECT sum(net_revenue), sum(cogs) FILTER (WHERE is_fulfilled), sum(shipping_cost), sum(gross_profit)
        FROM clean.order_summary""").fetchone()
    assert abs((net - cogs - ship) - gp) < 0.01
    assert one(conn, "SELECT count(*) FROM clean.orders WHERE status = 'cancelled' AND shipping_cost <> 0") == 0


def test_shipping_cost_allocation_adds_up_per_order(conn):
    """Line-level shipping (allocated by parcel weight) must sum back to each order's cost."""
    assert one(conn, """
        SELECT count(*) FROM (
            SELECT o.order_id FROM clean.order_summary o JOIN clean.sales_lines s USING (order_id)
            GROUP BY o.order_id, o.shipping_cost HAVING abs(sum(s.shipping_cost) - o.shipping_cost) > 0.005) x""") == 0


def test_clean_data_passes_the_quality_gate():
    import pandas as pd
    rules = pd.read_csv(config.REPORTS_DIR / "data_quality_rules.csv")
    clean = rules[rules["stage"] == "clean"]
    assert len(clean) > 0
    assert not ((clean["status"] == "FAIL") & clean["critical"]).any(), clean[clean["status"] == "FAIL"].to_string()


def test_clean_data_invariants(conn):
    assert one(conn, "SELECT count(*) FROM clean.order_items WHERE quantity <= 0 OR unit_price <= 0") == 0
    assert one(conn, "SELECT count(*) FROM clean.inventory_daily WHERE stock_on_hand < 0") == 0
    assert one(conn, "SELECT count(*) FROM clean.orders WHERE status NOT IN ('completed','refunded','cancelled')") == 0
    assert one(conn, "SELECT count(*) FROM clean.orders WHERE country NOT IN "
                     "('Greece','Cyprus','Germany','Italy','France','Netherlands','Spain','Bulgaria')") == 0
    # cancelled orders never carry revenue or refunds
    assert one(conn, "SELECT count(*) FROM clean.order_summary WHERE status = 'cancelled' AND net_revenue <> 0") == 0


def test_abc_classes_cover_the_catalogue(conn):
    shares = dict(conn.execute("""
        SELECT abc_class, sum(lifetime_net_revenue) / (SELECT sum(lifetime_net_revenue) FROM reporting.dim_product)
        FROM reporting.dim_product GROUP BY 1""").fetchall())
    assert 0.79 <= float(shares["A"]) <= 0.90   # A starts below 80%, so it ends just above it
    assert abs(sum(float(v) for v in shares.values()) - 1) < 1e-9


def test_every_question_has_a_result_file():
    for path in sorted(config.SQL_DIR.glob("[0-9][0-9]_*.sql")):
        if path.name.startswith("00_"):
            continue
        for qid, _, _ in db.questions(path):
            assert (config.OUTPUT_DIR / f"{qid}.csv").exists(), qid
