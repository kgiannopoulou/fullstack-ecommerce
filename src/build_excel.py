"""Build excel/Monthly_Business_Performance.xlsx by driving Excel itself.

Generating the workbook through Excel (COM automation) rather than writing the
file directly means it contains the real thing, the way an analyst would build
it by hand, so it can be refreshed and extended in Excel:

  * Power Query   one query per CSV in data/cleaned/, typed and renamed; the
                  folder is a single parameter (pDataFolder)
  * Power Pivot   a data model (sales fact + Calendar + Geography), two
                  relationships and DAX measures (Net Revenue, Gross Profit,
                  Gross Margin %, ...)
  * PivotTables   on the data model, driven by five shared slicers
                  (Year, Month, Country, Category, Customer Type)
  * Formulas      XLOOKUP, SUMIFS, COUNTIFS, IF, IFERROR, INDEX/MATCH on the
                  Executive Summary, Product, Inventory and Customer sheets

Requires Windows, Microsoft Excel (365/2021+) and pywin32. Run after the
pipeline has written data/cleaned/:

    python src/build_excel.py
"""
from __future__ import annotations

import time

import pandas as pd
import pythoncom
import win32com.client as win32

import config

OUT = config.EXCEL_DIR / "Monthly_Business_Performance.xlsx"
NAVY, LIGHT, GREY = 0x64381F, 0xFBF4EE, 0xF3F5F5      # Excel colours are BGR
WHITE = 0xFFFFFF
RED_FILL, AMBER_FILL, GREEN_FILL = 0xADCBF8, 0x99E6FF, 0xB4E0C6

SHEETS = ["Executive Summary", "Sales Analysis", "Product Performance", "Inventory",
          "Customer Analysis", "Raw Data", "Data Dictionary"]

# Power Query: query name -> (csv file, column types, renames shown to the user)
QUERIES = {
    "SalesSummary": ("SalesSummary.csv",
                     {"month": "date", "year": "Int64.Type", "month_name": "text", "country": "text", "category": "text",
                      "customer_type": "text", "channel": "text", "orders": "Int64.Type", "units": "Int64.Type",
                      "gross_sales": "number", "discounts": "number", "refunds": "number", "net_revenue": "number",
                      "cogs": "number", "shipping_cost": "number", "gross_profit": "number"}),
    "MonthlyKPIs": ("MonthlyKPIs.csv",
                    {"month": "date", "net_revenue": "number", "gross_revenue": "number", "gross_profit": "number",
                     "cogs": "number", "shipping_cost": "number", "orders_placed": "Int64.Type",
                     "fulfilled_orders": "Int64.Type", "units_sold": "Int64.Type", "active_customers": "Int64.Type",
                     "avg_order_value": "number", "refund_rate_pct": "number", "cancellation_rate_pct": "number",
                     "on_time_delivery_pct": "number", "gross_margin_pct": "number", "mom_growth_pct": "number",
                     "yoy_growth_pct": "number"}),
    "Products": ("ProductPerformance.csv",
                 {"product_id": "Int64.Type", "sku": "text", "product_name": "text", "category": "text",
                  "abc_class": "text", "units_2025": "Int64.Type", "net_revenue_2025": "number",
                  "net_revenue_2024": "number", "gross_profit_2025": "number", "discounts_2025": "number",
                  "shipping_cost_2025": "number"}),
    "Inventory": ("InventoryForecast.csv",
                  {"product_id": "Int64.Type", "sku": "text", "product_name": "text", "category": "text",
                   "abc_class": "text", "stock": "Int64.Type", "forecast_30d": "number", "difference": "number",
                   "days_cover": "number", "lead_time_days": "Int64.Type", "risk": "text", "reorder_qty": "number",
                   "expected_lost_units": "number", "avg_net_price": "number", "revenue_at_risk_30d": "number",
                   "recommended_action": "text"}),
    "Segments": ("CustomerSegments.csv",
                 {"segment": "text", "customers": "Int64.Type", "pct_customers": "number", "revenue": "number",
                  "pct_revenue": "number", "avg_orders": "number", "avg_recency_days": "number"}),
    "Cohorts": ("CohortRetention.csv",
                {"cohort": "date", "month_n": "Int64.Type", "customers": "Int64.Type", "cohort_size": "Int64.Type",
                 "retention_pct": "number"}),
    "Alerts": ("ManagementAlerts.csv",
               {"alert_id": "Int64.Type", "severity": "text", "icon": "text", "area": "text", "alert": "text",
                "value": "number", "as_of": "date"}),
    "DataQuality": ("DataQualityScorecard.csv",
                    {"stage": "text", "records": "Int64.Type", "completeness_pct": "number", "validity_pct": "number",
                     "duplicates_pct": "number", "missing_values_pct": "number", "rules_checked": "Int64.Type",
                     "failed_checks": "Int64.Type", "critical_failures": "Int64.Type"}),
    "Geography": ("DimGeography.csv", {"country": "text", "market": "text", "delivery_promise_days": "Int64.Type"}),
}
# Readable names for the columns slicers and pivots show.
FRIENDLY = {"customer_type": "Customer Type", "category": "Category", "country": "Country", "channel": "Channel"}

