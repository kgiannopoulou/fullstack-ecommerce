"""Anomaly detection: flag days and weeks that are far from what was expected.

Deliberately simple, explainable statistics, so every alert can be explained
to a manager in one sentence:

  * Revenue by category and orders by country (daily):
      expected = mean of the same weekday over the previous 8 weeks
      z        = (actual - expected) / standard deviation of those 8 days
                 (floored at 10% of expected, so a quiet 8 weeks cannot turn
                 normal noise into an alert)
      flagged when |z| >= 3.5, the gap is at least 25% and the segment is big
      enough to matter (>= EUR 1,500 or >= 25 orders expected per day)
  * Refund rate by category (weekly, because daily counts are too small):
      baseline = refund rate over the previous 12 weeks
      z        = binomial z-score of this week's rate against the baseline
      flagged when z >= 3 and the rate is at least 50% above baseline

Known causes (Black Friday weekend, the December peak, a single bulk B2B
order) are labelled, not hidden: an analyst still wants to see them, but they are not surprises.

Outputs: reports/anomalies.csv, reports/anomaly_report.md, data/cleaned/Anomalies.csv

    python src/anomaly_detection.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
import db
import extract

WEEKS = 8
Z = 3.5
MIN_GAP = 0.25
MIN_EXPECTED = {"net_revenue": 1500.0, "orders": 25.0}
SD_FLOOR = 0.10


def black_friday(year: int) -> pd.Timestamp:
    nov = pd.Timestamp(f"{year}-11-01")
    return nov + pd.offsets.Week(weekday=4) + pd.offsets.Week(3)


def calendar_event(day: pd.Timestamp) -> str:
    bf = black_friday(day.year)
    if bf - pd.Timedelta(days=1) <= day <= bf + pd.Timedelta(days=3):
        return "Black Friday weekend"
    if day.month == 12 and day.day <= 22:
        return "December peak"
    if day.month == 12:
        return "Christmas / year end"
    return ""


def same_weekday_zscores(s: pd.Series, weeks: int = WEEKS) -> pd.DataFrame:
    """s: a complete daily series. Returns actual, expected, sd, z, gap."""
    s = s.asfreq("D", fill_value=0.0)
    lagged = pd.concat([s.shift(7 * k) for k in range(1, weeks + 1)], axis=1)
    full = lagged.notna().all(axis=1)               # a full 8-week history is required
    expected = lagged.mean(axis=1).where(full)
    sd = np.maximum(lagged.std(axis=1, ddof=1), SD_FLOOR * expected)
    out = pd.DataFrame({"actual": s, "expected": expected, "sd": sd})
    out["z"] = (out["actual"] - out["expected"]) / out["sd"].replace(0, np.nan)
    out["gap_pct"] = 100 * (out["actual"] / out["expected"].replace(0, np.nan) - 1)
    return out.dropna(subset=["expected"])


def detect_daily(daily: pd.DataFrame, by: str, value: str, metric: str) -> pd.DataFrame:
    rows = []
    for key, g in daily.groupby(by):
        s = g.groupby("order_date")[value].sum()
        s.index = pd.to_datetime(s.index)
        sc = same_weekday_zscores(s)
        hit = sc[(sc["z"].abs() >= Z) & (sc["gap_pct"].abs() >= 100 * MIN_GAP)
                 & (sc["expected"] >= MIN_EXPECTED[value])]
        bulk = g.groupby("order_date")["bulk_revenue"].sum()
        bulk.index = pd.to_datetime(bulk.index)
        for day, r in hit.iterrows():
            # A spike that disappears without bulk (B2B-size) orders is explained by them.
            bulk_explains = value == "net_revenue" and r.actual - bulk.get(day, 0.0) < r.expected + Z * r.sd
            rows.append({"date": day.date(), "metric": metric, "dimension": by, "segment": key,
                         "actual": round(r.actual, 2), "expected": round(r.expected, 2),
                         "deviation_pct": round(r.gap_pct, 1), "z_score": round(r.z, 1),
                         "bulk_order": bool(bulk_explains and r.z > 0)})
    return pd.DataFrame(rows)


def detect_refund_rate(daily: pd.DataFrame, baseline_weeks: int = 12) -> pd.DataFrame:
    d = daily.assign(week=pd.to_datetime(daily["order_date"]).dt.to_period("W-SUN").dt.start_time)
    w = d.groupby(["category", "week"])[["orders", "refunded_orders"]].sum().reset_index()
    rows = []
    for cat, g in w.groupby("category"):
        g = g.sort_values("week").set_index("week")
        base_n = g["orders"].shift(1).rolling(baseline_weeks).sum()
        base_x = g["refunded_orders"].shift(1).rolling(baseline_weeks).sum()
        p0 = base_x / base_n
        p = g["refunded_orders"] / g["orders"]
        z = (p - p0) / np.sqrt(p0 * (1 - p0) / g["orders"])
        hit = (z >= Z) & (p >= p0 * (1 + 2 * MIN_GAP)) & (g["refunded_orders"] >= 5)
        for week in g.index[hit.fillna(False)]:
            rows.append({"date": week.date(), "metric": "Refund rate (weekly)", "dimension": "category", "segment": cat,
                         "actual": round(100 * p[week], 2), "expected": round(100 * p0[week], 2),
                         "deviation_pct": round(100 * (p[week] / p0[week] - 1), 1), "z_score": round(z[week], 1),
                         "bulk_order": False})
    return pd.DataFrame(rows)


def run(daily: pd.DataFrame, country_orders: pd.DataFrame) -> pd.DataFrame:
    parts = [
        detect_daily(daily, "category", "net_revenue", "Net revenue"),
        detect_daily(country_orders, "country", "orders", "Orders"),
        detect_refund_rate(daily),
    ]
    a = pd.concat([p for p in parts if len(p)], ignore_index=True)
    a["event"] = [calendar_event(pd.Timestamp(x)) for x in a["date"]]
    a.loc[a["bulk_order"] & (a["event"] == ""), "event"] = "Bulk (B2B) order"
    a = a.drop(columns="bulk_order")
    a["direction"] = np.where(a["deviation_pct"] > 0, "spike", "drop")
    a["severity"] = np.select([a["z_score"].abs() >= 5, a["z_score"].abs() >= 4], ["high", "medium"], "low")
    return a.sort_values(["date", "metric", "segment"]).reset_index(drop=True)


def describe(r) -> str:
    sign = "+" if r.deviation_pct > 0 else ""
    base = "vs 12-week baseline" if "Refund" in r.metric else "vs expected"
    return f"{r.metric} | {r.segment} | {sign}{r.deviation_pct:.1f}% {base} (z = {r.z_score:+.1f})"


def write_report(a: pd.DataFrame):
    as_of = pd.Timestamp(config.AS_OF)
    recent = a[pd.to_datetime(a["date"]) > as_of - pd.Timedelta(days=30)]
    unexplained = a[a["event"] == ""]
    lines = [
        "# Anomaly report", "",
        "Generated by [`src/anomaly_detection.py`](../src/anomaly_detection.py). Method: each day is compared with",
        f"the same weekday over the previous {WEEKS} weeks (z-score); refund rates are compared week by week with",
        f"their previous 12 weeks. An anomaly needs |z| >= {Z:.0f} *and* a material gap, so small noisy segments",
        "do not raise alarms.", "",
        f"## ANOMALIES DETECTED: last 30 days to {as_of:%Y-%m-%d}", "",
    ]
    if len(recent):
        lines += ["```"]
        for r in recent.sort_values("z_score", key=abs, ascending=False).head(12).itertuples():
            lines += [f"{r.date}  {describe(r)}" + (f"  [{r.event}]" if r.event else "")]
        lines += ["```", ""]
    else:
        lines += ["None.", ""]
    lines += [
        "## Summary, whole period", "",
        "| Metric | Flags | Explained (calendar / bulk order) | Unexplained | Spikes | Drops |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for m, g in a.groupby("metric"):
        lines.append(f"| {m} | {len(g)} | {(g['event'] != '').sum()} | {(g['event'] == '').sum()} | "
                     f"{(g['direction'] == 'spike').sum()} | {(g['direction'] == 'drop').sum()} |")
    lines += ["", "## Largest unexplained anomalies", "",
              "| Date | Metric | Segment | Actual | Expected | Deviation | z |", "|---|---|---|---:|---:|---:|---:|"]
    for r in unexplained.reindex(unexplained["z_score"].abs().sort_values(ascending=False).index).head(20).itertuples():
        lines.append(f"| {r.date} | {r.metric} | {r.segment} | {r.actual:,.2f} | {r.expected:,.2f} | "
                     f"{r.deviation_pct:+.1f}% | {r.z_score:+.1f} |")
    lines += ["", "One of these is investigated by hand in SQL in",
              "[`sql/10_anomaly_investigation.sql`](../sql/10_anomaly_investigation.sql) (Q10.6 - Q10.8): an alert is",
              "a question, and the investigation is what turns it into an explanation.", ""]
    (config.REPORTS_DIR / "anomaly_report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    with db.connect() as conn:
        daily = extract.daily_sales(conn)
        country_orders = extract.daily_orders_by_country(conn)
    a = run(daily, country_orders)
    a.to_csv(config.REPORTS_DIR / "anomalies.csv", index=False)
    config.CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    a.assign(description=[describe(r) for r in a.itertuples()]).to_csv(config.CLEAN_DIR / "Anomalies.csv", index=False)
    write_report(a)
    print(f"{len(a)} anomalies ({(a['event'] == '').sum()} not explained by the calendar or a bulk order)")
    print(a.groupby(["metric", "direction"]).size().to_string())


if __name__ == "__main__":
    main()
