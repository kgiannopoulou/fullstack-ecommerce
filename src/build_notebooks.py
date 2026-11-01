"""Create and execute the two analysis notebooks (outputs are saved, so GitHub shows them).

    python src/build_notebooks.py

notebooks/exploratory_analysis.ipynb   first look at the clean data: what is in it, what stands out
notebooks/statistical_analysis.ipynb   the discount investigation, step by step

The notebooks are generated from this file so they stay reproducible: re-running the
pipeline and this script refreshes every number and chart.
"""
from __future__ import annotations

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

import config

SETUP = """import sys, pathlib
sys.path.insert(0, str(pathlib.Path.cwd().parent / "src"))
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import db

pd.set_option("display.float_format", "{:,.2f}".format)
plt.rcParams.update({"figure.figsize": (9, 3.2), "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e4e3df", "axes.axisbelow": True})
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#b9b8b3"
conn = db.connect()
sql = lambda q: db.query(conn, q)"""


def eda() -> nbformat.NotebookNode:
    md, code = new_markdown_cell, new_code_cell
    cells = [
        md("# Exploratory analysis\n\nA first look at the cleaned warehouse (`clean.*`) before any formal analysis: "
           "what the data contains, how it is distributed, and which questions it raises. Each question raised here is "
           "answered properly in `sql/` or `notebooks/statistical_analysis.ipynb`.\n\n"
           "Requires the pipeline to have run (`python src/pipeline.py`)."),
        code(SETUP),
        md("## 1. What is in the data?"),
        code("""sql('''
SELECT 'orders' AS table_name, count(*) AS rows, min(order_date)::text AS first, max(order_date)::text AS last FROM clean.orders
UNION ALL SELECT 'order lines', count(*), NULL, NULL FROM clean.order_items
UNION ALL SELECT 'customers', count(*), min(signup_date)::text, max(signup_date)::text FROM clean.customers
UNION ALL SELECT 'products', count(*), NULL, NULL FROM clean.products
UNION ALL SELECT 'stock snapshots', count(*), min(snapshot_date)::text, max(snapshot_date)::text FROM clean.inventory_daily''')"""),
        code("""sql('''SELECT status, count(*) AS orders, round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM clean.orders GROUP BY 1 ORDER BY 2 DESC''')"""),
        md("## 2. How are order values distributed?\n\nOrder values are right-skewed: most orders are small, a few are very "
           "large. That matters for every average reported later (mean vs median, and the bulk B2B orders)."),
        code("""o = sql("SELECT net_revenue::float AS v, units, has_bulk FROM clean.order_summary WHERE is_fulfilled")
print(o["v"].describe(percentiles=[.25, .5, .75, .95, .99]).round(2).to_string())
fig, ax = plt.subplots()
ax.hist(o.loc[o["v"] < o["v"].quantile(.99), "v"], bins=80, color=BLUE)
ax.axvline(o["v"].median(), color=ORANGE, lw=2, label=f"median EUR {o['v'].median():.0f}")
ax.axvline(o["v"].mean(), color="black", lw=1, ls="--", label=f"mean EUR {o['v'].mean():.0f}")
ax.set_title("Net order value (top 1% cut for readability)"); ax.legend(); plt.show()"""),
        md("## 3. Trend and seasonality"),
        code("""d = sql('''SELECT order_date::date AS day, sum(net_revenue)::float AS rev FROM clean.order_summary GROUP BY 1 ORDER BY 1''')
d["day"] = pd.to_datetime(d["day"])
fig, ax = plt.subplots()
ax.plot(d["day"], d["rev"], color=GREY, lw=0.6, label="daily")
ax.plot(d["day"], d["rev"].rolling(28).mean(), color=BLUE, lw=2, label="28-day average")
ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"EUR {x/1e3:.0f}k"))
ax.set_title("Daily net revenue"); ax.legend(); plt.show()"""),
        code("""w = sql('''SELECT to_char(order_date, 'ID Dy') AS weekday, round(avg(rev)) AS avg_revenue FROM
  (SELECT order_date, sum(net_revenue) AS rev FROM clean.order_summary GROUP BY 1) x GROUP BY 1 ORDER BY 1''')
w"""),
        md("**Questions raised:** growth looks steady with a strong November-December peak. Is the growth underlying or "
           "just the peak? (answered in `sql/03_revenue_trends.sql`, Q03.5). Black Friday days are clear outliers: the "
           "anomaly detection must not treat them as surprises."),
        md("## 4. Products: revenue vs profit"),
        code("""p = sql('''SELECT product_name, category, sum(net_revenue)::float AS revenue, sum(gross_profit)::float AS profit
FROM clean.sales_lines WHERE order_date >= '2025-01-01' GROUP BY 1, 2''')
p["margin"] = p["profit"] / p["revenue"]
p["share"] = p["revenue"].sort_values(ascending=False).cumsum() / p["revenue"].sum()
print(f"{(p['share'] <= 0.8).mean():.0%} of products produce 80% of revenue")
print("Spearman correlation of revenue rank and profit rank:",
      round(p['revenue'].rank().corr(p['profit'].rank(), method='spearman'), 3))
p.sort_values("revenue", ascending=False).head(10)"""),
        code("""fig, ax = plt.subplots(figsize=(9, 4))
q = p[p["revenue"] > 1000]
ax.scatter(q["revenue"], q["margin"], s=14, color=BLUE, alpha=.7)
ax.set_xscale("log"); ax.yaxis.set_major_formatter(mtick.PercentFormatter(1))
ax.set_xlabel("net revenue 2025 (log)"); ax.set_ylabel("gross margin"); ax.set_title("Revenue vs margin by product")
plt.show()"""),
        md("**Question raised:** revenue rank and profit rank are highly correlated overall, but some high-revenue products "
           "have low margins. Which, and why? (answered in `sql/12_profitability.sql`, Q12.4 - Q12.6)"),
        md("## 5. Customers"),
        code("""c = sql('''SELECT orders, count(*) AS customers FROM reporting.dim_customer WHERE orders IS NOT NULL
GROUP BY 1 ORDER BY 1''')
c["pct"] = 100 * c["customers"] / c["customers"].sum()
c.head(8)"""),
        code("""# lead() finds each customer's next order in one pass (a correlated EXISTS takes minutes here)
r = sql('''WITH o AS (SELECT customer_id, order_date,
    row_number() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS n,
    lead(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS next_order
  FROM clean.orders WHERE status <> 'cancelled' AND customer_id IS NOT NULL)
SELECT date_trunc('month', order_date)::date AS cohort,
       round(100.0 * avg(COALESCE(next_order - order_date <= 90, false)::int), 1) AS repeat_90d_pct
FROM o WHERE n = 1 AND order_date <= '2025-09-30' GROUP BY 1 ORDER BY 1''')
fig, ax = plt.subplots()
ax.plot(pd.to_datetime(r["cohort"]), r["repeat_90d_pct"], marker="o", color=BLUE)
ax.set_title("90-day repeat rate by month of first order"); ax.set_ylim(0); plt.show()"""),
        md("**Question raised:** a step change in March 2025. The loyalty programme launched then, but a courier change "
           "followed in May. Which one caused it? (answered in `sql/07_cohort_retention.sql`, Q07.3 - Q07.5, and tested in "
           "`reports/statistical_tests.md`)"),
        md("## 6. Discounts\n\nAbout one order in five uses a discount code. The natural question (does discounting pay?) "
           "needs care because codes cluster in November-December. It is the subject of `statistical_analysis.ipynb`."),
        code("""sql('''SELECT to_char(order_date, 'MM') AS month, round(100.0 * avg((discount_pct > 0)::int), 1) AS pct_orders_discounted
FROM clean.orders WHERE status <> 'cancelled' GROUP BY 1 ORDER BY 1''').T"""),
    ]
    return new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})


