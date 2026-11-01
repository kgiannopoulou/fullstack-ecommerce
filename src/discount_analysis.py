"""Statistical investigation: did discounting pay for itself?

About one order in four uses a discount code (10-25% off). Did the codes
increase sales enough to justify the margin they give away?

Codes are used far more in November and December, when baskets differ anyway,
so every comparison is also made *within the same month* and then averaged
(weighted by discounted orders). Repeat purchasing is compared for first-time
buyers with a Cochran-Mantel-Haenszel test stratified by month.

Called by stats_analysis.py; the walk-through with charts is
notebooks/statistical_analysis.ipynb.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.contingency_tables import StratifiedTable

import config
import db

ORDERS = """
SELECT order_id, order_date, discount_pct::float AS discount_pct, units, gross_amount::float AS basket,
       net_revenue::float AS net_revenue, gross_profit::float AS gross_profit
FROM clean.order_summary
WHERE is_fulfilled AND NOT has_bulk
"""
FIRST_ORDERS = """
WITH r AS (
    SELECT customer_id, order_date, discount_pct,
           row_number() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS n,
           lead(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS next_order
    FROM clean.order_summary
    WHERE is_fulfilled AND customer_id IS NOT NULL
)
SELECT date_trunc('month', order_date)::date AS month, discount_pct > 0 AS discounted,
       COALESCE(next_order - order_date <= 90, false) AS repeat_90d
FROM r WHERE n = 1 AND order_date <= '2025-10-02'
"""


def fmt_p(p):
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def load(conn) -> tuple[pd.DataFrame, pd.DataFrame]:
    o = db.query(conn, ORDERS)
    o["month"] = pd.to_datetime(o["order_date"]).dt.to_period("M")
    o["disc"] = o["discount_pct"] > 0
    return o, db.query(conn, FIRST_ORDERS)


def within_month(o: pd.DataFrame, col: str, n_boot: int = 200) -> dict:
    """Discounted minus full-price mean inside each month, weighted by discounted orders.
    95% CI by bootstrap over orders."""
    rng = np.random.default_rng(config.SEED)

    def est(df):
        m = df.groupby(["month", "disc"])[col].mean().unstack()
        w = df[df["disc"]].groupby("month").size()
        d = (m[True] - m[False]).reindex(w.index)
        return float(np.average(d, weights=w)), int((d > 0).sum()), len(d)

    point, months_up, months = est(o)
    boot = [est(o.sample(len(o), replace=True, random_state=int(rng.integers(1_000_000_000))))[0] for _ in range(n_boot)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"diff": point, "lo": lo, "hi": hi, "months_higher": months_up, "months": months}


def repeat_test(f: pd.DataFrame) -> dict:
    tables = []
    for _, g in f.groupby("month"):
        ct = pd.crosstab(g["discounted"], g["repeat_90d"]).reindex(index=[True, False], columns=[True, False], fill_value=0)
        if (ct.sum(axis=1) > 0).all():
            tables.append(ct.to_numpy())
    st = StratifiedTable(tables)
    cmh = st.test_null_odds(correction=True)
    lo, hi = st.oddsratio_pooled_confint()
    return {"odds_ratio": st.oddsratio_pooled, "lo": lo, "hi": hi, "chi2": cmh.statistic, "p": cmh.pvalue,
            "rate_discounted": f.loc[f["discounted"], "repeat_90d"].mean(),
            "rate_full_price": f.loc[~f["discounted"], "repeat_90d"].mean(), "n": len(f)}


def analyse(o: pd.DataFrame, f: pd.DataFrame) -> dict:
    d, n = o[o["disc"]], o[~o["disc"]]
    r = {"n_disc": len(d), "n_full": len(n),
         "units": within_month(o, "units"), "basket": within_month(o, "basket"),
         "gross_profit": within_month(o, "gross_profit"), "repeat": repeat_test(f),
         "mean": o.groupby("disc")[["units", "basket", "net_revenue", "gross_profit"]].mean(),
         "margin_full": n["gross_profit"].sum() / n["net_revenue"].sum(),
         "margin_disc": d["gross_profit"].sum() / d["net_revenue"].sum()}
    r["p_units"] = stats.mannwhitneyu(d["units"], n["units"]).pvalue
    r["t_basket"], r["p_basket"] = stats.ttest_ind(d["basket"], n["basket"], equal_var=False)
    r["t_gp"], r["p_gp"] = stats.ttest_ind(d["gross_profit"], n["gross_profit"], equal_var=False)
    r["profit_given_away"] = (r["mean"].loc[False, "gross_profit"] - r["mean"].loc[True, "gross_profit"]) * len(d)
    m = r["margin_full"]
    r["break_even_lift"] = {k: m / (m - k) - 1 for k in (0.10, 0.15, 0.20, 0.25)}
    return r


def test_rows(r: dict) -> list[tuple]:
    m, u, b, g, rep = r["mean"], r["units"], r["basket"], r["gross_profit"], r["repeat"]
    n = r["n_disc"] + r["n_full"]
    return [
        ("Discount codes do not make customers buy more units",
         "Mann-Whitney U + within-month difference (bootstrap CI)",
         f"{m.loc[False, 'units']:.2f} vs {m.loc[True, 'units']:.2f} units/order; within-month diff "
         f"{u['diff']:+.3f} (95% CI {u['lo']:+.3f} to {u['hi']:+.3f})", "", fmt_p(r["p_units"]), n),
        ("Discount codes do not raise the basket value before discount",
         "Welch t-test + within-month difference (bootstrap CI)",
         f"EUR {m.loc[False, 'basket']:.2f} vs {m.loc[True, 'basket']:.2f}; within-month diff EUR {b['diff']:+.2f} "
         f"(95% CI {b['lo']:+.2f} to {b['hi']:+.2f})", f"t = {r['t_basket']:.2f}", fmt_p(r["p_basket"]), n),
        ("Discounted orders earn less gross profit",
         "Welch t-test + within-month difference (bootstrap CI)",
         f"EUR {m.loc[False, 'gross_profit']:.2f} vs {m.loc[True, 'gross_profit']:.2f} per order; within-month diff "
         f"EUR {g['diff']:+.2f} (95% CI {g['lo']:+.2f} to {g['hi']:+.2f}), lower in {g['months'] - g['months_higher']} of {g['months']} months",
         f"t = {r['t_gp']:.1f}", fmt_p(r["p_gp"]), n),
        ("First orders with a discount do not create more loyal customers",
         "Cochran-Mantel-Haenszel test, stratified by first-order month",
         f"90-day repeat {rep['rate_full_price']:.1%} full price vs {rep['rate_discounted']:.1%} discounted; "
         f"common odds ratio {rep['odds_ratio']:.2f} (95% CI {rep['lo']:.2f} to {rep['hi']:.2f})",
         f"chi2 = {rep['chi2']:.1f}", fmt_p(rep["p"]), rep["n"]),
    ]


def markdown(r: dict) -> list[str]:
    m, u, b, g, rep = r["mean"], r["units"], r["basket"], r["gross_profit"], r["repeat"]
    be = r["break_even_lift"]
    return [
        "## Investigation: did discounting pay for itself?", "",
        f"**Question.** {r['n_disc'] / (r['n_disc'] + r['n_full']):.0%} of orders use a discount code (10-25% off). Did the codes increase sales",
        "enough to justify the margin they give away?", "",
        "**Approach.** Compare fulfilled orders with and without a code (bulk B2B orders excluded). Codes are",
        "used far more in November and December, when baskets are different anyway, so every comparison is",
        "also made *within the same month* and averaged. Repeat purchasing is compared for first-time buyers",
        "with a Cochran-Mantel-Haenszel test stratified by month. Walk-through with charts:",
        "[notebooks/statistical_analysis.ipynb](../notebooks/statistical_analysis.ipynb).", "",
        "| Measure | Full price | Discounted | Within-month difference (95% CI) |", "|---|---:|---:|---:|",
        f"| Orders | {r['n_full']:,} | {r['n_disc']:,} | |",
        f"| Units per order | {m.loc[False, 'units']:.2f} | {m.loc[True, 'units']:.2f} | {u['diff']:+.3f} ({u['lo']:+.3f} to {u['hi']:+.3f}) |",
        f"| Basket before discount | EUR {m.loc[False, 'basket']:.2f} | EUR {m.loc[True, 'basket']:.2f} | EUR {b['diff']:+.2f} ({b['lo']:+.2f} to {b['hi']:+.2f}) |",
        f"| Net order value | EUR {m.loc[False, 'net_revenue']:.2f} | EUR {m.loc[True, 'net_revenue']:.2f} | |",
        f"| Gross profit per order | EUR {m.loc[False, 'gross_profit']:.2f} | EUR {m.loc[True, 'gross_profit']:.2f} | EUR {g['diff']:+.2f} ({g['lo']:+.2f} to {g['hi']:+.2f}) |",
        f"| Gross margin | {100 * r['margin_full']:.1f}% | {100 * r['margin_disc']:.1f}% | |",
        f"| 90-day repeat rate (first orders) | {rep['rate_full_price']:.1%} | {rep['rate_discounted']:.1%} | odds ratio {rep['odds_ratio']:.2f} ({rep['lo']:.2f} to {rep['hi']:.2f}) |",
        "",
        f"**Break-even.** At a full-price gross margin of {100 * r['margin_full']:.1f}%, a 10% code needs baskets about "
        f"{100 * be[0.10]:.0f}% larger to earn the same profit, a 15% code {100 * be[0.15]:.0f}% larger and a 20% code "
        f"{100 * be[0.20]:.0f}% larger. The observed basket difference is {100 * b['diff'] / m.loc[False, 'basket']:+.1f}%.", "",
        "**Answer.** No. Discounted baskets are the same size as full-price ones, and those customers are no more",
        "likely to come back, so the codes gave away margin without buying extra volume or loyalty: about "
        f"**EUR {r['profit_given_away']:,.0f}** of gross profit over two years compared with the same orders at full price.", "",
        "**Assumptions and limitations.**", "",
        "- Observational data, not an experiment: customers chose to use a code. A randomised holdout (some",
        "  visitors are not offered the code) is the only clean way to measure incrementality.",
        "- The data has orders, not website sessions, so a code that persuades someone to buy *at all*",
        "  (conversion) is invisible here. The estimate assumes those orders would have happened anyway,",
        "  which overstates the cost if codes do convert hesitant visitors. That is the question to test next.",
        "- Order values are skewed; the t-tests are backed by a Mann-Whitney test and bootstrap intervals,",
        "  and with ~140k orders the sample means are close to normal.", "",
    ]


def run() -> tuple[list[tuple], list[str], dict]:
    with db.connect() as conn:
        o, f = load(conn)
    r = analyse(o, f)
    return test_rows(r), markdown(r), r


if __name__ == "__main__":
    rows, md, _ = run()
    print("\n".join(md))
