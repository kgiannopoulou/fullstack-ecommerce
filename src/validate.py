"""Validate: data-quality rules kept in code, scored on every run.

Each rule is a small function that returns a boolean mask of the records that
FAIL it, plus the share of failures the business tolerates. The same rule set
runs twice:

  * on the raw export   - measures how bad the source is (expected to fail)
  * on the clean tables - a gate: if a critical rule fails here, the pipeline
                          stops before anything is reported

Outputs
  reports/data_quality_rules.csv      one row per stage x rule
  reports/data_quality_scorecard.csv  the headline scores (completeness, validity, ...)
  docs/data_quality.md                the framework and the latest results

    python src/validate.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

import config
import db
import extract

STANDARD_COUNTRIES = {"Greece", "Cyprus", "Germany", "Italy", "France", "Netherlands", "Spain", "Bulgaria"}
STANDARD_STATUS = {"completed", "cancelled", "refunded"}
ISO_TS = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    dimension: str          # Completeness | Validity | Uniqueness | Consistency
    table: str
    column: str
    description: str
    fails: Callable[[dict[str, pd.DataFrame]], pd.Series]
    threshold: float = 0.0  # tolerated failure rate
    critical: bool = True   # a critical failure on clean data stops the pipeline


@dataclass
class Result:
    stage: str
    rule: Rule
    checked: int
    failures: int

    @property
    def failure_rate(self) -> float:
        return self.failures / self.checked if self.checked else 0.0

    @property
    def passed(self) -> bool:
        return self.failure_rate <= self.rule.threshold


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _shipped(t: pd.DataFrame) -> pd.Series:
    status = t["order_status"] if "order_status" in t else t["status"]
    return ~status.astype(str).str.lower().str.startswith("cancel")


# ----------------------------------------------------------------- raw rules --
# Raw columns are all text, exactly as the legacy system exported them.
def raw_rules() -> list[Rule]:
    tx = "transactions"

    def price_ratio(d):
        t, p = d[tx], d["products"]
        lp = t["product_id"].map(p.set_index("product_id")["list_price"].pipe(_num))
        return _num(t["unit_price"]) / lp

    return [
        Rule("R01", "Uniqueness", tx, "transaction_id", "Each transaction ID appears once",
             lambda d: d[tx].duplicated("transaction_id", keep="first")),
        Rule("R02", "Completeness", tx, "customer_id", "Customer ID present (guest checkout allowed up to 3%)",
             lambda d: d[tx]["customer_id"].isna(), threshold=0.03, critical=False),
        Rule("R03", "Completeness", tx, "category", "Category present",
             lambda d: d[tx]["category"].isna()),
        Rule("R04", "Completeness", tx, "payment_method", "Payment method present",
             lambda d: d[tx]["payment_method"].isna()),
        Rule("R05", "Completeness", tx, "shipping_cost", "Shipping cost present on shipped orders",
             lambda d: d[tx]["shipping_cost"].isna() & _shipped(d[tx])),
        Rule("R06", "Validity", tx, "quantity", "Quantity is a positive integer",
             lambda d: ~(_num(d[tx]["quantity"]) > 0)),
        Rule("R07", "Validity", tx, "unit_price", "Unit price > 0 and at most 5x the list price",
             lambda d: ~((_num(d[tx]["unit_price"]) > 0) & (price_ratio(d) <= 5))),
        Rule("R08", "Validity", tx, "order_date", "Order date in ISO format (YYYY-MM-DD hh:mm:ss)",
             lambda d: ~d[tx]["order_date"].astype(str).str.match(ISO_TS)),
        Rule("R09", "Consistency", tx, "customer_country", "Country uses the standard English name",
             lambda d: ~d[tx]["customer_country"].isin(STANDARD_COUNTRIES)),
        Rule("R10", "Consistency", tx, "order_status", "Order status uses the standard lower-case code",
             lambda d: ~d[tx]["order_status"].isin(STANDARD_STATUS)),
        Rule("R11", "Uniqueness", "inventory", "product_id, snapshot_date", "One stock count per product per day",
             lambda d: d["inventory"].duplicated(["product_id", "snapshot_date"], keep="first")),
        Rule("R12", "Validity", "inventory", "stock_on_hand", "Stock on hand is not negative",
             lambda d: _num(d["inventory"]["stock_on_hand"]) < 0),
        Rule("R13", "Consistency", "customers", "country", "Customer country uses the standard English name",
             lambda d: ~d["customers"]["country"].isin(STANDARD_COUNTRIES)),
    ]


# --------------------------------------------------------------- clean rules --
def clean_rules() -> list[Rule]:
    def orphan(child, key, parent):
        return lambda d: ~d[child][key].isin(d[parent][key])

    def net_amount_wrong(d):
        i = d["order_items"]
        expected = (i["gross_amount"].astype(float) - i["discount_amount"].astype(float)).round(2)
        return (expected - i["net_amount"].astype(float)).abs() > 0.011

    return [
        Rule("C01", "Uniqueness", "order_items", "transaction_id", "Each transaction ID appears once",
             lambda d: d["order_items"].duplicated("transaction_id")),
        Rule("C02", "Uniqueness", "orders", "order_id", "Each order appears once",
             lambda d: d["orders"].duplicated("order_id")),
        Rule("C03", "Completeness", "orders", "customer_id", "Customer ID present (guest checkout allowed up to 3%)",
             lambda d: d["orders"]["customer_id"].isna(), threshold=0.03, critical=False),
        Rule("C04", "Completeness", "orders", "payment_method", "Payment method known (Unknown allowed up to 1%)",
             lambda d: d["orders"]["payment_method"].eq("Unknown"), threshold=0.01, critical=False),
        Rule("C05", "Validity", "order_items", "quantity", "Quantity > 0",
             lambda d: ~(d["order_items"]["quantity"].astype(float) > 0)),
        Rule("C06", "Validity", "order_items", "unit_price", "Unit price > 0",
             lambda d: ~(d["order_items"]["unit_price"].astype(float) > 0)),
        Rule("C07", "Validity", "orders", "status", "Status is completed, refunded or cancelled",
             lambda d: ~d["orders"]["status"].isin(STANDARD_STATUS)),
        Rule("C08", "Validity", "orders", "country", "Country is one of the 8 markets",
             lambda d: ~d["orders"]["country"].isin(STANDARD_COUNTRIES)),
        Rule("C09", "Validity", "orders", "shipping_cost", "Shipped orders have a shipping cost > 0",
             lambda d: (d["orders"]["status"] != "cancelled") & ~(d["orders"]["shipping_cost"].astype(float) > 0)),
        Rule("C10", "Validity", "inventory_daily", "stock_on_hand", "Stock on hand >= 0",
             lambda d: d["inventory_daily"]["stock_on_hand"] < 0),
        Rule("C11", "Consistency", "order_items", "product_id", "Every line points to a known product",
             orphan("order_items", "product_id", "products")),
        Rule("C12", "Consistency", "order_items", "order_id", "Every line belongs to a known order",
             orphan("order_items", "order_id", "orders")),
        Rule("C13", "Consistency", "orders", "delivery_date", "Delivery is not before the order",
             lambda d: pd.to_datetime(d["orders"]["delivery_date"]) < pd.to_datetime(d["orders"]["order_date"])),
        Rule("C14", "Consistency", "orders", "refund_amount", "Only refunded orders carry a refund",
             lambda d: (d["orders"]["refund_amount"].astype(float) > 0) & (d["orders"]["status"] != "refunded")),
        Rule("C15", "Consistency", "order_items", "net_amount", "Net amount = gross - discount",
             net_amount_wrong),
    ]


# ------------------------------------------------------------------ scoring --
def run_rules(stage: str, rules: list[Rule], data: dict[str, pd.DataFrame]) -> list[Result]:
    out = []
    for r in rules:
        mask = r.fails(data).fillna(True).astype(bool)
        out.append(Result(stage, r, int(len(mask)), int(mask.sum())))
    return out


def required_columns(stage: str) -> tuple[str, list[str]]:
    if stage == "raw":
        return "transactions", ["transaction_id", "order_id", "order_date", "customer_id", "product_id", "category",
                                "quantity", "unit_price", "payment_method", "order_status", "customer_country"]
    return "orders", ["order_id", "customer_id", "order_date", "status", "payment_method", "country", "channel"]


def scorecard(stage: str, results: list[Result], data: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Headline scores shown on the data-quality dashboard."""
    table, cols = required_columns(stage)
    df = data[table]
    present = df[cols].notna()
    if stage == "clean":   # 'Unknown' is a placeholder, not a value
        present["payment_method"] &= df["payment_method"] != "Unknown"
    validity = [r for r in results if r.rule.dimension in ("Validity", "Consistency")]
    dup = next(r for r in results if r.rule.dimension == "Uniqueness")
    # Records that fail any validity/consistency rule, counted once.
    invalid = np.zeros(len(data[dup.rule.table]), dtype=bool)
    for r in validity:
        if r.rule.table == dup.rule.table:
            invalid |= r.rule.fails(data).fillna(True).to_numpy(bool)
    return {
        "records": len(df) if stage == "raw" else len(data["order_items"]),
        "completeness_pct": round(100 * present.all(axis=1).mean(), 2),
        "validity_pct": round(100 * (1 - invalid.mean()), 2),
        "duplicates_pct": round(100 * dup.failure_rate, 2),
        "missing_values_pct": round(100 * (1 - present.to_numpy().mean()), 2),
        "rules_checked": len(results),
        "failed_checks": sum(not r.passed for r in results),
        "critical_failures": sum((not r.passed) and r.rule.critical for r in results),
    }