CALENDAR_M = """let
    Source = SalesSummary,
    Months = Table.Distinct(Table.SelectColumns(Source, {"month"})),
    AddYear = Table.AddColumn(Months, "Year", each Date.Year([month]), Int64.Type),
    AddQuarter = Table.AddColumn(AddYear, "Quarter", each "Q" & Text.From(Date.QuarterOfYear([month])), type text),
    AddMonthNo = Table.AddColumn(AddQuarter, "Month No", each Date.Month([month]), Int64.Type),
    AddMonth = Table.AddColumn(AddMonthNo, "Month Name", each Text.PadStart(Text.From(Date.Month([month])), 2, "0") & " " & Date.ToText([month], "MMM", "en-US"), type text),
    Sorted = Table.Sort(AddMonth, {{"month", Order.Ascending}})
in
    Sorted"""

# DAX measures in the Power Pivot model: (name, formula, format)
MEASURES = [
    ("Net Revenue", "SUM(SalesSummary[net_revenue])", "eur"),
    ("Gross Profit", "SUM(SalesSummary[gross_profit])", "eur"),
    ("Gross Margin %", "DIVIDE([Gross Profit], [Net Revenue])", "pct"),
    ("Units Sold", "SUM(SalesSummary[units])", "int"),
    ("Discount Amount", "SUM(SalesSummary[discounts])", "eur"),
    ("Refund Amount", "SUM(SalesSummary[refunds])", "eur"),
    ("Shipping Costs", "SUM(SalesSummary[shipping_cost])", "eur"),
    ("Discount Rate %", "DIVIDE([Discount Amount], SUM(SalesSummary[gross_sales]))", "pct"),
    ("Net Revenue PY", "CALCULATE([Net Revenue], FILTER(ALL('Calendar'), 'Calendar'[Year] = MAX('Calendar'[Year]) - 1 "
                       "&& 'Calendar'[Month No] IN VALUES('Calendar'[Month No])))", "eur"),
    ("YoY Growth %", "IF(NOT ISBLANK([Net Revenue PY]), DIVIDE([Net Revenue] - [Net Revenue PY], [Net Revenue PY]))", "pct"),
]


def m_query(csv: str, types: dict[str, str]) -> str:
    typed = ", ".join(f'{{"{c}", {t if "." in t else "type " + t}}}' for c, t in types.items())
    renames = ", ".join(f'{{"{c}", "{FRIENDLY[c]}"}}' for c in types if c in FRIENDLY)
    rename_step = f',\n    Renamed = Table.RenameColumns(Typed, {{{renames}}})' if renames else ""
    last = "Renamed" if renames else "Typed"
    return (f'let\n    Source = Csv.Document(File.Contents(pDataFolder & "{csv}"), '
            f'[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n'
            f'    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),\n'
            f'    Typed = Table.TransformColumnTypes(Promoted, {{{typed}}}, "en-US"){rename_step}\nin\n    {last}')


def formula2(rng, formula: str):
    """Write a formula so that it works in every Excel that has the function.

    XLOOKUP is written in its file form, _xlfn.XLOOKUP: that is exactly how Excel 365 stores it,
    so the workbook can be generated by an Excel build without XLOOKUP and still compute in any
    Excel 365 / 2021+ (the file is marked to fully recalculate on open, see mark_full_recalc).
    Dynamic-array functions are avoided on purpose so nothing spills into older versions."""
    import re
    # [@units_2025] is ambiguous to Excel's parser (digits in the name); [@[units_2025]] is not.
    formula = re.sub(r"\[@([^\[\]]+)\]", r"[@[\1]]", formula)
    rng.Formula = formula.replace("XLOOKUP(", "_xlfn.XLOOKUP(")


def mark_full_recalc(path):
    """Set <calcPr fullCalcOnLoad="1"/> so Excel recalculates every formula when the file opens."""
    import re
    import shutil
    import zipfile
    tmp = path.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/workbook.xml":
                text = data.decode("utf-8")
                text = re.sub(r"<calcPr([^>]*?)/>", lambda m: "<calcPr" + m.group(1).replace(' fullCalcOnLoad="1"', "")
                              + ' fullCalcOnLoad="1"/>', text, count=1)
                data = text.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)


def col(name: str) -> str:
    return FRIENDLY.get(name, name)


