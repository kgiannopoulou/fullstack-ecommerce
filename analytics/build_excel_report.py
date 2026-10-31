"""Build reports/ecommerce_management_report.xlsx from the query results.

One sheet per brief question, native Excel charts (they stay editable) and
conditional formatting, so the workbook can be handed to a manager as is.
"""
from __future__ import annotations

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import config

HEADER = PatternFill("solid", fgColor="1F3864")
TITLE = Font(size=14, bold=True, color="1F3864")
NOTE = Font(italic=True, color="595959")
RED = PatternFill("solid", fgColor="F8CBAD")
AMBER = PatternFill("solid", fgColor="FFE699")
GREEN = PatternFill("solid", fgColor="C6E0B4")
BLUE = PatternFill("solid", fgColor="BDD7EE")


def load(qid: str) -> pd.DataFrame:
    return pd.read_csv(config.OUTPUT_DIR / f"{qid}.csv")


def put_table(ws, df: pd.DataFrame, row: int, col: int = 1, title: str | None = None, note: str | None = None) -> int:
    """Write df at (row, col) with a styled header; returns the next free row."""
    if title:
        ws.cell(row, col, title).font = Font(bold=True, size=12)
        row += 1
    if note:
        ws.cell(row, col, note).font = NOTE
        row += 1
    for j, name in enumerate(df.columns):
        c = ws.cell(row, col + j, name.replace("_", " "))
        c.fill, c.font = HEADER, Font(bold=True, color="FFFFFF")
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for i, rec in enumerate(df.itertuples(index=False), start=1):
        for j, v in enumerate(rec):
            ws.cell(row + i, col + j, None if pd.isna(v) else v)
    for j, name in enumerate(df.columns):
        width = max(len(str(name)) * 0.9, *(len(str(v)) for v in df.iloc[:, j].head(200))) + 2
        letter = get_column_letter(col + j)
        ws.column_dimensions[letter].width = max(ws.column_dimensions[letter].width or 0, min(width, 48))
        if pd.api.types.is_float_dtype(df.iloc[:, j]) or pd.api.types.is_integer_dtype(df.iloc[:, j]):
            fmt = "#,##0" if ("revenue" in name or "value" in name or "eur" in name or "profit" in name
                              or "cogs" in name or "orders" in name or "customers" in name or "units" in name) else "#,##0.0#"
            for i in range(1, len(df) + 1):
                ws.cell(row + i, col + j).number_format = fmt
    ws.row_dimensions[row].height = 32
    return row + len(df) + 2


def sheet(wb, name, title, subtitle):
    ws = wb.create_sheet(name)
    ws["A1"], ws["A2"] = title, subtitle
    ws["A1"].font, ws["A2"].font = TITLE, NOTE
    ws.sheet_view.showGridLines = False
    return ws