def results_frame(results: list[Result]) -> pd.DataFrame:
    return pd.DataFrame([{
        "stage": x.stage, "rule_id": x.rule.rule_id, "dimension": x.rule.dimension, "table": x.rule.table,
        "column": x.rule.column, "rule": x.rule.description, "records_checked": x.checked,
        "failures": x.failures, "failure_rate_pct": round(100 * x.failure_rate, 3),
        "threshold_pct": round(100 * x.rule.threshold, 2), "critical": x.rule.critical,
        "status": "PASS" if x.passed else "FAIL",
    } for x in results])


def main() -> int:
    with db.connect() as conn:
        raw = extract.raw_tables(conn)
        clean = extract.clean_tables(conn, ["products", "orders", "order_items", "inventory_daily"])
    res_raw = run_rules("raw", raw_rules(), raw)
    res_clean = run_rules("clean", clean_rules(), clean)
    rules = results_frame(res_raw + res_clean)
    cards = {"raw": scorecard("raw", res_raw, raw), "clean": scorecard("clean", res_clean, clean)}
    card = pd.DataFrame([{"stage": k, **c} for k, c in cards.items()])

    config.REPORTS_DIR.mkdir(exist_ok=True)
    rules.to_csv(config.REPORTS_DIR / "data_quality_rules.csv", index=False)
    card.to_csv(config.REPORTS_DIR / "data_quality_scorecard.csv", index=False)
    write_doc(rules, card)

    print(card.to_string(index=False))
    failed = rules[(rules["stage"] == "clean") & (rules["status"] == "FAIL")]
    if failed["critical"].any():
        print("\nCRITICAL data-quality failures on clean data, stopping:\n" + failed.to_string(index=False))
        return 1
    print(f"\nclean data passes all {int((rules['stage'] == 'clean').sum())} rules"
          + (f" ({len(failed)} non-critical warnings)" if len(failed) else ""))
    return 0


