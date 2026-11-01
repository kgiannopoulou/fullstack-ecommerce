"""Turn raw.* into clean.* and record every data-quality decision.

Each rule below is a business decision, not just a filter: the rationale is
stored next to the count in clean.data_quality_log and published in
docs/data_quality_report.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
import db
import extract

STANDARD_COUNTRIES = ["Greece", "Cyprus", "Germany", "Italy", "France", "Netherlands", "Spain", "Bulgaria"]
COUNTRY_MAP = {
    "gr": "Greece", "greece": "Greece", "hellas": "Greece", "ελλάδα": "Greece",
    "cy": "Cyprus", "cyprus": "Cyprus", "κύπρος": "Cyprus",
    "de": "Germany", "germany": "Germany", "deutschland": "Germany",
    "it": "Italy", "italy": "Italy", "italia": "Italy",
    "fr": "France", "france": "France",
    "nl": "Netherlands", "netherlands": "Netherlands", "holland": "Netherlands", "the netherlands": "Netherlands",
    "es": "Spain", "spain": "Spain", "españa": "Spain",
    "bg": "Bulgaria", "bulgaria": "Bulgaria",
}
STATUS_MAP = {"completed": "completed", "complete": "completed", "cancelled": "cancelled",
              "canceled": "cancelled", "refunded": "refunded"}
# Most precise first: when an order's lines disagree, keep the one with a time.
DATE_FORMATS = [
    ("iso", r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", "%Y-%m-%d %H:%M:%S"),
    ("eu", r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$", "%d/%m/%Y %H:%M"),
    ("slash", r"^\d{4}/\d{2}/\d{2}$", "%Y/%m/%d"),
    ("named", r"^\d{2}-[A-Za-z]{3}-\d{4}$", "%d-%b-%Y"),
]
BULK_QTY = 40


class Log:
    def __init__(self):
        self.rows = []

    def add(self, name, table, records, action, rationale):
        self.rows.append({"check_id": len(self.rows) + 1, "check_name": name, "table_name": table,
                          "records": int(records), "action": action, "rationale": rationale})
        print(f"  {name:55s} {records:>8,}  {action}")

    def frame(self):
        return pd.DataFrame(self.rows)


def standard_country(s: pd.Series) -> pd.Series:
    out = s.str.strip().str.lower().map(COUNTRY_MAP)
    if out.isna().any():
        raise ValueError(f"unmapped countries: {sorted(s[out.isna()].unique())[:10]}")
    return out


def parse_dates(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    ts = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    rank = pd.Series(99, index=s.index)
    for i, (_, pattern, fmt) in enumerate(DATE_FORMATS):
        m = s.str.match(pattern)
        ts[m] = pd.to_datetime(s[m], format=fmt)
        rank[m] = i
    if ts.isna().any():
        raise ValueError(f"{ts.isna().sum()} unparseable dates")
    return ts, rank


def main():
    log = Log()
    with db.connect() as conn:
        raw = extract.raw_tables(conn)
        tx, products, customers, inventory = raw["transactions"], raw["products"], raw["customers"], raw["inventory"]
        raw_records = len(tx)
        print(f"raw transaction records: {raw_records:,}")

        # ---- products: the reference data -----------------------------------
        products = products.astype({"product_id": int, "list_price": float, "unit_cost": float,
                                    "supplier_lead_time_days": int})
        products["parcel_size"] = products["parcel_size"].str.strip().str.upper()
        products["launch_date"] = pd.to_datetime(products["launch_date"]).dt.date
        list_price = products.set_index("product_id")["list_price"]
        category = products.set_index("product_id")["category"]
        unit_cost = products.set_index("product_id")["unit_cost"]

        # ---- 1. duplicates ----------------------------------------------------
        dup = tx.duplicated("transaction_id", keep="first")
        log.add("Duplicate transaction records", "raw.transactions", dup.sum(), "Removed (kept first copy)",
                "The integration re-sent records with the same transaction ID and identical content. "
                "Keeping them would double-count revenue and units.")
        tx = tx[~dup].copy()
        tx = tx.astype({"order_id": int, "product_id": int, "quantity": int, "unit_price": float,
                        "discount_pct": float, "refund_amount": float})
        tx["shipping_cost"] = pd.to_numeric(tx["shipping_cost"])
        tx["customer_id"] = pd.to_numeric(tx["customer_id"]).astype("Int64")

        # ---- 2. negative quantities ----------------------------------------
        neg = tx["quantity"] < 0
        log.add("Negative quantity (legacy return adjustments)", "raw.transactions", neg.sum(),
                "Investigated, excluded (refund already on the order)",
                "Every negative line mirrors a positive sale of the same product in the same order "
                "(see Q01.7). They are manual stock-return entries from the old POS; the money side "
                "of returns is already recorded as refund_amount, so counting them would deduct twice.")
        tx = tx[~neg]

        # ---- 3. invalid prices ----------------------------------------------
        ratio = tx["unit_price"] / tx["product_id"].map(list_price)
        bad = (tx["unit_price"] <= 0) | (ratio > 5)
        log.add("Invalid unit price (zero, negative or >5x list)", "raw.transactions", bad.sum(), "Excluded",
                "Zero/negative prices and prices ~100x the list price (entered in cents) cannot be trusted. "
                "Too few to matter for totals (<0.02% of records), so they are excluded rather than guessed.")
        tx = tx[~bad].copy()

        # ---- 4. guest checkouts ---------------------------------------------
        guest = tx["customer_id"].isna()
        log.add("Missing customer ID (guest checkout)", "raw.transactions", guest.sum(),
                "Retained as guest; excluded from customer metrics",
                "These are real, paid orders placed without an account. Dropping them would understate "
                f"revenue; they are kept for sales KPIs ({tx.loc[guest, 'order_id'].nunique():,} orders) "
                "but cannot be part of retention, RFM or cohort analysis.")

        # ---- 5. missing category --------------------------------------------
        miss_cat = tx["category"].isna()
        log.add("Missing category", "raw.transactions", miss_cat.sum(), "Mapped from product master",
                "Category is an attribute of the product, not the sale. The product master has it for every SKU, "
                "so the value is recovered exactly instead of being bucketed as 'Unknown'.")
        tx["category"] = tx["product_id"].map(category)

        # ---- 6. payment method ----------------------------------------------
        miss_pay = tx["payment_method"].isna()
        log.add("Missing payment method", "raw.transactions", miss_pay.sum(), "Classified as Unknown",
                "Payment type is not needed for revenue, so the orders stay; reporting them as 'Unknown' keeps the "
                "payment-mix percentages honest instead of silently redistributing them.")
        tx["payment_method"] = tx["payment_method"].fillna("Unknown")

        # ---- 7. country -----------------------------------------------------
        nonstd = ~tx["customer_country"].isin(STANDARD_COUNTRIES)
        log.add("Non-standard country name", "raw.transactions", nonstd.sum(), "Standardised to English country name",
                "'GR', 'Hellas', 'Ελλάδα' and 'greece' are one market. Without mapping, Greece would be split "
                "across six rows of every country report.")
        tx["country"] = standard_country(tx["customer_country"])

        # ---- 8. dates -------------------------------------------------------
        ts, rank = parse_dates(tx["order_date"])
        log.add("Non-ISO date format", "raw.transactions", (rank > 0).sum(), "Parsed with explicit format rules",
                "Four formats are in use. Each is parsed with its own explicit rule (never guessed), so 05/03 is "
                "always 5 March. Where an order's lines disagree, the timestamp with a time of day is used.")
        tx["order_ts"], tx["date_rank"] = ts, rank

        # ---- 9/10/11. status ------------------------------------------------
        st = tx["order_status"].str.strip().str.lower()
        log.add("Non-standard order status spelling", "raw.transactions",
                (~tx["order_status"].isin(["completed", "cancelled", "refunded"])).sum(), "Normalised",
                "'COMPLETE', 'Completed' and 'CANCELED' are the same states written by different systems.")
        tx["status"] = st.map(STATUS_MAP)
        if tx["status"].isna().any():
            raise ValueError("unmapped status values")
        log.add("Cancelled order lines", "raw.transactions", (tx["status"] == "cancelled").sum(),
                "Kept for cancellation KPIs, excluded from revenue",
                "Cancelled orders were never shipped or paid, so they are not revenue - but they are an operational "
                "signal (cancellation rate by payment method), so the rows are kept.")
        log.add("Refunded order lines", "raw.transactions", (tx["status"] == "refunded").sum(),
                "Kept; refund deducted in Net Revenue",
                "The goods were shipped; the refunded amount (full or partial) is subtracted in Net Revenue.")

        # ---- 12. outliers ---------------------------------------------------
        bulk = tx["quantity"] >= BULK_QTY
        log.add("Quantity outliers (>= 40 units)", "raw.transactions", bulk.sum(),
                "Retained (verified bulk orders), flagged is_bulk",
                "Far above the P99 quantity, but prices and customers are normal: these are small businesses buying "
                "in bulk. They are real revenue, so they are kept and flagged so they can be excluded from "
                "per-order averages where they would distort them.")

        # ---- 13. shipping cost ----------------------------------------------
        no_ship = tx["shipping_cost"].isna() & (tx["status"] != "cancelled")
        log.add("Missing shipping cost (no matched courier invoice)", "raw.transactions", no_ship.sum(),
                "Imputed: median cost for the same courier and country",
                "The parcel was shipped (it has a courier and a delivery date), so the cost is real but the invoice "
                "line was not matched. Treating it as 0 would overstate gross profit; the courier-and-country median "
                f"is a close estimate ({tx.loc[no_ship, 'order_id'].nunique():,} orders, flagged shipping_cost_imputed).")

        # ---- orders (one row per order) ---------------------------------------
        best = tx.sort_values(["order_id", "date_rank"]).drop_duplicates("order_id")
        orders = best[["order_id", "customer_id", "order_ts", "status", "payment_method", "discount_pct",
                       "channel", "country", "courier", "ship_date", "delivery_date", "shipping_cost"]].copy()
        orders["is_guest"] = orders["customer_id"].isna()
        orders["order_date"] = orders["order_ts"].dt.date
        refunds = tx.groupby("order_id")["refund_amount"].sum().round(2)
        orders["refund_amount"] = orders["order_id"].map(refunds)
        shipped = orders["status"] != "cancelled"
        orders["shipping_cost_imputed"] = shipped & orders["shipping_cost"].isna()
        median_cost = orders[shipped].groupby(["courier", "country"])["shipping_cost"].transform("median")
        orders.loc[orders["shipping_cost_imputed"], "shipping_cost"] = median_cost[orders["shipping_cost_imputed"]].round(2)
        orders.loc[~shipped, "shipping_cost"] = 0.0
        if orders["shipping_cost"].isna().any():
            raise ValueError("shipping cost could not be imputed for some orders")

        # ---- order items ------------------------------------------------------
        items = tx[["transaction_id", "order_id", "product_id", "quantity", "unit_price", "discount_pct"]].copy()
        items["unit_cost"] = items["product_id"].map(unit_cost)
        items["gross_amount"] = (items["quantity"] * items["unit_price"]).round(2)
        items["discount_amount"] = (items["gross_amount"] * items["discount_pct"]).round(2)
        items["net_amount"] = (items["gross_amount"] - items["discount_amount"]).round(2)
        items["is_bulk"] = items["quantity"] >= BULK_QTY
        items = items.drop(columns="discount_pct")

        # ---- customers ------------------------------------------------------
        nonstd_c = ~customers["country"].isin(STANDARD_COUNTRIES)
        customers["country"] = standard_country(customers["country"])
        customers["customer_id"] = customers["customer_id"].astype(int)
        customers["signup_date"] = pd.to_datetime(customers["signup_date"]).dt.date

        # ---- inventory --------------------------------------------------------
        inv_dup = inventory.duplicated(["product_id", "snapshot_date"], keep="first")
        log.add("Duplicate inventory snapshots", "raw.inventory", inv_dup.sum(), "Removed",
                "The warehouse system uploaded some days twice. One stock count per product per day is kept.")
        inventory = inventory[~inv_dup].astype({"product_id": int, "stock_on_hand": int,
                                                 "units_received": int, "units_sold": int})
        negstock = inventory["stock_on_hand"] < 0
        log.add("Negative stock on hand", "raw.inventory", negstock.sum(), "Set to 0, flagged stock_corrected",
                "Physical stock cannot be negative: these are counting errors on days the SKU had sold out. "
                "Treating them as 0 (out of stock) matches the sales recorded on those days.")
        inventory["stock_corrected"] = negstock
        inventory.loc[negstock, "stock_on_hand"] = 0

        log.add("Non-standard country name (customer master)", "raw.customers", nonstd_c.sum(),
                "Standardised to English country name", "Same mapping as the transaction table.")

        # ---- write --------------------------------------------------------------
        conn.execute("TRUNCATE clean.order_items, clean.orders, clean.customers, clean.products, "
                     "clean.inventory_daily, clean.data_quality_log")
        db.copy_frame(conn, "clean.products", products)
        db.copy_frame(conn, "clean.customers", customers[["customer_id", "signup_date", "country", "acquisition_channel"]])
        db.copy_frame(conn, "clean.orders", orders[[
            "order_id", "customer_id", "is_guest", "order_ts", "order_date", "status", "payment_method",
            "discount_pct", "channel", "country", "courier", "ship_date", "delivery_date", "refund_amount",
            "shipping_cost", "shipping_cost_imputed"]])
        db.copy_frame(conn, "clean.order_items", items)
        db.copy_frame(conn, "clean.inventory_daily", inventory[[
            "snapshot_date", "product_id", "stock_on_hand", "units_received", "units_sold", "stock_corrected"]])
        dq = log.frame()
        db.copy_frame(conn, "clean.data_quality_log", dq)
        conn.execute("ANALYZE")

        valid = len(items)
        # Cancelled/refunded are business states and bulk orders are genuine:
        # they are documented decisions, not defects.
        not_defects = {"Cancelled order lines", "Refunded order lines", "Quantity outliers (>= 40 units)"}
        issues = int(dq.loc[~dq["check_name"].isin(not_defects), "records"].sum())
        write_report(dq, raw_records, valid, len(orders), orders["is_guest"].sum(), issues)
        print(f"valid transaction records: {valid:,}  orders: {len(orders):,}  issues logged: {issues:,}")


def write_report(dq: pd.DataFrame, raw_records: int, valid: int, n_orders: int, guests: int, issues: int):
    lines = [
        "# Data Quality Report",
        "",
        "Generated by `src/clean.py` from the raw export. The same counts are reproduced in SQL by",
        "`sql/01_data_quality_checks.sql` (Q01.10), and stored in `clean.data_quality_log`.",
        "",
        "| | |",
        "|---|---:|",
        f"| Raw transaction records | {raw_records:,} |",
        f"| Valid transaction records after cleaning | {valid:,} |",
        f"| Records removed (duplicates, return adjustments, invalid prices) | {raw_records - valid:,} |",
        f"| Data-quality defects found (sum over defect checks) | {issues:,} |",
        f"| Orders | {n_orders:,} (of which guest checkouts: {guests:,}) |",
        "",
        "Defects overlap (one record can have both a non-ISO date and a misspelt country), so they add up",
        "to more than the records affected. Only three checks remove records; every other decision keeps",
        "the data and repairs or labels it, because removing a row removes real revenue or a real customer.",
        "Cancelled/refunded lines and bulk orders are listed because they need a decision, but they are",
        "not defects and are not counted in the defect total.",
        "",
        "| # | Check | Table | Records | Action |",
        "|---:|---|---|---:|---|",
    ]
    for r in dq.itertuples():
        lines.append(f"| {r.check_id} | {r.check_name} | `{r.table_name}` | {r.records:,} | {r.action} |")
    lines += ["", "## Why each decision was made", ""]
    for r in dq.itertuples():
        lines += [f"**{r.check_id}. {r.check_name}** ({r.records:,} records, {r.action.lower()})", "", r.rationale, ""]
    lines += [
        "## What the cleaning does *not* do",
        "",
        "- It does not delete cancelled orders: the cancellation rate is a KPI. Revenue queries filter them.",
        "- It does not impute missing customers: guest revenue is real, but guests cannot have a retention curve.",
        "- It does not cap outliers: bulk orders are genuine. Per-order averages are reported with and without them.",
        "",
    ]
    (config.DOCS_DIR / "data_quality_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
