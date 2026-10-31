"""Statistical checks behind the headline findings.

A difference in a dashboard is not a finding until it is unlikely to be
noise. Each test answers one claim made in reports/findings.md and is
written to reports/statistical_tests.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

import config
import db

FIRST_ORDERS = """
WITH ranked AS (
    SELECT customer_id, order_date, is_late, country,
           row_number() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS n,
           lead(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS next_order
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
)
SELECT order_date, is_late, country,
       COALESCE(next_order - order_date <= 90, false) AS repeat_90d
FROM ranked
WHERE n = 1 AND order_date <= '2025-10-02'
"""


def two_proportion(x1, n1, x2, n2):
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    z = (p2 - p1) / np.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return p1, p2, z, 2 * stats.norm.sf(abs(z)), (p2 - p1 - 1.96 * se, p2 - p1 + 1.96 * se)


def fmt_p(p):
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def main():
    rows = []
    with db.connect() as conn:
        f = db.query(conn, FIRST_ORDERS)
        f["order_date"] = pd.to_datetime(f["order_date"])
        orders = db.query(conn, """
            SELECT order_date, net_revenue::float AS net_revenue, has_bulk, payment_method, status,
                   country, (delivery_date - order_date) AS days_to_deliver
            FROM clean.order_summary""")
        orders["order_date"] = pd.to_datetime(orders["order_date"])

    # 1. Loyalty programme: did 90-day repeat purchasing rise?
    before = f[f["order_date"] < config.LOYALTY_LAUNCH]
    after = f[f["order_date"] >= config.LOYALTY_LAUNCH]
    p1, p2, z, p, ci = two_proportion(before["repeat_90d"].sum(), len(before), after["repeat_90d"].sum(), len(after))
    rows.append(("Repeat purchasing rose after the loyalty launch",
                 "Two-proportion z-test, 90-day repeat rate of first-time buyers",
                 f"{p1:.1%} -> {p2:.1%} (+{(p2 - p1) * 100:.1f} pp, 95% CI {ci[0] * 100:.1f} to {ci[1] * 100:.1f} pp)",
                 f"z = {z:.1f}", fmt_p(p), len(f)))

    # 2. Is the loyalty effect still there among on-time deliveries only?
    #    (rules out "it was just the courier")
    on_time = f[~f["is_late"].astype(bool)]
    b, a = on_time[on_time["order_date"] < config.LOYALTY_LAUNCH], on_time[on_time["order_date"] >= config.LOYALTY_LAUNCH]
    p1, p2, z, p, ci = two_proportion(b["repeat_90d"].sum(), len(b), a["repeat_90d"].sum(), len(a))
    rows.append(("The loyalty effect holds with delivery held constant (on-time first orders only)",
                 "Two-proportion z-test", f"{p1:.1%} -> {p2:.1%} (+{(p2 - p1) * 100:.1f} pp)",
                 f"z = {z:.1f}", fmt_p(p), len(on_time)))

    # 3. Late first delivery and coming back: chi-square + odds ratio.
    table = pd.crosstab(f["is_late"], f["repeat_90d"])
    chi2, p, _, _ = stats.chi2_contingency(table)
    odds = (table.loc[False, True] * table.loc[True, False]) / (table.loc[False, False] * table.loc[True, True])
    late_rate = f.loc[f["is_late"], "repeat_90d"].mean()
    ontime_rate = f.loc[~f["is_late"].astype(bool), "repeat_90d"].mean()
    rows.append(("A late first delivery lowers the chance of a second order",
                 "Chi-square test of independence (2x2) and odds ratio",
                 f"repeat {ontime_rate:.1%} on time vs {late_rate:.1%} late; on-time buyers have {odds:.2f}x the odds of returning",
                 f"chi2 = {chi2:.0f}", fmt_p(p), len(f)))

    # 4. Courier switch: Greek delivery times before vs after.
    gr = orders[(orders["country"] == "Greece") & orders["days_to_deliver"].notna()]
    d_before = gr.loc[gr["order_date"] < config.COURIER_SWITCH, "days_to_deliver"].astype(float)
    d_after = gr.loc[gr["order_date"] >= config.COURIER_SWITCH, "days_to_deliver"].astype(float)
    u, p = stats.mannwhitneyu(d_before, d_after, alternative="greater")
    rows.append(("The new courier delivers faster in Greece",
                 "Mann-Whitney U (one-sided; delivery days are skewed, so no t-test)",
                 f"median {d_before.median():.0f} -> {d_after.median():.0f} days, mean {d_before.mean():.2f} -> {d_after.mean():.2f}",
                 f"U = {u:.3g}", fmt_p(p), len(gr)))

    # 5. AOV fell in 2025: real, and not caused by bulk outliers?
    ful = orders[(orders["status"] != "cancelled") & ~orders["has_bulk"].astype(bool)]
    a24 = ful.loc[ful["order_date"].dt.year == 2024, "net_revenue"].to_numpy()
    a25 = ful.loc[ful["order_date"].dt.year == 2025, "net_revenue"].to_numpy()
    t, p = stats.ttest_ind(a25, a24, equal_var=False)
    rng = np.random.default_rng(config.SEED)
    boot = [rng.choice(a25, len(a25)).mean() - rng.choice(a24, len(a24)).mean() for _ in range(1000)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    rows.append(("Average order value fell in 2025 (bulk orders excluded)",
                 "Welch t-test + bootstrap 95% CI (1,000 resamples)",
                 f"EUR {a24.mean():.2f} -> {a25.mean():.2f} (diff {a25.mean() - a24.mean():.2f}, 95% CI {lo:.2f} to {hi:.2f})",
                 f"t = {t:.1f}", fmt_p(p), len(a24) + len(a25)))

    # 6. Cash on delivery is cancelled more often.
    cod = orders["payment_method"] == "Cash on Delivery"
    canc = orders["status"] == "cancelled"
    p1, p2, z, p, ci = two_proportion((canc & ~cod).sum(), (~cod).sum(), (canc & cod).sum(), cod.sum())
    rows.append(("Cash-on-delivery orders are cancelled more often",
                 "Two-proportion z-test", f"{p1:.1%} other methods vs {p2:.1%} COD",
                 f"z = {z:.1f}", fmt_p(p), len(orders)))

    out = pd.DataFrame(rows, columns=["claim", "test", "result", "statistic", "p_value", "n"])
    out.to_csv(config.OUTPUT_DIR / "statistical_tests.csv", index=False)
    lines = ["# Statistical tests", "",
             "Generated by `analytics/stats_analysis.py`. Each row checks one claim from",
             "[findings.md](findings.md) against the possibility that it is noise (alpha = 0.05).", "",
             "| Claim | Test | Result | Statistic | p-value | n |", "|---|---|---|---|---|---:|"]
    for r in out.itertuples():
        lines.append(f"| {r.claim} | {r.test} | {r.result} | {r.statistic} | {r.p_value} | {r.n:,} |")
    lines += ["", "Notes:", "",
              "- The data covers the whole customer base, not a sample, so very small p-values are expected for",
              "  large effects. The confidence intervals and effect sizes matter more than the p-values.",
              "- Test 2 is the important control: two things changed in 2025, so the loyalty effect is re-tested",
              "  among customers whose first delivery was on time, which removes the courier change from the comparison.",
              "- These are observational comparisons, not an experiment: a before/after difference supports, but",
              "  does not prove, that the programme caused it. A holdout group would."]
    (config.REPORTS_DIR / "statistical_tests.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out[["claim", "result", "p_value"]].to_string(index=False))


if __name__ == "__main__":
    main()