def main():
    wb = Workbook()
    wb.remove(wb.active)

    # 1. Summary ------------------------------------------------------------------
    ws = sheet(wb, "Summary", "E-Commerce Sales, Customer & Operations Analytics",
               "Jan 2024 - Dec 2025 | net revenue = completed order revenue - discounts - refunds (docs/kpi_dictionary.md)")
    r = put_table(ws, load("Q02.1"), 4, title="Headline KPIs")
    r = put_table(ws, load("Q02.2"), r, title="Are we growing? 2025 vs 2024")
    ws.cell(r, 1, "Findings and recommendations: reports/findings.md. Every number comes from a query in sql/.").font = NOTE

    # 2. Revenue trend ------------------------------------------------------------
    ws = sheet(wb, "Revenue Trend", "Brief Q1 - How is the business performing?", "Monthly net revenue with MoM and YoY growth")
    m = load("Q03.1")
    end = put_table(ws, m, 4)
    chart = LineChart()
    chart.title, chart.y_axis.title, chart.height, chart.width = "Monthly net revenue (EUR)", "EUR", 8, 22
    chart.add_data(Reference(ws, min_col=2, min_row=4, max_row=4 + len(m)), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=5, max_row=4 + len(m)))
    ws.add_chart(chart, "J4")
    put_table(ws, load("Q03.2"), end, title="Quarterly")
    put_table(ws, load("Q03.8"), end + 12, title="Why did AOV fall? (mix, not price)",
              note="Like-for-like prices rose ~2%, revenue per unit fell: customers shifted to cheaper categories.")

    # 3. Products -----------------------------------------------------------------
    ws = sheet(wb, "Products", "Brief Q2 - Which products drive or hurt revenue?", "Category performance, ABC classes, winners and losers")
    cat = load("Q04.1")
    end = put_table(ws, cat, 4, title="Category performance")
    bar = BarChart()
    bar.type, bar.title, bar.height, bar.width = "bar", "Net revenue by category", 9, 16
    bar.add_data(Reference(ws, min_col=2, min_row=5, max_row=5 + len(cat)), titles_from_data=True)
    bar.set_categories(Reference(ws, min_col=1, min_row=6, max_row=5 + len(cat)))
    ws.add_chart(bar, "K4")
    yoy_col = get_column_letter(list(cat.columns).index("yoy_growth_pct") + 1)
    ws.conditional_formatting.add(f"{yoy_col}6:{yoy_col}{5 + len(cat)}",
                                  ColorScaleRule(start_type="num", start_value=-50, start_color="F8696B",
                                                 mid_type="num", mid_value=0, mid_color="FFFFFF",
                                                 end_type="num", end_value=100, end_color="63BE7B"))
    end = put_table(ws, load("Q04.3"), end, title="ABC analysis")
    end = put_table(ws, load("Q04.5"), end, title="Biggest winners and losers (H2 2025 vs H2 2024)")
    put_table(ws, load("Q04.4"), end, title="Declining three months in a row (2025)")

    # 4. Customers ----------------------------------------------------------------
    ws = sheet(wb, "Customers", "Brief Q3 - Are customers returning?", "Repeat behaviour and RFM segments (registered customers)")
    end = put_table(ws, load("Q05.1"), 4, title="Customer base")
    rfm = load("Q06.1")
    start = end
    end = put_table(ws, rfm, end, title="RFM segments")
    bar = BarChart()
    bar.title, bar.height, bar.width = "Share of customers vs share of revenue by segment", 9, 20
    bar.add_data(Reference(ws, min_col=3, min_row=start + 1, max_row=start + 1 + len(rfm)), titles_from_data=True)
    bar.add_data(Reference(ws, min_col=5, min_row=start + 1, max_row=start + 1 + len(rfm)), titles_from_data=True)
    bar.set_categories(Reference(ws, min_col=1, min_row=start + 2, max_row=start + 1 + len(rfm)))
    ws.add_chart(bar, f"L{start}")
    end = put_table(ws, load("Q06.2"), end, title="What to do with each segment")
    end = put_table(ws, load("Q05.5"), end, title="Repeat rate by acquisition channel")
    put_table(ws, load("Q05.7"), end, title="Late first delivery vs coming back (180 days)")

    # 5. Cohorts ------------------------------------------------------------------
    ws = sheet(wb, "Cohorts", "Brief Q3 - Is retention improving for newer customers?",
               "Share of each first-purchase cohort ordering again N months later")
    co = load("Q07.1")
    end = put_table(ws, co, 4)
    ws.conditional_formatting.add(f"C5:J{4 + len(co)}",
                                  ColorScaleRule(start_type="num", start_value=0, start_color="FFFFFF",
                                                 end_type="num", end_value=22, end_color="2E75B6"))
    end = put_table(ws, load("Q07.2"), end, title="90-day repeat rate, same months a year apart")
    end = put_table(ws, load("Q07.3"), end, title="Investigation: loyalty programme or delivery speed?")
    put_table(ws, load("Q07.5"), end, title="Decomposition of the improvement (percentage points)")

    # 6. Inventory ----------------------------------------------------------------
    ws = sheet(wb, "Inventory", "Brief Q4 - Which products are at risk of stockout or overstock?",
               "Position at 31 Dec 2025. Check CRITICAL / HIGH RISK actions against open purchase orders.")
    end = put_table(ws, load("Q08.2"), 4, title="Risk classes")
    end = put_table(ws, load("Q08.4"), end, title="Repeated stockouts by ABC class (2025)")
    inv = load("Q08.1")
    start = end
    end = put_table(ws, inv, end, title="Product action list")
    status_col = get_column_letter(list(inv.columns).index("stock_status") + 1)
    rng = f"A{start + 2}:{get_column_letter(len(inv.columns))}{start + 1 + len(inv)}"
    for word, fill in (("CRITICAL", RED), ("HIGH RISK", AMBER), ("OVERSTOCK", BLUE), ("DEAD STOCK", BLUE), ("HEALTHY", GREEN)):
        ws.conditional_formatting.add(rng, FormulaRule(formula=[f'${status_col}{start + 2}="{word}"'], fill=fill))
    ws.freeze_panes = f"A{start + 2}"
    put_table(ws, load("Q08.3"), end, title="Estimated sales lost to stockouts (2025)")

    # 7. Operations ---------------------------------------------------------------
    ws = sheet(wb, "Operations", "Fulfilment, delivery and cancellations", "Delivery promise: 4 days Greece, 7 days abroad")
    end = put_table(ws, load("Q09.2"), 4, title="On-time delivery by courier")
    end = put_table(ws, load("Q09.3"), end, title="Late deliveries and refunds")
    end = put_table(ws, load("Q09.4"), end, title="Weekend orders wait longer to ship")
    put_table(ws, load("Q02.4"), end, title="Cancellations by payment method")

    # 8. Data quality and statistics ----------------------------------------------
    ws = sheet(wb, "Data Quality", "Data quality decisions", "Counts reproduced in SQL (Q01.10) and Python (clean.py)")
    put_table(ws, load("Q01.10"), 4)
    tests = config.OUTPUT_DIR / "statistical_tests.csv"
    if tests.exists():
        ws = sheet(wb, "Statistical Tests", "Are the findings real?", "Generated by analytics/stats_analysis.py")
        put_table(ws, pd.read_csv(tests), 4)

    out = config.REPORTS_DIR / "ecommerce_management_report.xlsx"
    wb.save(out)
    print(f"wrote {out.relative_to(config.ROOT)} ({out.stat().st_size // 1024} KB, {len(wb.sheetnames)} sheets)")


if __name__ == "__main__":
    main()