def write_doc(rules: pd.DataFrame, card: pd.DataFrame):
    r, c = card.set_index("stage").loc["raw"], card.set_index("stage").loc["clean"]
    lines = [
        "# Data Quality Framework",
        "",
        "Data quality is measured, not assumed. The rules live in code",
        "([`src/validate.py`](../src/validate.py)), run on every pipeline execution, and are unit-tested",
        "([`tests/test_validation.py`](../tests/test_validation.py)). The same results feed the",
        "*Data Quality* page of the Power BI report and the Excel workbook.",
        "",
        "## Scorecard",
        "",
        "| Metric | Raw export | Clean warehouse | Definition |",
        "|---|---:|---:|---|",
        f"| Records | {int(r.records):,} | {int(c.records):,} | transaction lines |",
        f"| Completeness | {r.completeness_pct:.1f}% | {c.completeness_pct:.1f}% | records with every required field present |",
        f"| Validity | {r.validity_pct:.1f}% | {c.validity_pct:.1f}% | records passing every validity and consistency rule |",
        f"| Duplicates | {r.duplicates_pct:.2f}% | {c.duplicates_pct:.2f}% | repeated transaction IDs |",
        f"| Missing values | {r.missing_values_pct:.2f}% | {c.missing_values_pct:.2f}% | empty cells across required fields |",
        f"| Failed checks | {int(r.failed_checks)} of {int(r.rules_checked)} | {int(c.failed_checks)} of {int(c.rules_checked)} | rules above their tolerated failure rate |",
        "",
        "The raw export is *expected* to fail: that is why the cleaning step exists. The clean warehouse is a",
        "**gate**: if a critical rule fails there, `pipeline.py` stops before any report is rebuilt, so a",
        "broken load can never reach a dashboard. Non-critical rules (guest checkouts, unknown payment method)",
        "have a tolerated rate agreed with the business and are reported as warnings above it.",
        "",
        "## Dimensions",
        "",
        "| Dimension | Question it answers |",
        "|---|---|",
        "| Completeness | Is the value there? |",
        "| Validity | Is the value possible (positive quantity, plausible price, real date)? |",
        "| Uniqueness | Is each record recorded once? |",
        "| Consistency | Does it agree with other data (standard codes, keys that exist, amounts that add up)? |",
        "",
        "## Rules and latest results",
        "",
    ]
    for stage, title in (("raw", "Raw export (before cleaning)"), ("clean", "Clean warehouse (pipeline gate)")):
        lines += [f"### {title}", "", "| Rule | Dimension | Table.column | Rule | Failures | Rate | Tolerated | Status |",
                  "|---|---|---|---|---:|---:|---:|---|"]
        for x in rules[rules["stage"] == stage].itertuples():
            lines.append(f"| {x.rule_id} | {x.dimension} | `{x.table}.{x.column}` | {x.rule} | {x.failures:,} | "
                         f"{x.failure_rate_pct:.2f}% | {x.threshold_pct:.0f}% | {'✅ PASS' if x.status == 'PASS' else '❌ FAIL'} |")
        lines.append("")
    lines += [
        "## How a defect is handled",
        "",
        "Finding a defect is half the job; each one also needs a business decision (remove, repair, label or",
        "keep). Those decisions and their reasons are in [data_quality_report.md](data_quality_report.md), and",
        "the SQL profiling that reproduces every count is [`sql/01_data_quality_checks.sql`](../sql/01_data_quality_checks.sql).",
        "",
    ]
    (config.DOCS_DIR / "data_quality.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
