"""Forecast: which products will run out of stock in the next 30 days?

Revenue forecasts are interesting; stock decisions are useful. For each SKU:

  base rate   average daily units over the last 8 weeks, counting only days
              the product was in stock (a sold-out day shows 0 sales, but
              demand was not 0: those days would bias the forecast down)
  seasonality how the same 30 days compared with the same 8 weeks one year
              earlier, per category (e.g. January vs Nov-Dec)

  forecast_30d = base rate x seasonality x 30

Backtested on the four previous months against a naive "same as the last 30
days" forecast, so the method has to earn its place. A damped trend term was
tried as well (last 4 weeks vs the 4 before); it made every backtest month
worse and biased the forecast upwards, so it was removed.

Risk is judged against the supplier lead time, not against 30 days: most
SKUs are replenished every few weeks, so "less than 30 days of stock" is
normal. What matters is whether stock lasts until a new delivery can arrive.

Outputs: reports/stockout_forecast.csv, reports/forecast_report.md,
         data/cleaned/InventoryForecast.csv

    python src/forecast.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
import db
import extract

HORIZON = 30
BASE_DAYS = 56
SAFETY_DAYS = 7


def available(inv: pd.DataFrame) -> pd.Series:
    """In stock at some point in the day: sold something, or ended the day with stock."""
    return (inv["units_sold"] > 0) | (inv["stock_on_hand"] > 0)


def forecast(inv: pd.DataFrame, as_of: pd.Timestamp, horizon: int = HORIZON) -> pd.DataFrame:
    d = inv["snapshot_date"]
    base = inv[(d > as_of - pd.Timedelta(days=BASE_DAYS)) & (d <= as_of)]
    avail = base[available(base)]
    rate = avail.groupby("product_id")["units_sold"].mean()
    in_stock_days = avail.groupby("product_id").size()

    # Seasonality per category from the same calendar windows one year (52 weeks) earlier.
    ly = as_of - pd.Timedelta(days=364)
    cat = inv.drop_duplicates("product_id").set_index("product_id")["category"]
    by_cat = inv.assign(category=inv["product_id"].map(cat))
    ly_base = by_cat[(d > ly - pd.Timedelta(days=BASE_DAYS)) & (d <= ly)].groupby("category")["units_sold"].sum() / BASE_DAYS
    ly_next = by_cat[(d > ly) & (d <= ly + pd.Timedelta(days=horizon))].groupby("category")["units_sold"].sum() / horizon
    season = (ly_next / ly_base).replace([np.inf, -np.inf], np.nan).fillna(1.0).clip(0.5, 2.0)

    out = pd.DataFrame({"base_rate": rate, "in_stock_days": in_stock_days})
    out["category"] = out.index.map(cat)
    out["seasonality"] = out["category"].map(season).fillna(1.0)
    out["daily_forecast"] = out["base_rate"] * out["seasonality"]
    out["forecast"] = out["daily_forecast"] * horizon
    return out


def naive(inv: pd.DataFrame, as_of: pd.Timestamp, horizon: int = HORIZON) -> pd.Series:
    d = inv["snapshot_date"]
    last = inv[(d > as_of - pd.Timedelta(days=horizon)) & (d <= as_of)]
    return last.groupby("product_id")["units_sold"].sum() * horizon / horizon


def backtest(inv: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    """Score against products that stayed in stock for the whole horizon (otherwise sales != demand)."""
    d = inv["snapshot_date"]
    nxt = inv[(d > as_of) & (d <= as_of + pd.Timedelta(days=HORIZON))]
    fully = nxt.groupby("product_id").apply(lambda g: available(g).all(), include_groups=False)
    actual = nxt.groupby("product_id")["units_sold"].sum()[fully]
    f = forecast(inv, as_of)["forecast"].reindex(actual.index).fillna(0)
    n = naive(inv, as_of).reindex(actual.index).fillna(0)
    wape = lambda pred: 100 * (pred - actual).abs().sum() / actual.sum()
    return {"forecast_from": (as_of + pd.Timedelta(days=1)).date(), "products_scored": len(actual),
            "actual_units": int(actual.sum()), "wape_method_pct": round(wape(f), 1), "wape_naive_pct": round(wape(n), 1),
            "bias_method_pct": round(100 * (f.sum() / actual.sum() - 1), 1)}


def stock_position(inv: pd.DataFrame, fc: pd.DataFrame, prices: pd.Series, abc: pd.Series, as_of: pd.Timestamp) -> pd.DataFrame:
    last = inv[inv["snapshot_date"] == as_of].set_index("product_id")
    t = last[["sku", "product_name", "category", "unit_cost", "supplier_lead_time_days", "stock_on_hand"]].join(fc[["forecast", "daily_forecast"]], how="inner")
    t = t[t["forecast"] > 0.5]
    t["abc_class"] = t.index.map(abc).fillna("C")
    t["difference"] = t["stock_on_hand"] - t["forecast"]
    t["days_cover"] = t["stock_on_hand"] / t["daily_forecast"]
    lead = t["supplier_lead_time_days"]
    t["reorder_qty"] = np.ceil(np.maximum(t["daily_forecast"] * (lead + HORIZON + SAFETY_DAYS) - t["stock_on_hand"], 0))
    # If ordered today, stock arrives after the lead time: units short until then are lost.
    t["expected_lost_units"] = np.maximum(t["daily_forecast"] * lead - t["stock_on_hand"], 0)
    t["avg_net_price"] = t.index.map(prices).fillna(0)
    t["revenue_at_risk_30d"] = np.maximum(-t["difference"], 0) * t["avg_net_price"]
    t["risk"] = np.select(
        [t["days_cover"] < lead, t["days_cover"] < lead + SAFETY_DAYS, t["days_cover"] > 120],
        ["STOCKOUT BEFORE RESTOCK", "REORDER NOW", "OVERSTOCK"], "OK")
    t["recommended_action"] = np.select(
        [t["risk"] == "STOCKOUT BEFORE RESTOCK", t["risk"] == "REORDER NOW", t["risk"] == "OVERSTOCK"],
        ["Order " + t["reorder_qty"].astype(int).astype(str) + " units today and expedite"
         + np.where(t["expected_lost_units"].round() >= 1,
                    " (~" + t["expected_lost_units"].round().astype(int).astype(str) + " units of demand will go unserved)", ""),
         "Order " + t["reorder_qty"].astype(int).astype(str) + " units today",
         "Pause reorders; review price or promote",
         ], "No action")
    t = t.reset_index().rename(columns={"stock_on_hand": "stock", "forecast": "forecast_30d",
                                        "supplier_lead_time_days": "lead_time_days"})
    order = {"STOCKOUT BEFORE RESTOCK": 0, "REORDER NOW": 1, "OVERSTOCK": 2, "OK": 3}
    t = t.sort_values(["risk", "revenue_at_risk_30d"], key=lambda s: s.map(order) if s.name == "risk" else -s)
    cols = ["product_id", "sku", "product_name", "category", "abc_class", "stock", "forecast_30d", "difference",
            "days_cover", "lead_time_days", "risk", "reorder_qty", "expected_lost_units", "avg_net_price",
            "revenue_at_risk_30d", "recommended_action"]
    t = t[cols]
    return t.round({"forecast_30d": 0, "difference": 0, "days_cover": 1, "expected_lost_units": 0, "revenue_at_risk_30d": 0})


def write_report(pos: pd.DataFrame, bt: pd.DataFrame, as_of: pd.Timestamp):
    risky = pos[pos["risk"].isin(["STOCKOUT BEFORE RESTOCK", "REORDER NOW"])]
    lines = [
        "# 30-day stockout forecast", "",
        f"Stock position on **{as_of:%d %b %Y}**, demand forecast for the next {HORIZON} days.",
        "Generated by [`src/forecast.py`](../src/forecast.py).", "",
        "| | |", "|---|---:|",
        f"| Products forecast | {len(pos)} |",
        f"| Will run out before a reorder placed today can arrive | **{(pos['risk'] == 'STOCKOUT BEFORE RESTOCK').sum()}** |",
        f"| Must be reordered today (cover < lead time + {SAFETY_DAYS} safety days) | **{(pos['risk'] == 'REORDER NOW').sum()}** |",
        f"| ...of the two groups above, A-class (top 80% of revenue) | {(risky['abc_class'] == 'A').sum()} |",
        f"| Demand that cannot be served even if ordered today | {risky['expected_lost_units'].sum():,.0f} units, "
        f"EUR {(risky['expected_lost_units'] * risky['avg_net_price']).sum():,.0f} |",
        f"| Revenue at risk in the next 30 days if nothing is ordered | **EUR {risky['revenue_at_risk_30d'].sum():,.0f}** |",
        f"| Products with less stock than their 30-day forecast (normal between deliveries) | {(pos['difference'] < 0).sum()} |",
        f"| Overstocked (> 120 days of cover) | {(pos['risk'] == 'OVERSTOCK').sum()} |", "",
        "## Reorder list", "",
        "| SKU | Product | Class | Stock | 30d forecast | Difference | Days cover | Lead time | Action |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in risky.head(25).itertuples():
        lines.append(f"| {r.sku} | {r.product_name} | {r.abc_class} | {r.stock:,} | {r.forecast_30d:,.0f} | "
                     f"{r.difference:+,.0f} ⚠ | {r.days_cover:.1f} | {r.lead_time_days} | {r.recommended_action} |")
    lines += [
        "", "## Does the forecast work? Backtest", "",
        "The same method, run as if it were the end of each of the previous four months, scored against what",
        "actually sold (products that stayed in stock the whole month, because a sold-out product's sales",
        "are not its demand). WAPE = total absolute error / total units sold, lower is better.", "",
        "| Forecast from | Products | Units sold | WAPE, this method | WAPE, naive (last 30 days) | Bias |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in bt.itertuples():
        lines.append(f"| {r.forecast_from} | {r.products_scored} | {r.actual_units:,} | {r.wape_method_pct}% | "
                     f"{r.wape_naive_pct}% | {r.bias_method_pct:+.1f}% |")
    lines += [
        "", "## Limitations", "",
        "- Purchase orders already in transit are not in the export, so 'stock' is stock on hand. A product",
        "  flagged here may already have a delivery on its way; the list is a check-list for purchasing, not an order.",
        "- Seasonality comes from one previous year. With one year, a one-off event last January would be",
        "  repeated; more history would allow a proper seasonal model.",
        "- Demand on sold-out days is unknown. Using in-stock days only avoids under-forecasting, but",
        "  cannot see demand that went to a competitor before the product sold out.",
        "",
    ]
    (config.REPORTS_DIR / "forecast_report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    as_of = pd.Timestamp(config.AS_OF)
    with db.connect() as conn:
        inv = extract.daily_inventory(conn)
        prices = db.query(conn, f"""
            SELECT product_id, (sum(net_revenue) / sum(quantity))::float AS p FROM clean.sales_lines
            WHERE order_date > '{as_of.date()}'::date - 90 GROUP BY 1""").set_index("product_id")["p"]
        abc = db.query(conn, "SELECT product_id, abc_class FROM reporting.dim_product").set_index("product_id")["abc_class"]
    inv["snapshot_date"] = pd.to_datetime(inv["snapshot_date"])

    bt = pd.DataFrame([backtest(inv, as_of - pd.offsets.MonthEnd(k)) for k in (4, 3, 2, 1)])
    pos = stock_position(inv, forecast(inv, as_of), prices, abc, as_of)

    pos.to_csv(config.REPORTS_DIR / "stockout_forecast.csv", index=False)
    config.CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    pos.to_csv(config.CLEAN_DIR / "InventoryForecast.csv", index=False)
    bt.to_csv(config.REPORTS_DIR / "forecast_backtest.csv", index=False)
    write_report(pos, bt, as_of)
    print(bt.to_string(index=False))
    print(pos["risk"].value_counts().to_string())
    print(pos.head(8)[["sku", "product_name", "abc_class", "stock", "forecast_30d", "difference", "risk"]].to_string(index=False))


if __name__ == "__main__":
    main()
