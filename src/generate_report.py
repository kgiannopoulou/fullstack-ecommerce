"""Generate the management outputs: alerts, charts and the executive PDF.

Every number in the report is read from the pipeline's own outputs
(reports/output/*.csv, data/cleaned/*.csv), so re-running the pipeline
rewrites the report with the new figures. The wording is written for a
manager: what happened, why, and what to do - not how it was computed
(that is in docs/methodology.md).

Outputs: data/cleaned/ManagementAlerts.csv, reports/figures/*.png,
         reports/Executive_Analysis_Report.pdf

    python src/generate_report.py
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from PIL import Image as PILImage
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

import config
import transform

# Reference categorical palette (validated: first three slots pass all-pairs CVD checks).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, CONTEXT = "#0b0b0b", "#52514e", "#e4e3df", "#b9b8b3"
WARN = "#c25400"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": CONTEXT, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.titleweight": "bold", "axes.titlesize": 10, "axes.titlecolor": INK, "axes.titlelocation": "left",
    "legend.frameon": False, "savefig.dpi": 200, "savefig.bbox": "tight",
})
EUR_K = mtick.FuncFormatter(lambda x, _: f"€{x / 1e3:,.0f}k")
EUR_M = mtick.FuncFormatter(lambda x, _: f"€{x / 1e6:,.1f}M")


def q(qid: str) -> pd.DataFrame:
    return pd.read_csv(config.OUTPUT_DIR / f"{qid}.csv")


def eur(x: float, d: int = 0) -> str:
    if abs(x) >= 1e6:
        return f"€{x / 1e6:,.2f}M"
    if abs(x) >= 1e4:
        return f"€{x / 1e3:,.0f}k"
    return f"€{x:,.{d}f}"


# ------------------------------------------------------------------ facts --
def collect() -> dict:
    """Every number the report quotes, in one place."""
    f = {}
    kp = q("Q02.2").set_index("metric")
    pb = q("Q12.1").set_index("period")
    f["rev24"], f["rev25"] = pb.loc["2024", "net_revenue"], pb.loc["2025", "net_revenue"]
    f["gp24"], f["gp25"] = pb.loc["2024", "gross_profit"], pb.loc["2025", "gross_profit"]
    f["gm24"], f["gm25"] = pb.loc["2024", "gross_margin_pct"], pb.loc["2025", "gross_margin_pct"]
    f["ship24"], f["ship25"] = pb.loc["2024", "shipping_pct_of_revenue"], pb.loc["2025", "shipping_pct_of_revenue"]
    f["cogs24"], f["cogs25"] = pb.loc["2024", "cogs_pct_of_revenue"], pb.loc["2025", "cogs_pct_of_revenue"]
    f["bridge25"] = pb.loc["2025"]
    f["orders24"], f["orders25"] = kp.loc["Fulfilled orders", "y2024"], kp.loc["Fulfilled orders", "y2025"]
    f["aov24"], f["aov25"] = kp.loc["Average order value", "y2024"], kp.loc["Average order value", "y2025"]
    f["cust24"], f["cust25"] = kp.loc["Active customers", "y2024"], kp.loc["Active customers", "y2025"]
    f["refund24"], f["refund25"] = kp.loc["Refund rate %", "y2024"], kp.loc["Refund rate %", "y2025"]
    mix = q("Q03.8").set_index("yr")
    f["lfl_price"] = mix.loc[2025, "like_for_like_price_change_pct"]
    f["lowprice24"], f["lowprice25"] = mix.loc[2024, "low_price_category_share_pct"], mix.loc[2025, "low_price_category_share_pct"]

    quad = q("Q12.6").set_index("quadrant")
    f["vt"] = quad.loc["Volume traps"]
    f["stars"] = quad.loc["Stars"]
    drops = q("Q12.4")
    f["drops"] = drops
    f["loss_makers"] = q("Q12.7")
    cat = q("Q12.3")
    f["cat"] = cat
    f["courier"] = q("Q12.9").set_index("courier")
    f["markets"] = q("Q12.10")

    st = pd.read_csv(config.OUTPUT_DIR / "statistical_tests.csv")
    f["tests"] = st
    d = q("Q12.8").set_index("discount_code")
    f["disc"] = d

    f["repeat"] = q("Q05.1").iloc[0]
    f["decomp"] = q("Q07.5").iloc[0]
    rfm = q("Q06.2").set_index("segment")
    f["rfm"] = rfm
    f["at_risk_cust"] = rfm.loc[["At Risk", "Cannot Lose Them"], "pct_customers"].sum()
    f["at_risk_rev"] = rfm.loc[["At Risk", "Cannot Lose Them"], "pct_revenue"].sum()
    f["channels"] = q("Q05.5")

    f["abc_stockouts"] = q("Q08.4").set_index("abc_class")
    f["inv_status"] = q("Q08.2").set_index("stock_status")
    fc = pd.read_csv(config.CLEAN_DIR / "InventoryForecast.csv")
    f["fc"] = fc
    f["fc_risky"] = fc[fc["risk"].isin(["STOCKOUT BEFORE RESTOCK", "REORDER NOW"])]
    f["backtest"] = pd.read_csv(config.REPORTS_DIR / "forecast_backtest.csv")
    f["anomaly"] = q("Q10.7").iloc[0]
    f["anomaly_sku"] = q("Q10.8").iloc[0]
    f["on_time"] = q("Q09.2").set_index("courier")
    f["cod"] = q("Q02.4")
    f["dq"] = pd.read_csv(config.REPORTS_DIR / "data_quality_scorecard.csv").set_index("stage")
    f["defects"] = q("Q01.11").iloc[0]
    f["alerts"] = pd.read_csv(config.CLEAN_DIR / "ManagementAlerts.csv")
    f["monthly"] = q("Q11.2")
    return f


# ----------------------------------------------------------------- charts --
def save(fig, name: str) -> str:
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FIGURES_DIR / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    return str(path)


def chart_monthly(f) -> str:
    m = f["monthly"].assign(month=lambda d: pd.to_datetime(d["month"]))
    fig, ax = plt.subplots(figsize=(7.2, 2.2))
    ax.plot(m["month"], m["net_revenue"], color=BLUE, lw=2, label="Net revenue")
    ax.plot(m["month"], m["gross_profit"], color=ORANGE, lw=2, label="Gross profit")
    for col, c in (("net_revenue", BLUE), ("gross_profit", ORANGE)):
        ax.annotate(eur(m[col].iloc[-1]), (m["month"].iloc[-1], m[col].iloc[-1]), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=8, color=INK)
    ax.yaxis.set_major_formatter(EUR_K)
    ax.set_title("Net revenue and gross profit by month")
    ax.legend(loc="upper left", ncols=2)
    ax.set_ylim(0)
    return save(fig, "monthly_revenue_profit")


def chart_bridge(f) -> str:
    b = f["bridge25"]
    steps = [("Gross sales", b.gross_sales), ("Discounts", -b.discounts), ("Refunds", -b.refunds),
             ("Net revenue", b.net_revenue), ("Cost of goods", -b.cogs), ("Shipping", -b.shipping_cost),
             ("Gross profit", b.gross_profit)]
    fig, ax = plt.subplots(figsize=(7.2, 2.3))
    run = 0
    for i, (name, v) in enumerate(steps):
        total = name in ("Gross sales", "Net revenue", "Gross profit")
        bottom = 0 if total else (run + v if v < 0 else run)
        ax.bar(i, abs(v), bottom=bottom, width=0.62, color=BLUE if total else CONTEXT,
               edgecolor="white", linewidth=1)
        ax.text(i, bottom + abs(v) + b.gross_sales * 0.015, eur(v) if total else f"−{eur(-v)}",
                ha="center", fontsize=8, color=INK)
        run = v if total else run + v
    ax.set_xticks(range(len(steps)), [s for s, _ in steps])
    ax.yaxis.set_major_formatter(EUR_M)
    ax.grid(axis="x", visible=False)
    ax.set_title("2025: from list-price sales to gross profit")
    return save(fig, "profit_bridge_2025")


def chart_scatter(f) -> str:
    p = q("Q12.5")
    p = p[p["net_revenue"] > 1000]
    trap = p["quadrant"].str.startswith("Volume traps")
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    ax.scatter(p.loc[~trap, "net_revenue"], p.loc[~trap, "gross_margin_pct"], s=16, color=CONTEXT,
               edgecolor="white", linewidth=0.6, label="Other products")
    ax.scatter(p.loc[trap, "net_revenue"], p.loc[trap, "gross_margin_pct"], s=22, color=ORANGE,
               edgecolor="white", linewidth=0.6, label="Volume traps: high revenue, low margin")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(EUR_K)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    med_m = p["gross_margin_pct"].median()
    ax.axhline(med_m, color=MUTED, lw=0.8, ls="--")
    for r in f["drops"].head(3).itertuples():
        row = p[p["product_name"] == r.product_name]
        if len(row):
            ax.annotate(r.product_name, (row["net_revenue"].iloc[0], row["gross_margin_pct"].iloc[0]),
                        xytext=(6, -10), textcoords="offset points", fontsize=7.5, color=INK)
    ax.set_xlabel("Net revenue 2025 (log scale)")
    ax.set_ylabel("Gross margin")
    ax.set_title("Revenue vs gross margin, every product (2025)")
    ax.legend(loc="lower right", fontsize=8)
    return save(fig, "revenue_vs_margin")


def chart_discount(f) -> str:
    d = f["disc"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.0))
    x = range(len(d))
    axes[0].bar(x, d["units_per_order"], color=BLUE, width=0.6)
    axes[0].set_title("Units per order")
    axes[0].set_ylim(0, d["units_per_order"].max() * 1.25)
    axes[1].bar(x, d["avg_gross_profit_per_order"], color=[BLUE] + [ORANGE] * (len(d) - 1), width=0.6)
    axes[1].set_title("Gross profit per order")
    axes[1].yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"€{v:,.0f}"))
    for ax, col, fmt in ((axes[0], "units_per_order", "{:.2f}"), (axes[1], "avg_gross_profit_per_order", "€{:.0f}")):
        ax.set_xticks(list(x), ["no code" if c == "0%" else c for c in d.index])
        ax.grid(axis="x", visible=False)
        for i, v in enumerate(d[col]):
            ax.text(i, v * 1.02, fmt.format(v), ha="center", fontsize=8, color=INK)
    fig.suptitle("Discount codes: same basket, less profit", x=0.01, ha="left", fontweight="bold", fontsize=10)
    fig.tight_layout()
    return save(fig, "discount_effect")


def chart_retention(f) -> str:
    r = q("Q07.2")
    fig, ax = plt.subplots(figsize=(7.2, 2.1))
    x = np.arange(len(r))
    ax.plot(x, r["repeat_90d_2024_pct"], color=CONTEXT, lw=2, marker="o", ms=4, label="First order in 2024")
    ax.plot(x, r["repeat_90d_2025_pct"], color=BLUE, lw=2, marker="o", ms=4, label="First order in 2025")
    i = r.index[r["cohort_month"] == "Mar"][0]
    ax.annotate("Loyalty programme\nlaunched 1 March", (i, r.loc[i, "repeat_90d_2025_pct"]), xytext=(-70, 6),
                textcoords="offset points", fontsize=8, color=INK, arrowprops={"arrowstyle": "-", "color": MUTED})
    ax.set_xticks(x, r["cohort_month"])
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.set_ylim(15, 50)
    ax.set_title("Customers who order again within 90 days, by month of first order")
    ax.legend(loc="lower right")
    return save(fig, "repeat_rate")


def chart_rfm(f) -> str:
    r = f["rfm"].sort_values("pct_revenue")
    fig, ax = plt.subplots(figsize=(7.2, 2.5))
    y = np.arange(len(r))
    ax.barh(y + 0.2, r["pct_customers"], height=0.38, color=CONTEXT, label="% of customers")
    ax.barh(y - 0.2, r["pct_revenue"], height=0.38, color=BLUE, label="% of revenue")
    ax.set_yticks(y, r.index)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.grid(axis="y", visible=False)
    for lab in ax.get_yticklabels():
        if lab.get_text() in ("At Risk", "Cannot Lose Them"):
            lab.set_color(WARN); lab.set_fontweight("bold")
    ax.set_title("Customer segments (RFM): share of customers vs share of revenue")
    ax.legend(loc="lower right")
    return save(fig, "rfm_segments")


def chart_stock(f) -> str:
    r = f["fc_risky"].sort_values("revenue_at_risk_30d", ascending=False).head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 2.5))
    y = np.arange(len(r))
    ax.barh(y + 0.2, r["forecast_30d"], height=0.38, color=CONTEXT, label="Forecast demand, next 30 days")
    ax.barh(y - 0.2, r["stock"], height=0.38, color=BLUE, label="Stock on hand, 31 Dec")
    ax.set_yticks(y, [f"{n} ({c})" for n, c in zip(r["product_name"], r["abc_class"])])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Units")
    ax.set_title("Largest stockout risks: stock vs 30-day forecast")
    ax.legend(loc="lower right", fontsize=8)
    return save(fig, "stockout_risk")


def chart_anomaly(f) -> str:
    a = q("Q10.6").assign(day=lambda d: pd.to_datetime(d["day"]))
    fig, ax = plt.subplots(figsize=(7.2, 2.3))
    ax.plot(a["day"], a["expected"], color=CONTEXT, lw=2, ls="--", label="Expected (same weekday, 8-week average)")
    ax.plot(a["day"], a["revenue"], color=BLUE, lw=2, label="Actual Wearables revenue")
    ax.axvline(pd.Timestamp("2025-01-01"), color=WARN, lw=1)
    ax.annotate("Fitness Band O174 sells out 31 Dec;\nno further deliveries", (pd.Timestamp("2025-01-01"), a["expected"].max()),
                xytext=(6, -4), textcoords="offset points", fontsize=8, color=INK, va="top")
    ax.yaxis.set_major_formatter(EUR_K)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.set_ylim(0)
    ax.set_title("Alert investigated: Wearables revenue, Dec 2024 - Jan 2025")
    ax.legend(loc="lower left", fontsize=8)
    return save(fig, "anomaly_wearables")


def chart_dashboard(f) -> str:
    """A one-image preview of the Executive Overview page for the README, drawn from the same data
    (the interactive dashboard is the Power BI project in powerbi/)."""
    m = f["monthly"].assign(month=lambda d: pd.to_datetime(d["month"]))
    m25, m24 = m[m["month"].dt.year == 2025], m[m["month"].dt.year == 2024]
    fig = plt.figure(figsize=(12.8, 7.2), facecolor="#F7F7F5")
    gs = fig.add_gridspec(3, 4, height_ratios=[0.62, 1.25, 1.25], hspace=0.55, wspace=0.28,
                          left=0.04, right=0.98, top=0.88, bottom=0.07)
    fig.text(0.04, 0.95, "E-Commerce Performance Dashboard · Executive Overview · 2025", fontsize=16, fontweight="bold", color=INK)
    fig.text(0.04, 0.915, "Preview rendered from the pipeline's data. Interactive version: Power BI project in powerbi/",
             fontsize=9, color=MUTED)

    def yoy(a, b):
        return f"{'+' if b >= a else '−'}{abs(100 * (b / a - 1)):.1f}% YoY"
    tiles = [("NET REVENUE", eur(f["rev25"]), yoy(f["rev24"], f["rev25"])),
             ("GROSS PROFIT", eur(f["gp25"]), yoy(f["gp24"], f["gp25"])),
             ("ORDERS", f"{f['orders25']:,.0f}", yoy(f["orders24"], f["orders25"])),
             ("AOV", f"€{f['aov25']:.2f}", yoy(f["aov24"], f["aov25"]))]
    for i, (lab, val, ch) in enumerate(tiles):
        ax = fig.add_subplot(gs[0, i]); ax.axis("off")
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, color="white", ec=GRID, lw=1))
        ax.text(0.06, 0.8, lab, fontsize=9, color=MUTED, transform=ax.transAxes)
        ax.text(0.06, 0.36, val, fontsize=21, fontweight="bold", color=INK, transform=ax.transAxes)
        ax.text(0.06, 0.1, ch, fontsize=10, ha="left", color="#0a7d3b" if not ch.startswith("−") else WARN,
                transform=ax.transAxes)

    ax = fig.add_subplot(gs[1, :2])
    ax.plot(m25["month"].dt.month, m25["net_revenue"], color=BLUE, lw=2, marker="o", ms=3, label="2025")
    ax.plot(m24["month"].dt.month, m24["net_revenue"], color=CONTEXT, lw=2, label="2024")
    ax.set_xticks(range(1, 13), list("JFMAMJJASOND")); ax.yaxis.set_major_formatter(EUR_K)
    ax.set_title("Monthly net revenue vs last year"); ax.legend(loc="upper left")

    ax = fig.add_subplot(gs[1, 2:])
    ax.plot(m["month"], m["gross_margin_pct"], color=ORANGE, lw=2)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0)); ax.set_ylim(35, 42)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.set_title("Gross margin trend (after COGS and shipping)")

    ax = fig.add_subplot(gs[2, 0])
    c = f["cat"].head(6).iloc[::-1]
    ax.barh(c["category"], c["net_revenue"], color=BLUE, height=0.6)
    ax.xaxis.set_major_formatter(EUR_M); ax.set_title("Revenue by category (top 6)"); ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", labelsize=7.5)

    ct = pd.read_csv(config.CLEAN_DIR / "CustomerTypeMonthly.csv")
    ct["year"] = pd.to_datetime(ct["month"]).dt.year
    ct = ct[ct["customer_type"] != "Guest"].groupby(["year", "customer_type"])["net_revenue"].sum().unstack()
    ax = fig.add_subplot(gs[2, 1])
    x = np.arange(len(ct))
    ax.bar(x - 0.2, ct["New"], 0.38, color=CONTEXT, label="New")
    ax.bar(x + 0.2, ct["Returning"], 0.38, color=BLUE, label="Returning")
    ax.set_xticks(x, ct.index); ax.yaxis.set_major_formatter(EUR_M); ax.grid(axis="x", visible=False)
    ax.set_ylim(0, ct.to_numpy().max() * 1.3)
    ax.set_title("New vs returning customers"); ax.legend(fontsize=8, loc="upper left", ncols=2)

    ax = fig.add_subplot(gs[2, 2:]); ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, color="white", ec=GRID, lw=1))
    ax.text(0.03, 0.88, "Management alerts", fontsize=10, fontweight="bold", color=INK, transform=ax.transAxes)
    sym = {"warning": ("!", WARN), "positive": ("+", "#0a7d3b"), "info": ("i", MUTED)}
    for i, r in enumerate(f["alerts"].head(5).itertuples()):
        s, col_ = sym[r.severity]
        y = 0.70 - i * 0.16
        ax.text(0.03, y, s, fontsize=10, fontweight="bold", color=col_, transform=ax.transAxes)
        ax.text(0.07, y, r.alert.replace("EUR ", "€").replace(" -> ", " → ").replace(", the usual Q4 discount dip", ""), fontsize=8.4, color=INK,
                transform=ax.transAxes)
    return save(fig, "dashboard_executive_overview")


# -------------------------------------------------------------------- PDF --
def styles():
    ss = getSampleStyleSheet()
    base = ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13.5,
                          textColor=colors.HexColor(INK), spaceAfter=5, alignment=TA_LEFT)
    return {
        "title": ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base, textColor=colors.HexColor(MUTED), fontSize=9.5, spaceAfter=10),
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=18, spaceBefore=4,
                             spaceAfter=6, textColor=colors.HexColor("#1F3864")),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=6,
                             spaceAfter=3),
        "body": base,
        "bullet": ParagraphStyle("b", parent=base, leftIndent=12, bulletIndent=2, spaceAfter=3),
        "small": ParagraphStyle("sm", parent=base, fontSize=8, leading=10.5, textColor=colors.HexColor(MUTED)),
        "rec": ParagraphStyle("r", parent=base, backColor=colors.HexColor("#EEF4FB"), borderPadding=(5, 6, 5, 6),
                              spaceBefore=4, spaceAfter=8, leftIndent=2, rightIndent=2),
    }


def table(rows, widths, right=(), header=True, zebra=True):
    """right: indexes of numeric columns (right-aligned); text columns stay left-aligned."""
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    st = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.5), ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(INK)),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
          ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor(CONTEXT))]
    st += [("ALIGN", (c, 0), (c, -1), "RIGHT") for c in right]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5)]
    if zebra:
        for i in range(1 if header else 0, len(rows)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F5F5F3")))
    t.setStyle(TableStyle(st))
    return t


def kpi_tiles(f, s):
    def tile(label, value, change):
        good = not change.startswith("−")
        return [Paragraph(f'<font size="7.5" color="{MUTED}">{label}</font>', s["body"]),
                Paragraph(f'<font size="15"><b>{value}</b></font>', s["body"]),
                Paragraph(f'<font size="8" color="{"#0a7d3b" if good else WARN}">{change}</font>', s["body"])]

    def pct(a, b):
        v = 100 * (b / a - 1)
        return f"{'+' if v >= 0 else '−'}{abs(v):.1f}% vs 2024"

    tiles = [
        tile("NET REVENUE 2025", eur(f["rev25"]), pct(f["rev24"], f["rev25"])),
        tile("GROSS PROFIT", eur(f["gp25"]), pct(f["gp24"], f["gp25"])),
        tile("GROSS MARGIN", f"{f['gm25']:.1f}%", f"{'+' if f['gm25'] >= f['gm24'] else '−'}{abs(f['gm25'] - f['gm24']):.1f}pp vs 2024"),
        tile("ORDERS", f"{f['orders25']:,.0f}", pct(f["orders24"], f["orders25"])),
        tile("AVG ORDER VALUE", f"€{f['aov25']:.2f}", pct(f["aov24"], f["aov25"])),
    ]
    cols = [[t[i] for t in tiles] for i in range(3)]
    t = Table(cols, colWidths=[3.4 * cm] * 5, hAlign="LEFT")
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(CONTEXT)),
                           ("LINEAFTER", (0, 0), (-2, -1), 0.5, colors.HexColor(CONTEXT)),
                           ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAF8")),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    return t


def build_pdf(f, figs):
    s = styles()
    doc = SimpleDocTemplate(str(config.REPORTS_DIR / "Executive_Analysis_Report.pdf"), pagesize=A4,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            title="Executive Analysis Report: E-Commerce Performance 2024-2025",
                            author="Konstantina Giannopoulou")
    W = A4[0] - 3.6 * cm
    def img(key, _h=None, width=W):
        w, h = PILImage.open(figs[key]).size        # keep the chart's aspect ratio
        return Image(figs[key], width=width, height=width * h / w)
    P = lambda text, st="body": Paragraph(text, s[st])
    story = []

    vt, stars, dec = f["vt"], f["stars"], f["decomp"]
    disc_gp_none = f["disc"].loc["0%", "avg_gross_profit_per_order"]
    disc_rows = f["tests"][f["tests"]["claim"].str.contains("discount", case=False)]
    d = f["disc"]
    gp_given = ((disc_gp_none - d["avg_gross_profit_per_order"]) * d["orders"]).iloc[1:].sum()
    risky, fc = f["fc_risky"], f["fc"]
    risky_a = risky[risky["abc_class"] == "A"]
    abc = f["abc_stockouts"].loc["A"]
    over = f["inv_status"].loc["OVERSTOCK"]
    an, sku = f["anomaly"], f["anomaly_sku"]
    cour = f["courier"]
    ship_delta = cour.loc["SwiftCourier", "avg_shipping_cost"] - cour.loc["ELTA Courier", "avg_shipping_cost"]
    big = f["drops"][f["drops"]["rank_drop"] >= 15].sort_values("revenue_rank")
    worst = big.iloc[0] if len(big) else f["drops"].iloc[0]          # a high-revenue product with a large drop
    second = f["drops"][f["drops"]["product_name"] != worst.product_name].iloc[0]
    rev_growth = 100 * (f["rev25"] / f["rev24"] - 1)
    gp_growth = 100 * (f["gp25"] / f["gp24"] - 1)
    late = f["tests"][f["tests"]["claim"].str.startswith("A late first delivery")].iloc[0]

    # ---- page 1: executive summary ----
    story += [P("Executive Analysis Report", "title"),
              P("E-commerce performance, January 2024 to December 2025 · prepared for the Head of Operations · "
                f"data: {f['defects'].raw_records:,.0f} transaction records", "sub"),
              kpi_tiles(f, s), Spacer(1, 10), P("Executive summary", "h1")]
    story += [
        P(f"<b>The business grew strongly and profitably.</b> Net revenue rose {rev_growth:.1f}% to {eur(f['rev25'])} and "
          f"gross profit {gp_growth:.1f}% to {eur(f['gp25'])}. Gross margin held at {f['gm25']:.1f}% "
          f"({f['gm25'] - f['gm24']:+.1f}pp) even though shipping costs rose from {f['ship24']:.1f}% to {f['ship25']:.1f}% "
          "of revenue, because list-price increases offset the more expensive courier."),
        P(f"<b>Revenue is a misleading guide to which products matter.</b> {int(vt.products)} high-revenue products earn "
          f"{vt.revenue_share_pct:.0f}% of revenue but only {vt.profit_share_pct:.0f}% of gross profit, at a {vt.gross_margin_pct:.0f}% margin "
          f"against {stars.gross_margin_pct:.0f}% for the best products. {worst.product_name} ranks #{worst.revenue_rank} by revenue but "
          f"#{worst.profit_rank} by profit."),
        P(f"<b>Discount codes did not pay for themselves.</b> Discounted orders contain the same number of items as "
          f"full-price orders but earn €{disc_gp_none - (d['avg_gross_profit_per_order'].iloc[1:] * d['orders'].iloc[1:]).sum() / d['orders'].iloc[1:].sum():.0f} "
          f"less gross profit each: about {eur(gp_given)} given away over two years with no measurable gain in volume or loyalty."),
        P(f"<b>Customers come back far more often since the loyalty programme.</b> The share of new customers who order "
          f"again within 90 days rose from {dec.repeat_90d_before_pct:.1f}% to {dec.repeat_90d_after_pct:.1f}%: "
          f"{dec.loyalty_effect_pp:+.1f}pp from the programme and {dec.delivery_effect_pp:+.1f}pp from faster delivery."),
        P(f"<b>Stock availability is the most urgent operational risk.</b> {len(risky)} products need reordering today, "
          f"{len(risky_a)} of them A-class best-sellers, with {eur(risky['revenue_at_risk_30d'].sum())} of revenue at risk "
          f"in January. In 2025, {int(abc.with_3plus_stockout_episodes)} A-class products ran out three or more times, costing an estimated "
          f"{eur(abc.their_est_lost_revenue)} in lost sales."),
        P("Top recommendations", "h2"),
    ]
    recs_short = [
        f"Order the {len(risky)} at-risk products today and raise safety stock on the {int(abc.with_3plus_stockout_episodes)} "
        "repeatedly out-of-stock A-class products.",
        "Rank products by gross profit, not revenue, in category reviews; re-price or re-source the volume-trap products.",
        "Stop blanket discount codes; test targeted offers against a hold-out group before rolling them out.",
        f"Keep the loyalty programme and target the {f['at_risk_cust']:.1f}% of customers in the At Risk / Cannot Lose Them "
        f"segments ({f['at_risk_rev']:.1f}% of revenue) with a win-back campaign.",
    ]
    story += [Paragraph(r, s["bullet"], bulletText="•") for r in recs_short]
    story.append(PageBreak())

    # ---- page 2: business performance ----
    b = f["bridge25"]
    story += [P("1. Business performance", "h1"), img("monthly", 6.6 * cm),
              P(f"Revenue grew in every quarter, and growth was not a Black Friday effect: rolling 90-day revenue was up "
                f"between 26% and 28% year on year in both halves of 2025. Orders grew faster ({100 * (f['orders25'] / f['orders24'] - 1):.1f}%) "
                f"than revenue, so the average order value fell from €{f['aov24']:.2f} to €{f['aov25']:.2f}. That fall is "
                f"<b>product mix, not pricing</b>: the same products cost {f['lfl_price']:.1f}% more in 2025, but cheaper categories "
                f"grew from {f['lowprice24']:.1f}% to {f['lowprice25']:.1f}% of revenue."),
              img("bridge", 6.8 * cm),
              P(f"Of every €100 of list-price sales in 2025, €{100 * b.discounts / b.gross_sales:.0f} went in discounts and "
                f"€{100 * b.refunds / b.gross_sales:.0f} in refunds. Cost of goods takes {f['cogs25']:.0f}% of net revenue and "
                f"shipping {f['ship25']:.1f}%, leaving a gross margin of {f['gm25']:.1f}%. Shipping is the cost growing fastest: the faster "
                f"courier for Greece costs €{ship_delta:.2f} more per order (€{cour.loc['ELTA Courier', 'avg_shipping_cost']:.2f} to "
                f"€{cour.loc['SwiftCourier', 'avg_shipping_cost']:.2f}), in exchange for on-time delivery rising from "
                f"{cour.loc['ELTA Courier', 'on_time_pct']:.0f}% to {cour.loc['SwiftCourier', 'on_time_pct']:.0f}%."),
              P(f"<b>Recommendation:</b> report gross profit next to revenue in the monthly pack, and AOV next to units per "
                f"order, so that a falling AOV is not mistaken for discounting.", "rec"),
              PageBreak()]

    # ---- page 3: products & profitability ----
    rows = [["Product", "Revenue rank", "Profit rank", "Margin", "Main reason"]]
    for r in f["drops"].head(6).itertuples():
        rows.append([r.product_name, f"#{r.revenue_rank}", f"#{r.profit_rank}", f"{r.gross_margin_pct:.0f}%", r.main_driver])
    story += [P("2. Products and profitability", "h1"),
              P("The product review used to rank products by revenue. After adding unit cost, discounts, refunds and the "
                "shipping each product causes, that ranking turned out to be misleading, so gross profit is now the KPI "
                "for product decisions."),
              img("scatter", 7.6 * cm),
              P(f"{int(vt.products)} products sit in the 'volume trap' corner: above-median revenue, below-median margin. They are "
                f"{vt.revenue_share_pct:.0f}% of 2025 revenue but {vt.profit_share_pct:.0f}% of gross profit. Two causes dominate: a "
                f"high unit cost (low markup) and, for bulky items, shipping. {second.product_name} drops from #{second.revenue_rank} "
                f"by revenue to #{second.profit_rank} by profit; Home &amp; Kitchen and Fitness lose "
                f"{f['cat'].set_index('category').loc['Home & Kitchen', 'shipping_pct']:.0f}% and "
                f"{f['cat'].set_index('category').loc['Fitness', 'shipping_pct']:.0f}% of their revenue to shipping alone. "
                f"{len(f['loss_makers'])} products lost money on every sale in 2025."),
              table(rows, [5.4 * cm, 2.1 * cm, 2.0 * cm, 1.6 * cm, 6.3 * cm], right=(1, 2, 3)),
              Spacer(1, 6),
              KeepTogether([P("Did discounting pay for itself?", "h2"), img("discount", 5.3 * cm),
                            P(f"About one order in five used a 10-25% code. Compared within the same month (codes cluster in "
                              f"November-December), discounted orders held no more items "
                              f"({disc_rows.iloc[0].result.split(';')[1].strip().replace('within-month diff', 'difference')} items per order), "
                              "and first-time buyers who used a code were no more likely to return. At a 41% margin a 15% code "
                              "needs baskets ~57% larger to break even; the observed difference is under 1%.")]),
              P("<b>Recommendation:</b> review price or supplier cost for the volume-trap products, add a minimum order value "
                "or shipping charge for bulky low-price items, and replace blanket codes with targeted offers tested "
                "against a hold-out group.", "rec"),
              PageBreak()]

    # ---- page 4: customers ----
    rfm = f["rfm"]
    rep = f["repeat"]
    ch = f["channels"].set_index(f["channels"].columns[0])
    story += [P("3. Customer insights", "h1"),
              P(f"{rep.repeat_customer_rate_pct:.1f}% of customers have ordered more than once, and they generate "
                f"{rep.revenue_from_repeat_customers_pct:.1f}% of revenue. Most who return do so quickly (median "
                f"{rep.median_days_between_purchases:.0f} days between orders), so the first weeks after a first order matter most."),
              img("retention", 6.4 * cm),
              P(f"Repeat purchasing stepped up in March 2025, the month the loyalty programme launched, and stayed up. Comparing "
                "the same calendar months a year apart rules out seasonality. A faster courier for Greece arrived in May; "
                f"separating the two, the programme explains {dec.loyalty_effect_pp:.1f}pp of the {dec.total_change_pp:.1f}pp improvement and "
                f"faster delivery {dec.delivery_effect_pp:.1f}pp. Late deliveries matter: {late.result}."),
              img("rfm", 7.0 * cm),
              P(f"At Risk and Cannot Lose Them customers have bought repeatedly but have gone quiet. They are "
                f"{f['at_risk_cust']:.1f}% of customers but {f['at_risk_rev']:.1f}% of historical revenue, a better target than the "
                f"larger Lost group, most of whom bought once."),
              P("<b>Recommendation:</b> keep the loyalty programme, add a second-order offer within 30 days of the first, and run "
                "a win-back campaign for At Risk / Cannot Lose Them before spending on lapsed one-time buyers.", "rec"),
              PageBreak()]

    # ---- page 5: inventory & operations ----
    rows = [["SKU", "Product", "Class", "Stock", "30-day forecast", "Difference", "Action"]]
    for r in risky.sort_values("revenue_at_risk_30d", ascending=False).head(8).itertuples():
        rows.append([r.sku, r.product_name, r.abc_class, f"{r.stock:,}", f"{r.forecast_30d:,.0f}",
                     f"{r.difference:+,.0f}", "Expedite" if r.risk.startswith("STOCKOUT") else "Order today"])
    bt = f["backtest"]
    story += [P("4. Product and inventory findings", "h1"),
              img("stock", 6.9 * cm),
              table(rows, [2.0 * cm, 5.0 * cm, 1.2 * cm, 1.5 * cm, 2.6 * cm, 2.0 * cm, 3.1 * cm], right=(3, 4, 5)),
              Spacer(1, 4),
              P(f"Demand for the next 30 days was forecast for every product from its recent sales on in-stock days, adjusted "
                f"for the seasonal January drop. Tested on the previous four months, the forecast was more accurate than "
                f"'same as last month' every time (average error {bt['wape_method_pct'].mean():.0f}% vs "
                f"{bt['wape_naive_pct'].mean():.0f}%). {len(risky)} products will run out before or soon after a new delivery could arrive. "
                f"Separately, {int(over.products)} products hold {eur(over.stock_value_at_cost)} of stock "
                f"({over.pct_of_stock_value:.0f}% of stock value) with more than 120 days of cover."),
              KeepTogether([P("An alert, investigated", "h2"), img("anomaly", 5.5 * cm),
                            P(f"Automated monitoring flagged Wearables revenue on 6 January 2025 at 84% below expectation. "
                              f"The investigation traced {an.share_of_category_change_pct:.0f}% of the drop to one product, "
                              f"{an.product_name}, the category's best-seller ({eur(sku.revenue_2024)} in 2024). It sold out on "
                              f"{pd.Timestamp(sku.sold_out_on):%d %B %Y}, its last delivery had been on "
                              f"{pd.Timestamp(sku.last_delivery):%d %B}, and it received no stock at all in 2025. Demand did not "
                              "disappear; the product stopped being bought in.")]),
              P(f"<b>Recommendation:</b> place the reorders above today; raise safety stock on the A-class products that "
                f"repeatedly run out; pause purchasing for overstocked lines; and confirm with purchasing whether "
                f"{an.product_name} was discontinued on purpose. Add a daily alert when an A-class product's stock falls "
                f"below its lead-time demand.", "rec"),
              PageBreak()]

    # ---- page 6: recommendations + methodology ----
    recs = [["#", "Action", "Evidence", "Owner"],
            ["1", f"Reorder {len(risky)} at-risk products now; raise safety stock on {int(abc.with_3plus_stockout_episodes)} A-class SKUs",
             f"{eur(risky['revenue_at_risk_30d'].sum())} at risk in January; {eur(abc.their_est_lost_revenue)} lost in 2025", "Purchasing"],
            ["2", "Use gross profit, not revenue, to rank products; fix the volume traps",
             f"{int(vt.products)} products: {vt.revenue_share_pct:.0f}% of revenue, {vt.profit_share_pct:.0f}% of profit", "Category mgmt"],
            ["3", "Replace blanket discount codes with targeted, tested offers",
             f"Same basket size, ~{eur(gp_given)} profit given away", "Marketing"],
            ["4", "Keep the loyalty programme; add a 30-day second-order offer",
             f"{dec.loyalty_effect_pp:+.1f}pp 90-day repeat rate", "Marketing"],
            ["5", "Win back At Risk / Cannot Lose Them customers",
             f"{f['at_risk_cust']:.1f}% of customers, {f['at_risk_rev']:.1f}% of revenue", "CRM"],
            ["6", "Bring delivery abroad up to the Greek standard", "Late first delivery lowers repeat rate", "Operations"],
            ["7", f"Release stock from {int(over.products)} overstocked SKUs", f"{eur(over.stock_value_at_cost)} tied up", "Purchasing"]]
    wrap = lambda t: Paragraph(t, ParagraphStyle("c", fontName="Helvetica", fontSize=8.3, leading=10.5))
    recs = [recs[0]] + [[r[0], wrap(r[1]), wrap(r[2]), r[3]] for r in recs[1:]]
    dq = f["dq"]
    story += [P("5. Recommendations", "h1"), P("Ranked by expected impact and how quickly they can be acted on:"),
              table(recs, [0.6 * cm, 7.4 * cm, 6.3 * cm, 3.1 * cm]),
              Spacer(1, 10), P("6. Methodology and limitations", "h1"),
              P(f"<b>Data.</b> {f['defects'].raw_records:,.0f} transaction records exported from the order system, plus customers, "
                f"products and daily stock counts. {f['defects'].pct_with_a_defect:.0f}% of records needed a correction (duplicates, "
                "four date formats, inconsistent country names, missing values, impossible prices); each defect has a documented "
                f"decision, and only {f['defects'].records_removed:,.0f} records were removed. After cleaning, the warehouse passes "
                f"all {int(dq.loc['clean', 'rules_checked'])} automated quality rules (completeness "
                f"{dq.loc['clean', 'completeness_pct']:.1f}%, validity {dq.loc['clean', 'validity_pct']:.1f}%, duplicates "
                f"{dq.loc['clean', 'duplicates_pct']:.1f}%)."),
              P("<b>Definitions.</b> Net revenue = sales after discounts and refunds, excluding cancelled orders. Gross profit = "
                "net revenue minus cost of goods and outbound shipping (delivery is free for customers). Each KPI is "
                "defined once in the database and reused by every report."),
              P("<b>Methods.</b> SQL for all KPIs; significance tests for every claim that compares groups; same-weekday "
                "z-scores for anomaly detection; a seasonal, stockout-aware demand forecast tested against a naive baseline."),
              P("<b>Limitations.</b> The data is simulated, with realistic defects and business events built in: the methods "
                "carry over, the figures do not. Before/after comparisons (loyalty programme, courier) are observational; a hold-out "
                "group would measure them directly. Website sessions are not in the data, so the effect of discounts on "
                "conversion cannot be measured. Lost-sales estimates assume demand while out of stock equals demand when in "
                "stock, so they are an upper bound. Purchase orders in transit are not in the export.", "body"),
              Spacer(1, 6),
              P("Full analysis, SQL and code: github.com/kgiannopoulou/fullstack-ecommerce", "small")]

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(1.8 * cm, 0.9 * cm, "Executive Analysis Report · E-commerce performance 2024-2025")
        canvas.drawRightString(A4[0] - 1.8 * cm, 0.9 * cm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main():
    transform.write_alerts()
    f = collect()
    figs = {"monthly": chart_monthly(f), "bridge": chart_bridge(f), "scatter": chart_scatter(f),
            "discount": chart_discount(f), "retention": chart_retention(f), "rfm": chart_rfm(f),
            "stock": chart_stock(f), "anomaly": chart_anomaly(f)}
    chart_dashboard(f)
    build_pdf(f, figs)
    print(f"wrote {len(figs)} charts to reports/figures/ and reports/Executive_Analysis_Report.pdf")


if __name__ == "__main__":
    main()