class Builder:
    def __init__(self):
        pythoncom.CoInitialize()
        self.xl = win32.gencache.EnsureDispatch(win32.DispatchEx("Excel.Application"))
        self.xl.Visible = False
        self.xl.DisplayAlerts = False
        self.c = win32.constants
        self.wb = self.xl.Workbooks.Add()
        while self.wb.Worksheets.Count < len(SHEETS):
            self.wb.Worksheets.Add(After=self.wb.Worksheets(self.wb.Worksheets.Count))
        for i, name in enumerate(SHEETS, start=1):
            ws = self.wb.Worksheets(i)
            ws.Name = name
            self.xl.ActiveWindow.DisplayGridlines = True
        self.ws = {n: self.wb.Worksheets(n) for n in SHEETS}

    # ---------------------------------------------------------- Power Query --
    def add_queries(self):
        folder = str(config.CLEAN_DIR) + "\\"
        self.wb.Queries.Add("pDataFolder", f'"{folder}" meta [IsParameterQuery=true, Type="Text", '
                                           f'IsParameterQueryRequired=true]',
                            "Folder holding the CSVs written by the pipeline (data/cleaned). Change it here after moving the repo.")
        for name, (csv, types) in QUERIES.items():
            self.wb.Queries.Add(name, m_query(csv, types), f"data/cleaned/{csv}")
        self.wb.Queries.Add("Calendar", CALENDAR_M, "One row per month, built from the sales query")

    def to_sheet(self, query: str, ws, cell: str, table: str, style: str = "TableStyleLight9"):
        conn = (f"OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=$Workbook$;Location={query};"
                "Extended Properties=\"\"")
        lo = ws.ListObjects.Add(SourceType=0, Source=conn, Destination=ws.Range(cell))
        qt = lo.QueryTable
        qt.CommandType = self.c.xlCmdSql
        qt.CommandText = [f"SELECT * FROM [{query}]"]
        qt.PreserveFormatting = True
        qt.RefreshOnFileOpen = False
        qt.BackgroundQuery = False
        qt.AdjustColumnWidth = True
        qt.ListObject.DisplayName = table
        qt.Refresh(False)
        lo.TableStyle = style
        return lo

    def to_model(self, query: str):
        conn = (f"OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=$Workbook$;Location={query};"
                "Extended Properties=\"\"")
        self.wb.Connections.Add2(f"Query - {query}", f"Connection to the '{query}' query in the workbook.", conn,
                                 f'"{query}"', 6, True, False)

    # ---------------------------------------------------------- Power Pivot --
    def build_model(self):
        for q in ("SalesSummary", "Calendar", "Geography"):
            self.to_model(q)
        model = self.wb.Model
        t = model.ModelTables
        model.ModelRelationships.Add(t("SalesSummary").ModelTableColumns("month"), t("Calendar").ModelTableColumns("month"))
        model.ModelRelationships.Add(t("SalesSummary").ModelTableColumns("Country"), t("Geography").ModelTableColumns("country"))
        def fmt(kind):
            if kind == "eur":
                f = model.ModelFormatCurrency
                f.Symbol, f.DecimalPlaces = "€", 0
            elif kind == "pct":
                f = model.ModelFormatPercentageNumber
                f.UseThousandSeparator, f.DecimalPlaces = False, 1
            else:
                f = model.ModelFormatWholeNumber
                f.UseThousandSeparator = True
            return f
        for name, dax, kind in MEASURES:
            model.ModelMeasures.Add(name, t("SalesSummary"), dax, fmt(kind))

    def pivot(self, ws, cell: str, name: str, rows: list[str], measures: list[str], cols: list[str] = ()):
        pc = self.wb.PivotCaches().Create(SourceType=self.c.xlExternal,
                                          SourceData=self.wb.Connections("ThisWorkbookDataModel"), Version=6)
        pt = pc.CreatePivotTable(TableDestination=ws.Range(cell), TableName=name)
        for r in rows:
            pt.CubeFields(r).Orientation = self.c.xlRowField
        for cf in cols:
            pt.CubeFields(cf).Orientation = self.c.xlColumnField
        for m in measures:
            pt.AddDataField(pt.CubeFields(f"[Measures].[{m}]"))
        pt.RowAxisLayout(self.c.xlTabularRow)
        pt.TableStyle2 = "PivotStyleLight16"
        return pt

    # ------------------------------------------------------------- helpers --
    def title(self, ws, text: str, sub: str):
        ws.Range("A1").Value = text
        ws.Range("A1").Font.Size = 16
        ws.Range("A1").Font.Bold = True
        ws.Range("A1").Font.Color = NAVY
        ws.Range("A2").Value = sub
        ws.Range("A2").Font.Italic = True
        ws.Range("A2").Font.Color = 0x595959

    def header(self, rng):
        rng.Interior.Color = NAVY
        rng.Font.Color = WHITE
        rng.Font.Bold = True

    def color_rule(self, rng, formula: str, fill: int):
        fc = rng.FormatConditions.Add(Type=self.c.xlExpression, Formula1=formula)
        fc.Interior.Color = fill

    # -------------------------------------------------------------- sheets --
    def raw_data(self):
        ws = self.ws["Raw Data"]
        self.title(ws, "Raw Data: monthly sales by country, category, customer type and channel",
                   "Power Query: data/cleaned/SalesSummary.csv (aggregated from reporting.fact_sales). Refresh: Data > Refresh All.")
        self.to_sheet("SalesSummary", ws, "A4", "tblSales")
        ws.Range("A:A").NumberFormat = "yyyy-mm"
        ws.Range("H:I").NumberFormat = "#,##0"
        ws.Range("J:P").NumberFormat = "€#,##0"

    def sales_analysis(self):
        ws = self.ws["Sales Analysis"]
        self.title(ws, "Sales Analysis", "PivotTables on the Power Pivot data model. Use the slicers to filter every pivot in the workbook.")
        self.pt_month = self.pivot(ws, "A12", "ptMonthly", ["[Calendar].[Year]", "[Calendar].[Month Name]"],
                                   ["Net Revenue", "Gross Profit", "Gross Margin %", "Net Revenue PY", "YoY Growth %"])
        self.pt_cat = self.pivot(ws, "I12", "ptCategory", ["[SalesSummary].[Category]"],
                                 ["Net Revenue", "Gross Profit", "Gross Margin %", "Units Sold", "Discount Rate %"])
        self.pt_country = self.pivot(ws, "I30", "ptCountry", ["[SalesSummary].[Country]"],
                                     ["Net Revenue", "Gross Profit", "Gross Margin %", "Shipping Costs"])
        # Month sort: by Month No (a calendar month is not alphabetical).
        try:
            self.pt_month.PivotFields("[Calendar].[Month Name].[Month Name]").AutoSort(self.c.xlManual, "Month Name")
        except Exception:
            pass
        ch = ws.Shapes.AddChart2(-1, self.c.xlColumnClustered, ws.Range("P4").Left, ws.Range("P12").Top, 520, 260).Chart
        ch.SetSourceData(self.pt_cat.TableRange1)
        ch.HasTitle = True
        ch.ChartTitle.Text = "Net revenue and gross profit by category"
        try:
            for s in range(ch.SeriesCollection().Count, 2, -1):   # keep the two euro measures
                ch.SeriesCollection(s).Delete()
        except Exception:
            pass

    def slicers(self):
        ws = self.ws["Sales Analysis"]
        pivots = [self.pt_month, self.pt_cat, self.pt_country, self.pt_ctype, self.pt_prod]
        spec = [("[Calendar].[Year]", "Year"), ("[Calendar].[Month Name]", "Month"), ("[SalesSummary].[Country]", "Country"),
                ("[SalesSummary].[Category]", "Category"), ("[SalesSummary].[Customer Type]", "Customer Type")]
        left = ws.Range("A4").Left
        for i, (field, caption) in enumerate(spec):
            sc = self.wb.SlicerCaches.Add2(self.pt_month, field)
            sc.Slicers.Add(ws, pythoncom.Missing, f"sl{caption.replace(' ', '')}", caption,
                           ws.Range("A4").Top, left + i * 150, 145, 115)
            for pt in pivots[1:]:
                try:
                    sc.PivotTables.AddPivotTable(pt)
                except Exception as e:
                    print(f"  slicer {caption} -> {pt.Name}: {e}")

    def product_performance(self):
        ws = self.ws["Product Performance"]
        self.title(ws, "Product Performance (2025)",
                   "Ranked by gross profit, not revenue: unit cost, discounts and shipping change the order.")
        lo = self.to_sheet("Products", ws, "A26", "tblProducts")
        n = lo.ListColumns.Count
        add = [("Gross Margin %", "=IFERROR([@gross_profit_2025]/[@net_revenue_2025],0)", "0.0%"),
               ("YoY Growth %", '=IFERROR([@net_revenue_2025]/[@net_revenue_2024]-1,"n/a")', "0.0%"),
               ("Revenue Rank", '=IFERROR(RANK.EQ([@net_revenue_2025],[net_revenue_2025],0),"")', "0"),
               ("Profit Rank", '=IFERROR(RANK.EQ([@gross_profit_2025],[gross_profit_2025],0),"")', "0"),
               ("Rank Change", '=IFERROR([@[Revenue Rank]]-[@[Profit Rank]],"")', "+0;-0;0"),
               ("Flag", '=IF([@[Revenue Rank]]="","No 2025 sales",IF(AND([@[Revenue Rank]]<=50,[@[Profit Rank]]-[@[Revenue Rank]]>=10),"Revenue overstates value",'
                        'IF([@gross_profit_2025]<0,"Loss-making","")))', "0")]
        for i, (name, formula, fmt) in enumerate(add, start=1):
            c = lo.ListColumns.Add()
            c.Name = name
            c.DataBodyRange.NumberFormat = "0.00"   # not text: a new column inherits its neighbour's format
            formula2(c.DataBodyRange, formula)
            c.DataBodyRange.NumberFormat = fmt
        ws.Range(lo.ListColumns("net_revenue_2025").DataBodyRange.Address).NumberFormat = "€#,##0"
        for cname in ("net_revenue_2024", "gross_profit_2025", "discounts_2025", "shipping_cost_2025"):
            lo.ListColumns(cname).DataBodyRange.NumberFormat = "€#,##0"
        flag = lo.ListColumns("Flag").DataBodyRange
        letter = ws.Cells(1, flag.Column).Address.split("$")[1]
        self.color_rule(flag, f'=${letter}{flag.Row}<>""', AMBER_FILL)

        # Top 10 by gross profit with INDEX/MATCH + LARGE, next to the same rank by revenue.
        ws.Range("A4").Value = "Top 10 by gross profit (INDEX/MATCH)"
        ws.Range("A4").Font.Bold = True
        hdr = ws.Range("A5:E5")
        hdr.Value = ("#", "Product", "Gross profit", "Margin", "Revenue rank")
        self.header(hdr)
        for i in range(1, 11):
            r = 5 + i
            ws.Range(f"A{r}").Value = i
            formula2(ws.Range(f"C{r}"), f"=LARGE(tblProducts[gross_profit_2025],A{r})")
            formula2(ws.Range(f"B{r}"), f"=INDEX(tblProducts[product_name],MATCH(C{r},tblProducts[gross_profit_2025],0))")
            formula2(ws.Range(f"D{r}"), f"=XLOOKUP(B{r},tblProducts[product_name],tblProducts[Gross Margin %])")
            formula2(ws.Range(f"E{r}"), f"=XLOOKUP(B{r},tblProducts[product_name],tblProducts[Revenue Rank])")
        ws.Range("C6:C15").NumberFormat = "€#,##0"
        ws.Range("D6:D15").NumberFormat = "0.0%"
        ws.Range("G4").Value = "Category x customer type (data model)"
        ws.Range("G4").Font.Bold = True
        self.pt_prod = self.pivot(ws, "G5", "ptCategoryType", ["[SalesSummary].[Category]"], ["Gross Profit"],
                                  cols=["[SalesSummary].[Customer Type]"])
        lo.Range.Columns.AutoFit()

    def inventory(self):
        ws = self.ws["Inventory"]
        self.title(ws, "Inventory: 30-day stockout forecast",
                   "Stock on 31 Dec 2025 vs forecast demand for the next 30 days (src/forecast.py).")
        lo = self.to_sheet("Inventory", ws, "A14", "tblInventory")
        for name, formula, fmt in [
            ("Class Check", '=XLOOKUP([@product_id],tblProducts[product_id],tblProducts[abc_class],"?")', "0"),
            ("Status", '=IF([@days_cover]<[@lead_time_days],"Stockout before restock",'
                       'IF([@days_cover]<[@lead_time_days]+7,"Reorder now",IF([@days_cover]>120,"Overstock","OK")))', "0"),
            ("Short 30d", "=IF([@difference]<0,-[@difference],0)", "#,##0"),
        ]:
            c = lo.ListColumns.Add()
            c.Name = name
            c.DataBodyRange.NumberFormat = "0.00"   # not text: a new column inherits its neighbour's format
            formula2(c.DataBodyRange, formula)
            c.DataBodyRange.NumberFormat = fmt
        lo.ListColumns("revenue_at_risk_30d").DataBodyRange.NumberFormat = "€#,##0"
        lo.ListColumns("avg_net_price").DataBodyRange.NumberFormat = "€#,##0.00"
        lo.ListColumns("forecast_30d").DataBodyRange.NumberFormat = "#,##0"
        lo.ListColumns("difference").DataBodyRange.NumberFormat = "+#,##0;-#,##0;0"
        status = lo.ListColumns("Status").DataBodyRange
        first = status.Row
        col = status.Column
        letter = ws.Cells(1, col).Address.split("$")[1]
        self.color_rule(status, f'=${letter}{first}="Stockout before restock"', RED_FILL)
        self.color_rule(status, f'=${letter}{first}="Reorder now"', AMBER_FILL)
        self.color_rule(status, f'=${letter}{first}="Overstock"', 0xE0E0E0)

        ws.Range("A4").Value = "Summary (COUNTIFS / SUMIFS)"
        ws.Range("A4").Font.Bold = True
        hdr = ws.Range("A5:D5")
        hdr.Value = ("Status", "Products", "A-class", "Revenue at risk (30d)")
        self.header(hdr)
        for i, st in enumerate(["Stockout before restock", "Reorder now", "Overstock", "OK"], start=6):
            ws.Range(f"A{i}").Value = st
            formula2(ws.Range(f"B{i}"), f'=COUNTIFS(tblInventory[Status],A{i})')
            formula2(ws.Range(f"C{i}"), f'=COUNTIFS(tblInventory[Status],A{i},tblInventory[abc_class],"A")')
            formula2(ws.Range(f"D{i}"), f'=SUMIFS(tblInventory[revenue_at_risk_30d],tblInventory[Status],A{i})')
        ws.Range("A10").Value = "Total"
        ws.Range("A10").Font.Bold = True
        for c_ in "BCD":
            formula2(ws.Range(f"{c_}10"), f"=SUM({c_}6:{c_}9)")
        ws.Range("D6:D10").NumberFormat = "€#,##0"
        lo.Range.Columns.AutoFit()
        ws.Columns("P").ColumnWidth = 60

    def customer_analysis(self):
        ws = self.ws["Customer Analysis"]
        self.title(ws, "Customer Analysis", "New vs returning revenue, RFM segments and monthly cohort retention.")
        ws.Range("A4").Value = "Revenue by customer type (data model; slicers apply)"
        ws.Range("A4").Font.Bold = True
        self.pt_ctype = self.pivot(ws, "A5", "ptCustomerType", ["[Calendar].[Year]"], ["Net Revenue", "Gross Profit"],
                                   cols=["[SalesSummary].[Customer Type]"])
        ws.Range("A14").Value = "RFM segments"
        ws.Range("A14").Font.Bold = True
        lo = self.to_sheet("Segments", ws, "A15", "tblSegments")
        c = lo.ListColumns.Add()
        c.Name = "Value Index"
        formula2(c.DataBodyRange, "=IFERROR([@pct_revenue]/[@pct_customers],0)")
        c.DataBodyRange.NumberFormat = "0.00"
        c = lo.ListColumns.Add()
        c.Name = "Action"
        formula2(c.DataBodyRange, ('=IF(OR([@segment]="At Risk",[@segment]="Cannot Lose Them"),"Win back now",'
                                    'IF([@[Value Index]]>=2,"Protect","Nurture / low priority"))'))
        lo.ListColumns("revenue").DataBodyRange.NumberFormat = "€#,##0"

        # Cohort matrix built with formulas from the long-format cohort table.
        start = 29
        ws.Range(f"A{start}").Value = "Cohort retention: % of each first-order month still buying N months later (SUMIFS / COUNTIFS)"
        ws.Range(f"A{start}").Font.Bold = True
        self.to_sheet("Cohorts", ws, "AA4", "tblCohorts")
        hdr_row = start + 1
        ws.Range(f"A{hdr_row}").Value = "Cohort"
        ws.Range(f"B{hdr_row}").Value = "Customers"
        for n in range(0, 13):
            ws.Cells(hdr_row, 3 + n).Value = n
        self.header(ws.Range(ws.Cells(hdr_row, 1), ws.Cells(hdr_row, 15)))
        cohorts = sorted(pd.read_csv(config.CLEAN_DIR / "CohortRetention.csv")["cohort"].unique())
        for i, c_ in enumerate(cohorts[:24]):
            ws.Range(f"A{hdr_row + 1 + i}").Formula = f'=DATEVALUE("{c_}")'

        rows = 24
        for i in range(rows):
            r = hdr_row + 1 + i
            formula2(ws.Range(f"B{r}"), f'=SUMIFS(tblCohorts[customers],tblCohorts[cohort],A{r},tblCohorts[month_n],0)')
            for n in range(0, 13):
                cell = ws.Cells(r, 3 + n)
                h = ws.Cells(hdr_row, 3 + n).Address
                formula2(cell, (f'=IF(COUNTIFS(tblCohorts[cohort],$A{r},tblCohorts[month_n],{h})=0,"",'
                                 f'SUMIFS(tblCohorts[retention_pct],tblCohorts[cohort],$A{r},tblCohorts[month_n],{h})/100)'))
        body = ws.Range(ws.Cells(hdr_row + 1, 4), ws.Cells(hdr_row + rows, 15))
        body.NumberFormat = "0.0%"
        cs = body.FormatConditions.AddColorScale(2)
        cs.ColorScaleCriteria(1).FormatColor.Color = WHITE
        cs.ColorScaleCriteria(2).FormatColor.Color = 0xD67828
        ws.Range(f"A{hdr_row + 1}:A{hdr_row + rows}").NumberFormat = "yyyy-mm"
        ws.Range(f"C{hdr_row + 1}:C{hdr_row + rows}").NumberFormat = "0%"
        ws.Columns("AA:AE").Hidden = True

    def executive_summary(self):
        ws = self.ws["Executive Summary"]
        self.title(ws, "Monthly Business Performance", "E-commerce sales, profit, customers and stock. Pick a month in C4; every figure updates.")
        # KPI table on a helper area of this sheet (loaded by Power Query)
        self.to_sheet("MonthlyKPIs", ws, "AA4", "tblKPI")
        self.to_sheet("Alerts", ws, "AA40", "tblAlerts")
        self.to_sheet("DataQuality", ws, "AA60", "tblDQ")
        ws.Range("B4").Value = "Report month"
        ws.Range("B4").Font.Bold = True
        last = pd.read_csv(config.CLEAN_DIR / "MonthlyKPIs.csv")["month"].iloc[-1]
        formula2(ws.Range("C4"), f'=DATEVALUE("{last}")')
        ws.Range("C4").Value = ws.Range("C4").Value
        ws.Range("C4").NumberFormat = "mmm yyyy"
        ws.Range("C4").Interior.Color = 0xCCF2FF
        dv = ws.Range("C4").Validation
        dv.Delete()
        dv.Add(Type=self.c.xlValidateList, AlertStyle=1, Operator=1, Formula1='=INDIRECT("tblKPI[month]")')

        hdr = ws.Range("B6:H6")
        hdr.Value = ("KPI", "This month", "Same month last year", "YoY change", "Trend", "Year to date", "YTD last year")
        self.header(hdr)
        kpis = [("Net revenue", "net_revenue", "€#,##0", True), ("Gross profit", "gross_profit", "€#,##0", True),
                ("Gross margin %", "gross_margin_pct", '0.0"%"', False), ("Orders", "fulfilled_orders", "#,##0", True),
                ("Average order value", "avg_order_value", "€#,##0.00", False),
                ("Active customers", "active_customers", "#,##0", False),
                ("Refund rate %", "refund_rate_pct", '0.00"%"', False),
                ("On-time delivery %", "on_time_delivery_pct", '0.0"%"', False)]
        for i, (label, field, fmt, additive) in enumerate(kpis, start=7):
            ws.Range(f"B{i}").Value = label
            formula2(ws.Range(f"C{i}"), f"=INDEX(tblKPI[{field}],MATCH($C$4,tblKPI[month],0))")
            formula2(ws.Range(f"D{i}"), f'=IFERROR(XLOOKUP(EDATE($C$4,-12),tblKPI[month],tblKPI[{field}]),"–")')
            if fmt.endswith('"%"'):
                formula2(ws.Range(f"E{i}"), f'=IFERROR(C{i}-D{i},"–")')
                ws.Range(f"E{i}").NumberFormat = '+0.0"pp";-0.0"pp"'
            else:
                formula2(ws.Range(f"E{i}"), f'=IFERROR(C{i}/D{i}-1,"–")')
                ws.Range(f"E{i}").NumberFormat = "+0.0%;-0.0%"
            better_low = field == "refund_rate_pct"
            formula2(ws.Range(f"F{i}"), (f'=IF(ISNUMBER(E{i}),IF(E{i}{"<" if better_low else ">"}0,"▲ better","▼ worse"),"")'))
            if additive:
                formula2(ws.Range(f"G{i}"), (f"=SUMIFS(tblKPI[{field}],tblKPI[month],\"<=\"&$C$4,"
                                               f"tblKPI[month],\">=\"&DATE(YEAR($C$4),1,1))"))
                formula2(ws.Range(f"H{i}"), (f"=SUMIFS(tblKPI[{field}],tblKPI[month],\"<=\"&EDATE($C$4,-12),"
                                               f"tblKPI[month],\">=\"&DATE(YEAR($C$4)-1,1,1))"))
            for c_ in "CDGH":
                ws.Range(f"{c_}{i}").NumberFormat = fmt
        self.color_rule(ws.Range("F7:F14"), '=$F7="▲ better"', GREEN_FILL)   # no commas: CF formulas use the local list separator
        self.color_rule(ws.Range("F7:F14"), '=$F7="▼ worse"', RED_FILL)

        # Category leader for the month: SUMIFS over the raw data + INDEX/MATCH.
        ws.Range("J6").Value = "Category"
        ws.Range("K6").Value = "Revenue this month"
        ws.Range("L6").Value = "Gross profit"
        ws.Range("M6").Value = "Margin"
        self.header(ws.Range("J6:M6"))
        cats = sorted(pd.read_csv(config.CLEAN_DIR / "SalesSummary.csv")["category"].unique())
        for i, c_ in enumerate(cats):
            ws.Range(f"J{7 + i}").Value = c_
        for r in range(7, 19):
            formula2(ws.Range(f"K{r}"), f"=SUMIFS(tblSales[net_revenue],tblSales[Category],J{r},tblSales[month],$C$4)")
            formula2(ws.Range(f"L{r}"), f"=SUMIFS(tblSales[gross_profit],tblSales[Category],J{r},tblSales[month],$C$4)")
            formula2(ws.Range(f"M{r}"), f"=IFERROR(L{r}/K{r},0)")
        ws.Range("K7:L18").NumberFormat = "€#,##0"
        ws.Range("M7:M18").NumberFormat = "0.0%"
        db = ws.Range("K7:K18").FormatConditions.AddDatabar()
        db.BarColor.Color = 0xD67828

        ws.Range("B17").Value = "Highlights"
        ws.Range("B17").Font.Bold = True
        formula2(ws.Range("B18"), '="Top category by revenue: "&INDEX(J7:J18,MATCH(MAX(K7:K18),K7:K18,0))')
        formula2(ws.Range("B19"), '="Top category by gross profit: "&INDEX(J7:J18,MATCH(MAX(L7:L18),L7:L18,0))')
        formula2(ws.Range("B20"), ('="Products to reorder today: "&COUNTIFS(tblInventory[Status],"Stockout before restock")'
                                    '+COUNTIFS(tblInventory[Status],"Reorder now")&" ("&COUNTIFS(tblInventory[Status],"<>OK",'
                                    'tblInventory[Status],"<>Overstock",tblInventory[abc_class],"A")&" A-class)"'))
        formula2(ws.Range("B21"), '="Loss-making products in 2025: "&COUNTIFS(tblProducts[gross_profit_2025],"<0")')

        ws.Range("B23").Value = "Management alerts"
        ws.Range("B23").Font.Bold = True
        for i in range(6):
            formula2(ws.Range(f"B{24 + i}"), f'=IFERROR(INDEX(tblAlerts[icon],{i + 1})&"  "&INDEX(tblAlerts[alert],{i + 1}),"")')

        ws.Range("B31").Value = "Data quality (latest pipeline run)"
        ws.Range("B31").Font.Bold = True
        self.header(ws.Range("B32:D32"))
        ws.Range("B32:D32").Value = ("Metric", "Raw export", "Clean warehouse")
        for i, (label, field, fmt) in enumerate([("Completeness", "completeness_pct", '0.0"%"'),
                                                 ("Validity", "validity_pct", '0.0"%"'),
                                                 ("Duplicates", "duplicates_pct", '0.00"%"'),
                                                 ("Missing values", "missing_values_pct", '0.00"%"'),
                                                 ("Failed checks", "failed_checks", "0")], start=33):
            ws.Range(f"B{i}").Value = label
            formula2(ws.Range(f"C{i}"), f'=XLOOKUP("raw",tblDQ[stage],tblDQ[{field}])')
            formula2(ws.Range(f"D{i}"), f'=XLOOKUP("clean",tblDQ[stage],tblDQ[{field}])')
            ws.Range(f"C{i}:D{i}").NumberFormat = fmt

        # Trend chart from the KPI table (native chart, stays live).
        ch = ws.Shapes.AddChart2(-1, self.c.xlLine, ws.Range("J21").Left, ws.Range("J21").Top, 560, 250).Chart
        while ch.SeriesCollection().Count:
            ch.SeriesCollection(1).Delete()
        for name, field in (("Net revenue", "net_revenue"), ("Gross profit", "gross_profit")):
            s = ch.SeriesCollection().NewSeries()
            s.Name = name
            s.Values = ws.ListObjects("tblKPI").ListColumns(field).DataBodyRange
            s.XValues = ws.ListObjects("tblKPI").ListColumns("month").DataBodyRange
        ch.HasTitle = True
        ch.ChartTitle.Text = "Net revenue and gross profit by month"
        ch.Axes(self.c.xlCategory).TickLabels.NumberFormat = "mmm yy"
        ch.Axes(self.c.xlValue).TickLabels.NumberFormat = "€#,##0,\"k\""
        ws.Columns("B").ColumnWidth = 30
        ws.Columns("C:H").ColumnWidth = 16
        ws.Columns("J").ColumnWidth = 22
        ws.Columns("K:M").ColumnWidth = 16
        ws.Columns("AA:AZ").Hidden = True

    def data_dictionary(self):
        ws = self.ws["Data Dictionary"]
        self.title(ws, "Data Dictionary", "What every sheet, table and measure contains. Full version: docs/data_dictionary.md, docs/kpi_dictionary.md")
        rows = [
            ("Sheet / object", "Field", "Definition"),
            ("Measure", "Net Revenue", "Sales after discounts and refunds; cancelled orders excluded"),
            ("Measure", "Gross Profit", "Net revenue - cost of goods - outbound shipping (paid by the shop)"),
            ("Measure", "Gross Margin %", "Gross profit / net revenue"),
            ("Measure", "Discount Rate %", "Discounts / gross sales (before discount)"),
            ("Measure", "Net Revenue PY / YoY Growth %", "Same months one year earlier, and growth against them (DAX)"),
            ("Executive Summary", "Report month (C4)", "Drop-down of months in the KPI table; every formula on the sheet follows it"),
            ("Executive Summary", "Average order value", "Net revenue / fulfilled orders"),
            ("Executive Summary", "Refund rate %", "Refunded orders / fulfilled orders (lower is better)"),
            ("Executive Summary", "On-time delivery %", "Delivered within the promise: 4 days in Greece, 7 days abroad"),
            ("Raw Data (tblSales)", "Grain", "One row per month x country x category x customer type x channel"),
            ("Raw Data (tblSales)", "Customer Type", "New = customer's first fulfilled order; Returning = bought before; Guest = no account"),
            ("Raw Data (tblSales)", "orders", "Orders containing that category. An order with two categories counts in both rows, so do not add orders across categories"),
            ("Product Performance", "Revenue Rank / Profit Rank", "RANK.EQ of 2025 net revenue / gross profit across all products"),
            ("Product Performance", "Flag", "'Revenue overstates value' = top-50 by revenue but 10+ places lower by profit"),
            ("Inventory", "forecast_30d", "Units expected to sell in the next 30 days (src/forecast.py)"),
            ("Inventory", "days_cover", "Stock / forecast daily demand"),
            ("Inventory", "Status", "Stockout before restock: cover < supplier lead time; Reorder now: cover < lead time + 7 days; Overstock: > 120 days"),
            ("Inventory", "revenue_at_risk_30d", "Units short over 30 days x average net price, if nothing is ordered"),
            ("Customer Analysis", "RFM segment", "Recency quintile (1-5) and order count (1-5+); e.g. At Risk = bought 2x, not for a long time"),
            ("Customer Analysis", "Cohort retention", "% of customers whose first order was in month M who bought again N months later"),
            ("Power Query", "pDataFolder", "Folder with the pipeline's CSV output. Change it once in Data > Queries, then Refresh All"),
            ("Data model", "Relationships", "SalesSummary[month] -> Calendar[month]; SalesSummary[Country] -> Geography[country]"),
        ]
        rng = ws.Range(ws.Cells(4, 1), ws.Cells(3 + len(rows), 3))
        rng.Value = rows
        lo = ws.ListObjects.Add(1, rng, pythoncom.Missing, 1)
        lo.Name = "tblDictionary"
        lo.TableStyle = "TableStyleLight9"
        ws.Columns("A").ColumnWidth = 26
        ws.Columns("B").ColumnWidth = 32
        ws.Columns("C").ColumnWidth = 110

    # ------------------------------------------------------------------ run --
    def build(self):
        t0 = time.perf_counter()
        self.add_queries()
        self.build_model()
        self.raw_data()                  # tblSales first: other sheets' formulas use it
        self.product_performance()
        self.inventory()
        self.sales_analysis()
        self.customer_analysis()
        self.executive_summary()
        self.data_dictionary()
        self.slicers()
        self.xl.CalculateFull()
        for ws in self.ws.values():
            ws.Activate()
            self.xl.ActiveWindow.Zoom = 90
            ws.Range("A1").Select()
        self.ws["Executive Summary"].Activate()
        config.EXCEL_DIR.mkdir(exist_ok=True)
        if OUT.exists():
            OUT.unlink()
        self.wb.SaveAs(str(OUT), FileFormat=51)
        self.saved = True
        print(f"wrote {OUT.relative_to(config.ROOT)} in {time.perf_counter() - t0:.0f}s")

    def close(self):
        try:
            self.wb.Close(SaveChanges=False)
        finally:
            self.xl.Quit()


def main():
    b = Builder()
    try:
        b.build()
    finally:
        b.close()
    mark_full_recalc(OUT)


if __name__ == "__main__":
    main()