def stats_nb() -> nbformat.NotebookNode:
    md, code = new_markdown_cell, new_code_cell
    cells = [
        md("# Statistical investigation: did discounting pay for itself?\n\n"
           "**Business question.** Discount codes (10-25% off) are used on about one order in five. Marketing believes "
           "they drive sales. Did they increase sales enough to justify the margin they give away?\n\n"
           "**What 'paying for itself' would require.** A discount reduces the profit of every order that uses it. To break "
           "even, discounted orders would need to be *bigger* (more items, higher basket), or the customers would need to "
           "*come back more often*. Both are testable.\n\n"
           "**Plan.**\n1. Describe discounted vs full-price orders.\n2. Check for confounding (when are codes used?).\n"
           "3. Compare basket size within the same month, with confidence intervals.\n4. Compare repeat purchasing, "
           "stratified by month.\n5. Break-even arithmetic.\n6. Conclusion, assumptions and limitations."),
        code(SETUP + "\nfrom scipy import stats\nimport discount_analysis as da"),
        md("## 1. Describe"),
        code("""o, f = da.load(conn)
o.groupby("disc")[["units", "basket", "net_revenue", "gross_profit"]].agg(["mean", "median", "count"]).T"""),
        md("At first sight discounted orders have the same basket but much lower profit. Before believing it, check "
           "whether the two groups are comparable."),
        md("## 2. Confounding: codes are not used at random"),
        code("""share = o.groupby(o["month"].dt.month)["disc"].mean()
fig, ax = plt.subplots()
ax.bar(share.index, share.values, color=BLUE)
ax.yaxis.set_major_formatter(mtick.PercentFormatter(1)); ax.set_xticks(range(1, 13))
ax.set_title("Share of orders using a discount code, by calendar month"); plt.show()"""),
        md("Codes are used about twice as often in November and December, when baskets are different (gifts, Black "
           "Friday). Comparing all discounted orders with all full-price orders would mix the discount effect with the "
           "season. So every comparison below is made **within the same month** and then averaged, weighted by the "
           "number of discounted orders."),
        md("## 3. Basket size: within-month difference with a bootstrap confidence interval"),
        code("""res = da.analyse(o, f)
pd.DataFrame({k: res[k] for k in ("units", "basket", "gross_profit")}).T[["diff", "lo", "hi", "months_higher", "months"]]"""),
        code("""print("Mann-Whitney U, units per order: p =", round(res["p_units"], 3))
print("Welch t-test, basket before discount: t = %.2f, p = %.3f" % (res["t_basket"], res["p_basket"]))
print("Welch t-test, gross profit per order: t = %.1f, p = %.2g" % (res["t_gp"], res["p_gp"]))"""),
        md("The confidence intervals for units per order and basket value both include zero: there is no evidence that "
           "a code makes customers buy more. Gross profit per order is lower in every one of the 24 months. Order "
           "values are skewed, so the t-test on the basket is backed up by a rank-based test and bootstrap intervals "
           "(with this many orders the sample means are close to normal anyway)."),
        md("## 4. Do discounted first orders create loyal customers?\n\nIf codes brought in customers who then came back, "
           "the lost margin could be an acquisition cost worth paying. Compare the 90-day repeat rate of first-time buyers "
           "with and without a code, again stratified by month (Cochran-Mantel-Haenszel)."),
        code("""rep = res["repeat"]
print(f"90-day repeat: full price {rep['rate_full_price']:.1%}, discounted {rep['rate_discounted']:.1%}")
print(f"common odds ratio {rep['odds_ratio']:.2f} (95% CI {rep['lo']:.2f} to {rep['hi']:.2f}), CMH chi2 = {rep['chi2']:.1f}, p = {rep['p']:.3f}")"""),
        md("The odds ratio is slightly *below* 1 and its confidence interval reaches 1: discounted first-time buyers are "
           "not more likely to return, if anything a little less."),
        md("## 5. Break-even"),
        code("""m = res["margin_full"]
pd.DataFrame({"discount": list(res["break_even_lift"]),
              "basket increase needed to keep the same profit": [f"{v:.0%}" for v in res["break_even_lift"].values()]})"""),
        code("""print(f"Observed basket difference: {res['basket']['diff'] / res['mean'].loc[False, 'basket']:+.1%}")
print(f"Gross profit given away vs the same orders at full price: EUR {res['profit_given_away']:,.0f}")"""),
        md("## 6. Conclusion\n\n**No: in this data, discount codes did not pay for themselves.** Discounted baskets are the "
           "same size as full-price ones, customers who start with a code are no more loyal, and the codes cost the "
           "margin shown above.\n\n**Recommendation.** Stop blanket codes. Test targeted offers (for example on "
           "overstocked products, or a second-order incentive) against a randomised hold-out group before rolling them out.\n\n"
           "**Assumptions and limitations.**\n- Observational data: customers chose to use a code. Only a randomised "
           "hold-out measures true incrementality.\n- Orders only, no website sessions: if a code persuades someone to buy "
           "*at all*, that conversion effect is invisible here, so the cost above is an upper bound.\n- Month "
           "stratification removes seasonality, but not every possible difference between code users and other customers."),
    ]
    return new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})


def main():
    nb_dir = config.ROOT / "notebooks"
    nb_dir.mkdir(exist_ok=True)
    for name, nb in (("exploratory_analysis", eda()), ("statistical_analysis", stats_nb())):
        ExecutePreprocessor(timeout=900, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(nb_dir)}})
        nbformat.write(nb, nb_dir / f"{name}.ipynb")
        print(f"wrote notebooks/{name}.ipynb")


if __name__ == "__main__":
    main()
