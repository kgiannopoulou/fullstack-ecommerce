"""Generate the Power BI project (PBIP) from code.

    python src/build_powerbi.py

Writes powerbi/ecommerce_analytics.pbip with
  * ecommerce_analytics.SemanticModel/   TMDL: star schema, relationships, DAX measures,
                                          Power Query partitions reading data/cleaned/*.csv
  * ecommerce_analytics.Report/          PBIR: five report pages and their visuals
  * measures.dax                          every measure in one readable file

PBIP is Power BI's text-based project format: it opens in Power BI Desktop like a
.pbix, and every change shows up as a readable diff in git. The model is written
from the spec below so that the measures, the KPI dictionary and the SQL stay in
step. Open the .pbip in Power BI Desktop, Refresh, then File > Save as .pbix.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import config

NAME = "ecommerce_analytics"
OUT = config.POWERBI_DIR
SM = OUT / f"{NAME}.SemanticModel"
RP = OUT / f"{NAME}.Report"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
NS = uuid.UUID("6f1c8e8a-2b9e-4c43-9c1e-6a1d3b0f7e10")   # stable lineage tags -> stable git diffs


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


EUR = '\\€#,0'
EUR2 = '\\€#,0.00'
PCT = '0.0%;-0.0%;0.0%'
INT = '#,0'

# ---------------------------------------------------------------- tables --
# table -> (csv, [(column, dataType, formatString or None, summarize)], options)
T = {
    "DimDate": ("DimDate.csv", [
        ("date", "dateTime", "dd mmm yyyy", "none"), ("year", "int64", "0", "none"), ("quarter", "int64", "0", "none"),
        ("year_quarter", "string", None, "none"), ("month", "int64", "0", "none"), ("year_month", "string", None, "none"),
        ("month_name", "string", None, "none"), ("weekday_number", "int64", "0", "none"),
        ("weekday_name", "string", None, "none"), ("is_weekend", "boolean", None, "none")],
        {"date_table": True, "sort": {"month_name": "month", "weekday_name": "weekday_number"}}),
    "DimProduct": ("DimProduct.csv", [
        ("product_id", "int64", "0", "none"), ("sku", "string", None, "none"), ("product_name", "string", None, "none"),
        ("category", "string", None, "none"), ("list_price", "double", EUR2, "none"), ("unit_cost", "double", EUR2, "none"),
        ("parcel_size", "string", None, "none"), ("supplier_lead_time_days", "int64", "0", "none"),
        ("abc_class", "string", None, "none")], {}),
    "DimCustomer": ("DimCustomer.csv", [
        ("customer_id", "int64", "0", "none"), ("country", "string", None, "none"),
        ("acquisition_channel", "string", None, "none"), ("signup_date", "dateTime", "dd mmm yyyy", "none"),
        ("first_order_date", "dateTime", "dd mmm yyyy", "none"), ("cohort_month", "dateTime", "mmm yyyy", "none"),
        ("orders", "int64", "0", "sum"), ("lifetime_revenue", "double", EUR, "sum"), ("recency_days", "int64", "0", "none"),
        ("r_score", "int64", "0", "none"), ("f_score", "int64", "0", "none"), ("rfm_segment", "string", None, "none")], {}),
    "DimChannel": ("DimChannel.csv", [
        ("channel_id", "int64", "0", "none"), ("channel", "string", None, "none"), ("channel_group", "string", None, "none")], {}),
    "DimGeography": ("DimGeography.csv", [
        ("country", "string", None, "none"), ("market", "string", None, "none"),
        ("delivery_promise_days", "int64", "0", "none")], {}),
    "FactSales": ("FactSales.csv", [
        ("transaction_id", "string", None, "none"), ("order_id", "int64", "0", "none"), ("customer_id", "int64", "0", "none"),
        ("order_date", "dateTime", "dd mmm yyyy", "none"), ("product_id", "int64", "0", "none"),
        ("country", "string", None, "none"), ("channel_id", "int64", "0", "none"), ("customer_type", "string", None, "none"),
        ("is_discounted", "boolean", None, "none"), ("quantity", "int64", INT, "sum"),
        ("gross_amount", "double", EUR, "sum"), ("discount_amount", "double", EUR, "sum"),
        ("refund_amount", "double", EUR, "sum"), ("net_revenue", "double", EUR, "sum"), ("cogs", "double", EUR, "sum"),
        ("shipping_cost", "double", EUR, "sum"), ("gross_profit", "double", EUR, "sum"), ("is_bulk", "boolean", None, "none")],
        {"hidden_numeric": True}),
    "FactOrders": ("FactOrders.csv", [
        ("order_id", "int64", "0", "none"), ("customer_id", "int64", "0", "none"),
        ("order_date", "dateTime", "dd mmm yyyy", "none"), ("status", "string", None, "none"),
        ("payment_method", "string", None, "none"), ("channel_id", "int64", "0", "none"), ("country", "string", None, "none"),
        ("courier", "string", None, "none"), ("customer_type", "string", None, "none"),
        ("discount_pct", "double", "0%", "none"), ("units", "int64", INT, "sum"), ("gross_amount", "double", EUR, "sum"),
        ("discount_amount", "double", EUR, "sum"), ("refund_amount", "double", EUR, "sum"),
        ("net_revenue", "double", EUR, "sum"), ("cogs", "double", EUR, "sum"), ("shipping_cost", "double", EUR, "sum"),
        ("gross_profit", "double", EUR, "sum"), ("days_to_ship", "int64", "0", "none"),
        ("days_to_deliver", "int64", "0", "none"), ("is_late", "boolean", None, "none"),
        ("is_fulfilled", "boolean", None, "none"), ("has_bulk", "boolean", None, "none")], {"hidden_numeric": True}),
    "FactInventoryDaily": ("FactInventoryDaily.csv", [
        ("snapshot_date", "dateTime", "dd mmm yyyy", "none"), ("product_id", "int64", "0", "none"),
        ("stock_on_hand", "int64", INT, "sum"), ("units_received", "int64", INT, "sum"), ("units_sold", "int64", INT, "sum"),
        ("stock_value_at_cost", "double", EUR, "sum"), ("is_stockout", "boolean", None, "none"),
        ("est_lost_units", "double", INT, "sum"), ("est_lost_revenue", "double", EUR, "sum")], {"hidden_numeric": True}),
    "InventoryForecast": ("InventoryForecast.csv", [
        ("product_id", "int64", "0", "none"), ("sku", "string", None, "none"), ("product_name", "string", None, "none"),
        ("category", "string", None, "none"), ("abc_class", "string", None, "none"), ("stock", "int64", INT, "sum"),
        ("forecast_30d", "double", INT, "sum"), ("difference", "double", "+#,0;-#,0;0", "sum"),
        ("days_cover", "double", "0.0", "none"), ("lead_time_days", "int64", "0", "none"), ("risk", "string", None, "none"),
        ("reorder_qty", "double", INT, "sum"), ("expected_lost_units", "double", INT, "sum"),
        ("avg_net_price", "double", EUR2, "none"), ("revenue_at_risk_30d", "double", EUR, "sum"),
        ("recommended_action", "string", None, "none")], {}),
    "CohortRetention": ("CohortRetention.csv", [
        ("cohort", "dateTime", "mmm yyyy", "none"), ("month_n", "int64", "0", "none"), ("customers", "int64", INT, "sum"),
        ("cohort_size", "int64", INT, "none"), ("retention_pct", "double", "0.0", "sum")], {}),
    "ManagementAlerts": ("ManagementAlerts.csv", [
        ("alert_id", "int64", "0", "none"), ("severity", "string", None, "none"), ("icon", "string", None, "none"),
        ("area", "string", None, "none"), ("alert", "string", None, "none"), ("value", "double", "0.0", "none"),
        ("as_of", "dateTime", "dd mmm yyyy", "none")], {}),
    "Anomalies": ("Anomalies.csv", [
        ("date", "dateTime", "dd mmm yyyy", "none"), ("metric", "string", None, "none"), ("dimension", "string", None, "none"),
        ("segment", "string", None, "none"), ("actual", "double", "#,0.0", "none"), ("expected", "double", "#,0.0", "none"),
        ("deviation_pct", "double", "+0.0;-0.0", "none"), ("z_score", "double", "+0.0;-0.0", "none"),
        ("event", "string", None, "none"), ("direction", "string", None, "none"), ("severity", "string", None, "none"),
        ("description", "string", None, "none")], {}),
    "DataQualityRules": ("DataQualityRules.csv", [
        ("stage", "string", None, "none"), ("rule_id", "string", None, "none"), ("dimension", "string", None, "none"),
        ("table", "string", None, "none"), ("column", "string", None, "none"), ("rule", "string", None, "none"),
        ("records_checked", "int64", INT, "sum"), ("failures", "int64", INT, "sum"),
        ("failure_rate_pct", "double", "0.00", "none"), ("threshold_pct", "double", "0", "none"),
        ("critical", "boolean", None, "none"), ("status", "string", None, "none")], {}),
    "DataQualityScorecard": ("DataQualityScorecard.csv", [
        ("stage", "string", None, "none"), ("records", "int64", INT, "none"), ("completeness_pct", "double", "0.0", "none"),
        ("validity_pct", "double", "0.0", "none"), ("duplicates_pct", "double", "0.00", "none"),
        ("missing_values_pct", "double", "0.00", "none"), ("rules_checked", "int64", "0", "none"),
        ("failed_checks", "int64", "0", "none"), ("critical_failures", "int64", "0", "none")], {}),
}

RELATIONSHIPS = [  # (from table.column, to table.column)  many -> one
    ("FactSales.order_date", "DimDate.date"), ("FactOrders.order_date", "DimDate.date"),
    ("FactInventoryDaily.snapshot_date", "DimDate.date"),
    ("FactSales.product_id", "DimProduct.product_id"), ("FactInventoryDaily.product_id", "DimProduct.product_id"),
    ("InventoryForecast.product_id", "DimProduct.product_id"),
    ("FactSales.customer_id", "DimCustomer.customer_id"), ("FactOrders.customer_id", "DimCustomer.customer_id"),
    ("FactSales.channel_id", "DimChannel.channel_id"), ("FactOrders.channel_id", "DimChannel.channel_id"),
    ("FactSales.country", "DimGeography.country"), ("FactOrders.country", "DimGeography.country"),
]

# ------------------------------------------------------------- measures --
# table -> [(name, DAX, format, display folder, description)]
M = {
    "FactSales": [
        ("Gross Sales", "SUM ( FactSales[gross_amount] )", EUR, "Revenue", "List-price value of fulfilled lines, before discounts"),
        ("Discounts", "SUM ( FactSales[discount_amount] )", EUR, "Revenue", "Discount given on fulfilled lines"),
        ("Refunds", "SUM ( FactSales[refund_amount] )", EUR, "Revenue", "Refunded amount, allocated to lines by value"),
        ("Net Revenue", "SUM ( FactSales[net_revenue] )", EUR, "Revenue", "Gross sales - discounts - refunds; cancelled orders excluded"),
        ("Cost of Goods", "SUM ( FactSales[cogs] )", EUR, "Profit", "Units x unit cost"),
        ("Shipping Cost", "SUM ( FactSales[shipping_cost] )", EUR, "Profit", "Carrier cost paid by the shop, allocated to lines by parcel weight"),
        ("Gross Profit", "[Net Revenue] - [Cost of Goods] - [Shipping Cost]", EUR, "Profit", "Net revenue - COGS - shipping"),
        ("Gross Margin %", "DIVIDE ( [Gross Profit], [Net Revenue] )", PCT, "Profit", "Gross profit / net revenue"),
        ("Discount Rate %", "DIVIDE ( [Discounts], [Gross Sales] )", PCT, "Revenue", ""),
        ("Units Sold", "SUM ( FactSales[quantity] )", INT, "Volume", ""),
        ("Net Revenue PM", "CALCULATE ( [Net Revenue], DATEADD ( DimDate[date], -1, MONTH ) )", EUR, "Time intelligence", "Previous month"),
        ("MoM Growth %", "DIVIDE ( [Net Revenue] - [Net Revenue PM], [Net Revenue PM] )", PCT, "Time intelligence", ""),
        ("Net Revenue PY", "CALCULATE ( [Net Revenue], SAMEPERIODLASTYEAR ( DimDate[date] ) )", EUR, "Time intelligence", "Same period last year"),
        ("YoY Growth %", "DIVIDE ( [Net Revenue] - [Net Revenue PY], [Net Revenue PY] )", PCT, "Time intelligence", ""),
        ("Gross Profit PY", "CALCULATE ( [Gross Profit], SAMEPERIODLASTYEAR ( DimDate[date] ) )", EUR, "Time intelligence", ""),
        ("Gross Profit YoY %", "DIVIDE ( [Gross Profit] - [Gross Profit PY], [Gross Profit PY] )", PCT, "Time intelligence", ""),
        ("Gross Margin PY", "CALCULATE ( [Gross Margin %], SAMEPERIODLASTYEAR ( DimDate[date] ) )", PCT, "Time intelligence", ""),
        ("Gross Margin Change pp", "IF ( NOT ISBLANK ( [Gross Margin PY] ), ( [Gross Margin %] - [Gross Margin PY] ) * 100 )",
         '+0.0" pp";-0.0" pp"', "Time intelligence", "Percentage points vs same period last year"),
        ("Returning Customer Revenue", 'CALCULATE ( [Net Revenue], FactSales[customer_type] = "Returning" )', EUR, "Customers", ""),
        ("Returning Customer Revenue %", "DIVIDE ( [Returning Customer Revenue], [Net Revenue] )", PCT, "Customers",
         "Share of net revenue from customers who had bought before"),
        ("Product Revenue Rank", "IF ( HASONEVALUE ( DimProduct[product_name] ), RANKX ( ALL ( DimProduct[product_name] ), [Net Revenue] ) )",
         "0", "Profit", ""),
        ("Product Profit Rank", "IF ( HASONEVALUE ( DimProduct[product_name] ), RANKX ( ALL ( DimProduct[product_name] ), [Gross Profit] ) )",
         "0", "Profit", ""),
    ],
    "FactOrders": [
        ("Orders", "CALCULATE ( COUNTROWS ( FactOrders ), FactOrders[is_fulfilled] = TRUE () )", INT, "Volume", "Fulfilled orders"),
        ("Orders Placed", "COUNTROWS ( FactOrders )", INT, "Volume", "Including cancelled"),
        ("Orders PY", "CALCULATE ( [Orders], SAMEPERIODLASTYEAR ( DimDate[date] ) )", INT, "Time intelligence", ""),
        ("Orders YoY %", "DIVIDE ( [Orders] - [Orders PY], [Orders PY] )", PCT, "Time intelligence", ""),
        ("AOV", "DIVIDE ( SUM ( FactOrders[net_revenue] ), [Orders] )", EUR2, "Revenue", "Average order value: net revenue / fulfilled orders"),
        ("AOV PY", "CALCULATE ( [AOV], SAMEPERIODLASTYEAR ( DimDate[date] ) )", EUR2, "Time intelligence", ""),
        ("AOV YoY %", "DIVIDE ( [AOV] - [AOV PY], [AOV PY] )", PCT, "Time intelligence", ""),
        ("Customers", "CALCULATE ( DISTINCTCOUNT ( FactOrders[customer_id] ), FactOrders[is_fulfilled] = TRUE (), "
                      "NOT ISBLANK ( FactOrders[customer_id] ) )", INT, "Customers", "Active customers (guests excluded)"),
        ("New Customers", 'CALCULATE ( [Customers], FactOrders[customer_type] = "New" )', INT, "Customers",
         "Customers whose first fulfilled order is in the period"),
        ("Returning Customers", 'CALCULATE ( [Customers], FactOrders[customer_type] = "Returning" )', INT, "Customers", ""),
        ("Repeat Rate %", "DIVIDE ( [Returning Customers], [Customers] )", PCT, "Customers",
         "Share of active customers who had bought before"),
        ("Revenue per Customer", 'DIVIDE ( CALCULATE ( SUM ( FactOrders[net_revenue] ), NOT ISBLANK ( FactOrders[customer_id] ) ), [Customers] )',
         EUR2, "Customers", ""),
        ("Refund Rate %", 'DIVIDE ( CALCULATE ( COUNTROWS ( FactOrders ), FactOrders[status] = "refunded" ), [Orders] )', PCT,
         "Operations", "Refunded / fulfilled orders"),
        ("Refund Rate PY", "CALCULATE ( [Refund Rate %], SAMEPERIODLASTYEAR ( DimDate[date] ) )", PCT, "Time intelligence", ""),
        ("Cancellation Rate %", 'DIVIDE ( CALCULATE ( COUNTROWS ( FactOrders ), FactOrders[status] = "cancelled" ), [Orders Placed] )',
         PCT, "Operations", ""),
        ("On-time Delivery %", "DIVIDE ( CALCULATE ( COUNTROWS ( FactOrders ), FactOrders[is_fulfilled] = TRUE (), "
                               "FactOrders[is_late] = FALSE () ), [Orders] )", PCT, "Operations", ""),
    ],
    "FactInventoryDaily": [
        ("Stockout Rate %", "DIVIDE ( CALCULATE ( COUNTROWS ( FactInventoryDaily ), FactInventoryDaily[is_stockout] = TRUE () ), "
                            "COUNTROWS ( FactInventoryDaily ) )", PCT, "Inventory", "Share of product-days with no stock"),
        ("Estimated Lost Sales", "SUM ( FactInventoryDaily[est_lost_revenue] )", EUR, "Inventory",
         "Stockout days x demand on in-stock days x net price (upper bound)"),
        ("Avg Inventory Value", "AVERAGEX ( VALUES ( DimDate[date] ), CALCULATE ( SUM ( FactInventoryDaily[stock_value_at_cost] ) ) )",
         EUR, "Inventory", "Average daily stock value at cost"),
        ("Inventory Turnover", "DIVIDE ( [Cost of Goods], [Avg Inventory Value] )", "0.0x", "Inventory",
         "COGS in the period / average stock value"),
    ],
    "InventoryForecast": [
        ("Products At Risk", 'CALCULATE ( COUNTROWS ( InventoryForecast ), InventoryForecast[risk] IN { "STOCKOUT BEFORE RESTOCK", "REORDER NOW" } )',
         INT, "Inventory", "Will run out before (or within 7 days of) a delivery ordered today"),
        ("A-class At Risk", 'CALCULATE ( [Products At Risk], InventoryForecast[abc_class] = "A" )', INT, "Inventory", ""),
        ("Revenue At Risk 30d", 'CALCULATE ( SUM ( InventoryForecast[revenue_at_risk_30d] ), InventoryForecast[risk] IN { "STOCKOUT BEFORE RESTOCK", "REORDER NOW" } )',
         EUR, "Inventory", ""),
    ],
    "DataQualityScorecard": [
        ("DQ Completeness", 'CALCULATE ( MAX ( DataQualityScorecard[completeness_pct] ), DataQualityScorecard[stage] = "clean" ) / 100', PCT, "Data quality", ""),
        ("DQ Validity", 'CALCULATE ( MAX ( DataQualityScorecard[validity_pct] ), DataQualityScorecard[stage] = "clean" ) / 100', PCT, "Data quality", ""),
        ("DQ Duplicates", 'CALCULATE ( MAX ( DataQualityScorecard[duplicates_pct] ), DataQualityScorecard[stage] = "clean" ) / 100', "0.00%", "Data quality", ""),
        ("DQ Missing Values", 'CALCULATE ( MAX ( DataQualityScorecard[missing_values_pct] ), DataQualityScorecard[stage] = "clean" ) / 100', "0.00%", "Data quality", ""),
        ("DQ Failed Checks (raw)", 'CALCULATE ( MAX ( DataQualityScorecard[failed_checks] ), DataQualityScorecard[stage] = "raw" )', "0", "Data quality", ""),
        ("DQ Failed Checks (clean)", 'CALCULATE ( MAX ( DataQualityScorecard[failed_checks] ), DataQualityScorecard[stage] = "clean" )', "0", "Data quality", ""),
    ],
}

M_TYPES = {"string": "type text", "int64": "Int64.Type", "double": "type number", "dateTime": "type date",
           "boolean": "type logical"}


def q(name: str) -> str:
    return f"'{name}'" if any(c in name for c in " -%().") else name


# ------------------------------------------------------------------ TMDL --
def table_tmdl(name: str) -> str:
    csv, cols, opt = T[name]
    lines = [f"table {name}", f"\tlineageTag: {tag(name)}"]
    if opt.get("date_table"):
        lines.append("\tdataCategory: Time")
    lines.append("")
    for mname, dax, fmt, folder, desc in M.get(name, []):
        if desc:
            lines.append(f"\t/// {desc}")
        lines += [f"\tmeasure {q(mname)} = {dax}", f"\t\tformatString: {fmt}", f"\t\tdisplayFolder: {folder}",
                  f"\t\tlineageTag: {tag(name, 'm', mname)}", ""]
    for cname, dtype, fmt, summ in cols:
        lines.append(f"\tcolumn {q(cname)}")
        lines.append(f"\t\tdataType: {dtype}")
        if opt.get("date_table") and cname == "date":
            lines.append("\t\tisKey")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        hide = opt.get("hidden_numeric") and summ == "sum"
        if hide or cname.endswith("_id") and name.startswith("Fact"):
            lines.append("\t\tisHidden")
        lines += [f"\t\tlineageTag: {tag(name, cname)}", f"\t\tsummarizeBy: {summ}", f"\t\tsourceColumn: {cname}"]
        if cname in opt.get("sort", {}):
            lines.append(f"\t\tsortByColumn: {opt['sort'][cname]}")
        lines += ["", "\t\tannotation SummarizationSetBy = Automatic", ""]
    types = ", ".join(f'{{"{c}", {M_TYPES[d]}}}' for c, d, _, _ in cols)
    lines += [
        f"\tpartition {name} = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\t\tlet",
        f'\t\t\t\t    Source = Csv.Document(File.Contents(DataFolder & "{csv}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "\t\t\t\t    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f'\t\t\t\t    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")',
        "\t\t\t\tin",
        "\t\t\t\t    Typed",
        "",
        "\tannotation PBI_ResultType = Table",
        "",
    ]
    return "\n".join(lines)


def write_model():
    d = SM / "definition"
    (d / "tables").mkdir(parents=True, exist_ok=True)
    (SM / "definition.pbism").write_text(json.dumps({"version": "4.0", "settings": {}}, indent=2), encoding="utf-8")
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1600\n", encoding="utf-8")
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
             f"annotation PBI_QueryOrder = {json.dumps(['DataFolder', *T])}", "",
             "annotation __PBI_TimeIntelligenceEnabled = 0", ""]
    model += [f"ref table {t}" for t in T]
    (d / "model.tmdl").write_text("\n".join(model) + "\n", encoding="utf-8")
    folder = str(config.CLEAN_DIR) + "\\"
    (d / "expressions.tmdl").write_text(
        "/// Folder with the CSV files written by the pipeline (data/cleaned). Change it after cloning the repo.\n"
        f'expression DataFolder = "{folder}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {tag('DataFolder')}\n\n\tannotation PBI_ResultType = Text\n", encoding="utf-8")
    rel = []
    for f, t in RELATIONSHIPS:
        ft, fc = f.split(".")
        tt, tc = t.split(".")
        rel += [f"relationship {tag('rel', f, t)}", f"\tfromColumn: {ft}.{q(fc)}", f"\ttoColumn: {tt}.{q(tc)}", ""]
    (d / "relationships.tmdl").write_text("\n".join(rel), encoding="utf-8")
    for t in T:
        (d / "tables" / f"{t}.tmdl").write_text(table_tmdl(t), encoding="utf-8")


# ------------------------------------------------------------------ PBIR --
def lit(v) -> dict:
    if isinstance(v, bool):
        return {"expr": {"Literal": {"Value": "true" if v else "false"}}}
    if isinstance(v, (int, float)):
        return {"expr": {"Literal": {"Value": f"{v}D"}}}
    return {"expr": {"Literal": {"Value": f"'{v}'"}}}


def measure(table: str, name: str) -> dict:
    return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
            "queryRef": f"{table}.{name}", "nativeQueryRef": name}


def column(table: str, name: str, agg: int | None = None) -> dict:
    col = {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}
    if agg is None:
        return {"field": col, "queryRef": f"{table}.{name}", "nativeQueryRef": name}
    fn = {0: "Sum", 1: "Avg", 3: "Min", 4: "Max"}[agg]
    return {"field": {"Aggregation": {"Expression": col, "Function": agg}},
            "queryRef": f"{fn}({table}.{name})", "nativeQueryRef": f"{fn} of {name}"}


class Page:
    def __init__(self, pid: str, title: str):
        self.pid, self.title, self.visuals = pid, title, []

    def add(self, vtype: str, x, y, w, h, roles: dict, title: str | None = None, objects: dict | None = None,
            sort: dict | None = None, extra: dict | None = None):
        n = len(self.visuals) + 1
        visual = {"visualType": vtype,
                  "query": {"queryState": {r: {"projections": p} for r, p in roles.items()}},
                  "drillFilterOtherVisuals": True}
        if sort:
            visual["query"]["sortDefinition"] = sort
        if objects:
            visual["objects"] = objects
        vco = {"title": [{"properties": {"show": lit(bool(title)), **({"text": lit(title)} if title else {})}}]}
        if vtype != "slicer":
            vco["border"] = [{"properties": {"show": lit(True), "color": {"solid": {"color": lit("#E4E3DF")}}, "radius": lit(6)}}]
        visual["visualContainerObjects"] = vco
        if extra:
            visual.update(extra)
        self.visuals.append({
            "$schema": f"{SCHEMA}/visualContainer/1.4.0/schema.json",
            "name": f"{self.pid}v{n:02d}",
            "position": {"x": x, "y": y, "z": n * 1000, "width": w, "height": h, "tabOrder": n * 1000},
            "visual": visual,
        })


def card(page: Page, x, y, table, name, label):
    page.add("card", x, y, 200, 105, {"Values": [measure(table, name)]}, title=None,
             objects={"labels": [{"properties": {"fontSize": lit(22)}}],
                      "categoryLabels": [{"properties": {"show": lit(True)}}]},
             extra={"visualContainerObjects": {"title": [{"properties": {"show": lit(True), "text": lit(label)}}]}})


def slicer(page: Page, x, y, w, table, col, title, h=60, dropdown=True):
    obj = {"data": [{"properties": {"mode": lit("Dropdown" if dropdown else "Basic")}}]}
    page.add("slicer", x, y, w, h, {"Values": [column(table, col)]}, title=title, objects=obj)


def pages() -> list[Page]:
    ps = []
    W = 1280

    # 1 ---------------------------------------------------- Executive Overview
    p = Page("p1", "Executive Overview")
    slicer(p, 20, 10, 180, "DimDate", "year", "Year")
    slicer(p, 210, 10, 180, "DimGeography", "country", "Country")
    for i, (t, m, lab) in enumerate([("FactSales", "Net Revenue", "Net revenue"), ("FactSales", "Gross Profit", "Gross profit"),
                                     ("FactOrders", "Orders", "Orders"), ("FactOrders", "AOV", "Average order value")]):
        card(p, 20 + i * 215, 80, t, m, lab)
    for i, (t, m, lab) in enumerate([("FactSales", "YoY Growth %", "Net revenue YoY"),
                                     ("FactSales", "Gross Profit YoY %", "Gross profit YoY"),
                                     ("FactOrders", "Orders YoY %", "Orders YoY"), ("FactOrders", "AOV YoY %", "AOV YoY")]):
        p.add("card", 20 + i * 215, 190, 200, 60, {"Values": [measure(t, m)]},
              objects={"labels": [{"properties": {"fontSize": lit(14)}}], "categoryLabels": [{"properties": {"show": lit(False)}}]},
              extra={"visualContainerObjects": {"title": [{"properties": {"show": lit(True), "text": lit(lab)}}]}})
    p.add("tableEx", 885, 80, 375, 290, {"Values": [column("ManagementAlerts", "icon"), column("ManagementAlerts", "alert")]},
          title="Management alerts")
    p.add("lineChart", 20, 265, 580, 215, {"Category": [column("DimDate", "year_month")],
                                           "Y": [measure("FactSales", "Net Revenue"), measure("FactSales", "Net Revenue PY")]},
          title="Monthly net revenue vs last year")
    p.add("lineChart", 610, 380, 650, 100 + 0, {"Category": [column("DimDate", "year_month")],
                                                "Y": [measure("FactSales", "Gross Margin %")]}, title="Gross margin trend")
    p.add("clusteredBarChart", 20, 490, 400, 220, {"Category": [column("DimProduct", "category")],
                                                    "Y": [measure("FactSales", "Net Revenue"), measure("FactSales", "Gross Profit")]},
          title="Revenue and gross profit by category",
          sort={"sort": [{"field": measure("FactSales", "Net Revenue")["field"], "direction": "Descending"}]})
    p.add("clusteredColumnChart", 430, 490, 380, 220, {"Category": [column("DimDate", "year")],
                                                        "Series": [column("FactSales", "customer_type")],
                                                        "Y": [measure("FactSales", "Net Revenue")]},
          title="New vs returning customer revenue")
    p.add("tableEx", 820, 490, 440, 220, {"Values": [column("DimProduct", "product_name"), measure("FactSales", "Net Revenue"),
                                                     measure("FactSales", "Gross Profit"), measure("FactSales", "Gross Margin %")]},
          title="Top products by gross profit",
          sort={"sort": [{"field": measure("FactSales", "Gross Profit")["field"], "direction": "Descending"}]})
    ps.append(p)

    # 2 ------------------------------------------- Sales & Product Performance
    p = Page("p2", "Sales & Product Performance")
    slicer(p, 20, 10, 240, "DimDate", "date", "Date", dropdown=False)
    slicer(p, 270, 10, 180, "DimGeography", "country", "Country")
    slicer(p, 460, 10, 180, "DimProduct", "category", "Category")
    slicer(p, 650, 10, 220, "DimProduct", "product_name", "Product")
    for i, (t, m, lab) in enumerate([("FactSales", "Net Revenue", "Revenue"), ("FactSales", "Gross Profit", "Profit"),
                                     ("FactSales", "Gross Margin %", "Margin"), ("FactSales", "Units Sold", "Units"),
                                     ("FactSales", "YoY Growth %", "Growth (YoY)")]):
        card(p, 20 + i * 250, 80, t, m, lab)
    p.add("scatterChart", 20, 195, 620, 515, {"Category": [column("DimProduct", "product_name")],
                                              "Series": [column("DimProduct", "abc_class")],
                                              "X": [measure("FactSales", "Net Revenue")],
                                              "Y": [measure("FactSales", "Gross Margin %")]},
          title="Revenue vs margin by product: high revenue, low margin = bottom right")
    p.add("tableEx", 650, 195, 610, 300, {"Values": [column("DimProduct", "product_name"), measure("FactSales", "Net Revenue"),
                                                     measure("FactSales", "Product Revenue Rank"),
                                                     measure("FactSales", "Product Profit Rank"),
                                                     measure("FactSales", "Gross Margin %"), measure("FactSales", "Discounts"),
                                                     measure("FactSales", "Shipping Cost")]},
          title="Products: revenue rank vs profit rank",
          sort={"sort": [{"field": measure("FactSales", "Net Revenue")["field"], "direction": "Descending"}]})
    p.add("clusteredBarChart", 650, 505, 610, 205, {"Category": [column("DimProduct", "category")],
                                                    "Y": [measure("FactSales", "Gross Margin %")]},
          title="Gross margin by category",
          sort={"sort": [{"field": measure("FactSales", "Gross Margin %")["field"], "direction": "Descending"}]})
    ps.append(p)

    # 3 --------------------------------------------------- Customer Analytics
    p = Page("p3", "Customer Analytics")
    slicer(p, 20, 10, 180, "DimDate", "year", "Year")
    slicer(p, 210, 10, 180, "DimGeography", "country", "Country")
    for i, (t, m, lab) in enumerate([("FactOrders", "Customers", "Customers"), ("FactOrders", "New Customers", "New customers"),
                                     ("FactOrders", "Returning Customers", "Returning customers"),
                                     ("FactOrders", "Repeat Rate %", "Repeat rate"),
                                     ("FactOrders", "Revenue per Customer", "Revenue / customer")]):
        card(p, 20 + i * 250, 80, t, m, lab)
    p.add("clusteredBarChart", 20, 195, 420, 255, {"Category": [column("DimCustomer", "rfm_segment")],
                                                   "Y": [measure("FactSales", "Net Revenue")]},
          title="Revenue by RFM segment",
          sort={"sort": [{"field": measure("FactSales", "Net Revenue")["field"], "direction": "Descending"}]})
    p.add("tableEx", 450, 195, 400, 255, {"Values": [column("DimCustomer", "rfm_segment"), measure("FactOrders", "Customers"),
                                                     measure("FactSales", "Net Revenue"),
                                                     measure("FactOrders", "Revenue per Customer")]},
          title="Customer segments")
    p.add("lineChart", 860, 195, 400, 255, {"Category": [column("DimDate", "year_month")],
                                            "Y": [measure("FactSales", "Returning Customer Revenue %")]},
          title="Returning-customer share of revenue")
    grad = {"FillRule": {"Input": {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Entity": "CohortRetention"}},
                                                                             "Property": "retention_pct"}}, "Function": 0}},
                         "FillRule": {"linearGradient2": {"min": {"color": {"Literal": {"Value": "'#FFFFFF'"}}},
                                                          "max": {"color": {"Literal": {"Value": "'#2A78D6'"}}},
                                                          "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}}}}}}
    p.add("pivotTable", 20, 460, 1240, 250, {"Rows": [column("CohortRetention", "cohort")],
                                            "Columns": [column("CohortRetention", "month_n")],
                                            "Values": [column("CohortRetention", "retention_pct", 0)]},
          title="Cohort retention: % of each first-order month buying again N months later",
          objects={"values": [{"properties": {"backColor": {"solid": {"color": {"expr": grad}}}},
                               "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}],
                                            "metadata": "Sum(CohortRetention.retention_pct)"}}]})
    ps.append(p)

    # 4 ---------------------------------------------- Inventory & Operations
    p = Page("p4", "Inventory & Operations")
    slicer(p, 20, 10, 180, "DimDate", "year", "Year")
    slicer(p, 210, 10, 180, "DimProduct", "category", "Category")
    for i, (t, m, lab) in enumerate([("FactInventoryDaily", "Stockout Rate %", "Stockout rate"),
                                     ("FactInventoryDaily", "Inventory Turnover", "Inventory turnover"),
                                     ("InventoryForecast", "Products At Risk", "Products at risk"),
                                     ("FactInventoryDaily", "Estimated Lost Sales", "Est. lost sales"),
                                     ("FactOrders", "Cancellation Rate %", "Cancellation rate"),
                                     ("FactOrders", "Refund Rate %", "Refund rate")]):
        card(p, 20 + i * 208, 80, t, m, lab)
    p.add("tableEx", 20, 195, 1240, 300, {"Values": [column("InventoryForecast", "sku"), column("InventoryForecast", "product_name"),
                                                     column("InventoryForecast", "abc_class"),
                                                     column("InventoryForecast", "stock", 0),
                                                     column("InventoryForecast", "forecast_30d", 0),
                                                     column("InventoryForecast", "days_cover", 0),
                                                     column("InventoryForecast", "risk"),
                                                     column("InventoryForecast", "recommended_action")]},
          title="Stock vs 30-day forecast: SKU | Product | Stock | Demand | Days cover | Risk | Recommended action",
          sort={"sort": [{"field": column("InventoryForecast", "days_cover", 0)["field"], "direction": "Ascending"}]})
    p.add("lineChart", 20, 505, 620, 205, {"Category": [column("DimDate", "year_month")],
                                           "Y": [measure("FactOrders", "On-time Delivery %")]}, title="On-time delivery")
    p.add("clusteredBarChart", 650, 505, 610, 205, {"Category": [column("DimProduct", "category")],
                                                    "Y": [measure("FactInventoryDaily", "Estimated Lost Sales")]},
          title="Estimated lost sales from stockouts by category",
          sort={"sort": [{"field": measure("FactInventoryDaily", "Estimated Lost Sales")["field"], "direction": "Descending"}]})
    ps.append(p)

    # 5 --------------------------------------------------------- Data Quality
    p = Page("p5", "Data Quality")
    for i, (m, lab) in enumerate([("DQ Completeness", "Completeness"), ("DQ Validity", "Validity"),
                                  ("DQ Duplicates", "Duplicates"), ("DQ Missing Values", "Missing values"),
                                  ("DQ Failed Checks (raw)", "Failed checks: raw export"),
                                  ("DQ Failed Checks (clean)", "Failed checks: clean")]):
        card(p, 20 + i * 208, 20, "DataQualityScorecard", m, lab)
    p.add("tableEx", 20, 140, 1240, 330, {"Values": [column("DataQualityRules", "stage"), column("DataQualityRules", "rule_id"),
                                                     column("DataQualityRules", "dimension"), column("DataQualityRules", "rule"),
                                                     column("DataQualityRules", "failures", 0),
                                                     column("DataQualityRules", "failure_rate_pct", 0),
                                                     column("DataQualityRules", "status")]},
          title="Validation rules (src/validate.py): raw export vs clean warehouse")
    p.add("tableEx", 20, 480, 1240, 230, {"Values": [column("Anomalies", "date"), column("Anomalies", "metric"),
                                                     column("Anomalies", "segment"),
                                                     column("Anomalies", "deviation_pct", 0), column("Anomalies", "z_score", 0),
                                                     column("Anomalies", "event")]},
          title="Anomalies detected (src/anomaly_detection.py)",
          sort={"sort": [{"field": column("Anomalies", "date")["field"], "direction": "Descending"}]})
    ps.append(p)
    return ps


def write_report():
    d = RP / "definition"
    if d.exists():
        shutil.rmtree(d)
    (d / "pages").mkdir(parents=True)
    (RP / "definition.pbir").write_text(json.dumps(
        {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}}, indent=2), encoding="utf-8")
    (d / "version.json").write_text(json.dumps(
        {"$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}, indent=2), encoding="utf-8")
    theme_dir = RP / "StaticResources" / "SharedResources" / "BaseThemes"
    theme = next(theme_dir.glob("*.json"), None) if theme_dir.exists() else None
    report = {"$schema": f"{SCHEMA}/report/1.2.0/schema.json", "layoutOptimization": "None",
              "themeCollection": {}, "settings": {"useStylableVisualContainerHeader": True,
                                                  "defaultDrillFilterOtherVisuals": True}}
    if theme:   # copied from a Desktop-saved project: keep using it
        report["themeCollection"]["baseTheme"] = {"name": theme.stem, "reportVersionAtImport": "5.59",
                                                  "type": "SharedResources"}
    (d / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    ps = pages()
    (d / "pages" / "pages.json").write_text(json.dumps(
        {"$schema": f"{SCHEMA}/pagesMetadata/1.0.0/schema.json", "pageOrder": [p.pid for p in ps],
         "activePageName": ps[0].pid}, indent=2), encoding="utf-8")
    for p in ps:
        pd_ = d / "pages" / p.pid
        (pd_ / "visuals").mkdir(parents=True)
        (pd_ / "page.json").write_text(json.dumps(
            {"$schema": f"{SCHEMA}/page/1.3.0/schema.json", "name": p.pid, "displayName": p.title,
             "displayOption": "FitToPage", "height": 720, "width": 1280}, indent=2), encoding="utf-8")
        for v in p.visuals:
            vd = pd_ / "visuals" / v["name"]
            vd.mkdir()
            (vd / "visual.json").write_text(json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")


def write_pbip():
    (OUT / f"{NAME}.pbip").write_text(json.dumps(
        {"$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
         "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
         "settings": {"enableAutoRecovery": True}}, indent=2), encoding="utf-8")
    (OUT / ".gitignore").write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\n", encoding="utf-8")


def write_measures_dax():
    out = ["// DAX measures of the Power BI semantic model, generated by src/build_powerbi.py.",
           "// Definitions match docs/kpi_dictionary.md and the SQL views (sql/00_schema.sql).",
           "// Star schema: FactSales / FactOrders / FactInventoryDaily -> DimDate, DimProduct,",
           "//              DimCustomer, DimChannel, DimGeography (see powerbi/README.md).", ""]
    for table, ms in M.items():
        out += [f"// ---- {table} " + "-" * (70 - len(table)), ""]
        for name, dax, fmt, folder, desc in ms:
            if desc:
                out.append(f"// {desc}")
            out += [f"{name} =", f"    {dax}", ""]
    (OUT / "measures.dax").write_text("\n".join(out), encoding="utf-8")


def main():
    OUT.mkdir(exist_ok=True)
    write_model()
    write_report()
    write_pbip()
    write_measures_dax()
    n = sum(len(v) for v in M.values())
    print(f"wrote powerbi/{NAME}.pbip: {len(T)} tables, {len(RELATIONSHIPS)} relationships, {n} measures, 5 pages")


if __name__ == "__main__":
    main()
