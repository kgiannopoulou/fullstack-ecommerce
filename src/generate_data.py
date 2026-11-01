"""Simulate two years of e-commerce history and export it the way a messy
legacy system would: inconsistent formats, duplicates, gaps and bad values.

The simulation is deterministic (fixed seed) and has business events built
in for the analysis to discover, the way they would be in real data:

  * steady growth with weekly and seasonal patterns (Black Friday, December)
  * a long-tail catalogue: a minority of SKUs earns most of the revenue
  * products that grow, decline or are discontinued
  * weak reorder policies on some best-sellers -> repeated stockouts
  * overstocked slow movers -> excess and dead stock
  * a loyalty programme (LOYALTY_LAUNCH) and a faster courier for Greece
    (COURIER_SWITCH), both of which lift repeat purchasing
  * late deliveries that make customers less likely to come back

  * free shipping for the customer, paid by the shop: carrier cost depends on
    the courier, the destination and how bulky the parcel is, so some
    high-revenue products earn far less than their revenue suggests

Output: data/raw/raw_{products,customers,transactions,inventory}.csv

    python src/generate_data.py [--scale 1.0]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import config

CATEGORIES = {
    # category: (price median EUR, price spread, demand weight, example names)
    "Audio": (79, 0.55, 1.30, ["Wireless Headphones", "Bluetooth Speaker", "Earbuds", "Soundbar", "Studio Headphones"]),
    "Computer Accessories": (39, 0.60, 1.40, ["Mechanical Keyboard", "Wireless Mouse", "USB-C Hub", "Laptop Stand", "Webcam", "Monitor Arm"]),
    "Phone Accessories": (22, 0.50, 1.35, ["Phone Charger", "Phone Case", "Power Bank", "Car Mount", "Screen Protector"]),
    "Smart Home": (55, 0.60, 0.80, ["Smart Plug", "Smart Bulb", "Security Camera", "Video Doorbell", "Motion Sensor"]),
    "Gaming": (64, 0.65, 0.75, ["Gaming Headset", "Game Controller", "Gaming Mouse Pad", "Capture Card"]),
    "Home & Kitchen": (29, 0.55, 1.00, ["Ceramic Coffee Mug", "Water Bottle", "Coffee Grinder", "Kitchen Scale", "Tea Kettle"]),
    "Office": (18, 0.60, 0.85, ["Notebook Set", "Desk Lamp", "Cable Organizer", "Desk Mat", "Pen Set"]),
    "Bags & Travel": (49, 0.45, 0.70, ["Canvas Backpack", "Laptop Sleeve", "Travel Organizer", "Duffel Bag"]),
    "Fitness": (34, 0.60, 0.65, ["Yoga Mat", "Resistance Bands", "Fitness Tracker", "Foam Roller"]),
    "Cameras": (189, 0.55, 0.30, ["Action Camera", "Vintage Camera", "Camera Tripod", "Ring Light"]),
    "Wearables": (119, 0.50, 0.45, ["Smartwatch", "Watch Strap", "Fitness Band"]),
    "Books & Prints": (21, 0.55, 0.40, ["Art Print", "Photo Book", "Limited Edition Print", "Poster Set"]),
}

COUNTRIES = {
    # country: (share of customers, delivery days before / after courier switch, SLA days)
    "Greece": (0.52, (3.6, 2.1), 3),
    "Cyprus": (0.11, (5.0, 4.8), 6),
    "Germany": (0.09, (5.6, 5.4), 6),
    "Italy": (0.07, (5.8, 5.6), 6),
    "France": (0.06, (5.9, 5.7), 6),
    "Netherlands": (0.05, (5.4, 5.3), 6),
    "Spain": (0.05, (6.1, 5.9), 6),
    "Bulgaria": (0.05, (4.6, 4.5), 6),
}

# Spellings the legacy exports actually contain.
COUNTRY_VARIANTS = {
    "Greece": ["GR", "greece", "Hellas", "GREECE", "Ελλάδα", "Greece "],
    "Cyprus": ["CY", "cyprus", "Κύπρος"],
    "Germany": ["DE", "Deutschland", "germany"],
    "Italy": ["IT", "Italia", "italy"],
    "France": ["FR", "france"],
    "Netherlands": ["NL", "Holland", "The Netherlands"],
    "Spain": ["ES", "España", "spain"],
    "Bulgaria": ["BG", "bulgaria"],
}

CHANNELS = ["Organic Search", "Paid Search", "Social", "Email", "Marketplace", "Direct"]
CHANNEL_P = [0.28, 0.22, 0.16, 0.10, 0.09, 0.15]
PAYMENTS = ["Card", "PayPal", "Cash on Delivery", "Bank Transfer", "Apple Pay"]
PAYMENT_P = [0.57, 0.19, 0.16, 0.05, 0.03]

# Parcel size drives the carrier's per-unit charge (EUR per unit shipped).
PARCEL_SIZE = {
    "Phone Accessories": "S", "Office": "S", "Books & Prints": "S", "Wearables": "S",
    "Audio": "M", "Computer Accessories": "M", "Smart Home": "M", "Gaming": "M", "Cameras": "M",
    "Home & Kitchen": "L", "Fitness": "L", "Bags & Travel": "L",
}
PER_UNIT_SHIPPING = {"S": 0.25, "M": 0.70, "L": 2.10}
# Base charge per parcel. The faster courier for Greece costs more.
BASE_SHIPPING = {
    "ELTA Courier": 3.20, "SwiftCourier": 4.45,
    ("DHL", "Cyprus"): 8.90, ("DHL", "Germany"): 6.80, ("DHL", "Italy"): 7.20, ("DHL", "France"): 7.30,
    ("DHL", "Netherlands"): 6.50, ("DHL", "Spain"): 7.60, ("DHL", "Bulgaria"): 6.20,
}


def build_products(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    pid = 0
    for cat, (median, spread, weight, names) in CATEGORIES.items():
        n = int(round(30 * weight)) + 6
        for i in range(n):
            pid += 1
            base = names[i % len(names)]
            series = ["", " Pro", " Lite", " Max", " Mini", " Plus", " 2", " X", " Air", " Go"][i // len(names) % 10]
            model = f"{chr(65 + (i * 7) % 26)}{100 + (i * 37) % 900}"
            price = float(np.clip(rng.lognormal(np.log(median), spread), 4, 900))
            price = np.floor(price) + 0.99 if price > 10 else round(price, 2)
            rows.append({
                "product_id": pid,
                "sku": f"SKU-{pid:05d}",
                "product_name": f"{base}{series} {model}",
                "category": cat,
                "list_price": round(price, 2),
                "unit_cost": round(price * rng.uniform(0.42, 0.68), 2),
                "cat_weight": weight,
                "parcel_size": PARCEL_SIZE[cat],
            })
    p = pd.DataFrame(rows)
    n = len(p)

    # Long-tail popularity: a few SKUs sell far more than the rest.
    rank = rng.permutation(n) + 1
    p["popularity"] = (1.0 / rank ** 1.05) * p["cat_weight"] * rng.uniform(0.7, 1.3, n)

    # Lifecycle: most products are steady, some grow, some fade or are
    # discontinued (demand -> 0 while stock is still on the shelf).
    life = rng.choice(["steady", "growing", "declining", "discontinued"], n, p=[0.68, 0.14, 0.12, 0.06])
    p["lifecycle"] = life
    p["launch_day"] = np.where(rng.random(n) < 0.12, rng.integers(60, 600, n), 0)
    p["decline_start"] = rng.integers(150, 520, n)

    # Inventory policy. Some best-sellers are under-protected (stockouts),
    # some slow movers are over-bought (overstock).
    pop_rank = p["popularity"].rank(ascending=False)
    p["lead_time"] = rng.integers(6, 15, n)
    p["safety_factor"] = 2.2
    weak = (pop_rank <= 40) & (rng.random(n) < 0.15)
    p.loc[weak, "safety_factor"] = 0.35
    p["cover_days"] = 35
    heavy = (pop_rank > n * 0.45) & (rng.random(n) < 0.25)
    p.loc[heavy, "cover_days"] = rng.integers(150, 300, heavy.sum())
    p["launch_date"] = pd.Timestamp(config.START_DATE) + pd.to_timedelta(p["launch_day"], unit="D")
    return p


def demand_multiplier(p: pd.DataFrame, day: np.ndarray) -> np.ndarray:
    """products x days matrix of relative demand."""
    d = day[None, :].astype(float)
    life = p["lifecycle"].to_numpy()[:, None]
    start = p["decline_start"].to_numpy()[:, None]
    m = np.ones((len(p), len(day)))
    m = np.where(life == "growing", 0.55 + d / 730 * 1.4, m)
    m = np.where(life == "declining", np.where(d < start, 1.0, np.maximum(0.15, 1 - (d - start) / 260)), m)
    m = np.where(life == "discontinued", np.where(d < start, 1.0, 0.02), m)
    m = np.where(d < p["launch_day"].to_numpy()[:, None], 0.0, m)
    return m


def daily_seasonality(dates: pd.DatetimeIndex) -> np.ndarray:
    day = np.arange(len(dates))
    growth = 1.0 + 0.10 * day / 365                       # underlying acquisition growth
    weekday = np.array([1.05, 1.02, 1.0, 1.0, 0.97, 0.88, 0.95])[dates.day_of_week]
    month = np.array([0.88, 0.85, 0.95, 0.97, 1.0, 0.96, 0.9, 0.82, 1.0, 1.05, 1.22, 1.38])[dates.month - 1]
    bf = np.zeros(len(dates))
    for y in (2024, 2025):
        nov = pd.Timestamp(f"{y}-11-01")
        black_friday = nov + pd.offsets.Week(weekday=4) + pd.offsets.Week(3)
        bf += np.where((dates >= black_friday - pd.Timedelta(days=1)) & (dates <= black_friday + pd.Timedelta(days=3)), 1.6, 0)
    return growth * weekday * month * (1 + bf)


def simulate(scale: float, seed: int):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(config.START_DATE, config.END_DATE, freq="D")
    n_days = len(dates)
    loyalty_day = (pd.Timestamp(config.LOYALTY_LAUNCH) - dates[0]).days
    courier_day = (pd.Timestamp(config.COURIER_SWITCH) - dates[0]).days

    products = build_products(rng)

    # ---- customers: acquisition follows the same growth/seasonality ----------
    season = daily_seasonality(dates)
    n_customers = int(92_000 * scale)
    acq_day = rng.choice(n_days, n_customers, p=season / season.sum())
    acq_day.sort()
    country_names = list(COUNTRIES)
    country_p = np.array([c[0] for c in COUNTRIES.values()])
    customers = pd.DataFrame({
        "customer_id": np.arange(1, n_customers + 1) + 100_000,
        "acq_day": acq_day,
        "country": rng.choice(country_names, n_customers, p=country_p / country_p.sum()),
        "acquisition_channel": rng.choice(CHANNELS, n_customers, p=CHANNEL_P),
    })
    customers["signup_date"] = dates[0] + pd.to_timedelta(np.maximum(acq_day - rng.integers(0, 40, n_customers), 0), unit="D")
    # Marketplace shoppers rarely come back; email subscribers often do.
    loyal_bias = customers["acquisition_channel"].map(
        {"Email": 0.08, "Direct": 0.05, "Organic Search": 0.02, "Paid Search": -0.02, "Social": -0.03, "Marketplace": -0.10}
    ).to_numpy()

    # ---- orders: each customer's purchases are a renewal process -------------
    sla = {c: v[2] for c, v in COUNTRIES.items()}
    deliv_before = {c: v[1][0] for c, v in COUNTRIES.items()}
    deliv_after = {c: v[1][1] for c, v in COUNTRIES.items()}
    o_cust, o_day, o_late, o_deliv, o_ship = [], [], [], [], []
    cust_country = customers["country"].to_numpy()
    for i in range(n_customers):
        day = acq_day[i]
        country = cust_country[i]
        while day < n_days:
            ship = int(rng.choice([0, 1, 1, 2, 2, 3])) + (1 if dates[day].day_of_week >= 5 else 0)
            mean = deliv_after[country] if day >= courier_day else deliv_before[country]
            deliv = max(1, int(round(rng.gamma(4.0, mean / 4.0))))
            late = ship + deliv > sla[country] + 1
            o_cust.append(i); o_day.append(day); o_late.append(late); o_deliv.append(deliv); o_ship.append(ship)
            p_return = 0.40 + loyal_bias[i] + (0.14 if day >= loyalty_day else 0.0) - (0.13 if late else 0.0)
            if rng.random() > p_return:
                break
            day += max(3, int(rng.gamma(1.6, 30)))

    orders = pd.DataFrame({
        "cust_idx": o_cust, "day": o_day, "late": o_late, "delivery_days": o_deliv, "ship_days": o_ship,
    })
    orders = orders.sort_values(["day", "cust_idx"], kind="stable").reset_index(drop=True)
    n_orders = len(orders)
    orders["order_id"] = np.arange(1, n_orders + 1) + 500_000
    orders["customer_id"] = customers["customer_id"].to_numpy()[orders["cust_idx"]]
    orders["country"] = cust_country[orders["cust_idx"]]
    orders["channel"] = customers["acquisition_channel"].to_numpy()[orders["cust_idx"]]
    seconds = rng.choice(np.arange(24), n_orders, p=_hour_profile()) * 3600 + rng.integers(0, 3600, n_orders)
    orders["order_ts"] = dates[orders["day"]] + pd.to_timedelta(seconds, unit="s")
    orders["payment_method"] = rng.choice(PAYMENTS, n_orders, p=PAYMENT_P)

    # Discounts: everyday promo codes, heavier around Black Friday / December.
    month = orders["order_ts"].dt.month.to_numpy()
    promo_p = np.where(month == 11, 0.42, np.where(month == 12, 0.30, 0.16))
    has_promo = rng.random(n_orders) < promo_p
    orders["discount_pct"] = np.where(has_promo, rng.choice([0.10, 0.15, 0.20, 0.25], n_orders, p=[0.45, 0.3, 0.17, 0.08]), 0.0)

    # Status: COD orders get cancelled more; late deliveries get refunded more.
    cancel_p = np.where(orders["payment_method"] == "Cash on Delivery", 0.10, 0.045)
    status = np.where(rng.random(n_orders) < cancel_p, "cancelled", "completed")
    refund_p = np.where(orders["late"], 0.055, 0.026)
    status = np.where((status == "completed") & (rng.random(n_orders) < refund_p), "refunded", status)
    orders["status"] = status
    orders["courier"] = np.where(
        orders["country"] == "Greece",
        np.where(orders["day"] >= courier_day, "SwiftCourier", "ELTA Courier"),
        "DHL",
    )

    # ---- order lines ----------------------------------------------------------
    n_lines = 1 + rng.poisson(1.45, n_orders)
    line_order = np.repeat(np.arange(n_orders), n_lines)
    line_day = orders["day"].to_numpy()[line_order]
    mult = demand_multiplier(products, np.arange(n_days))
    pop = products["popularity"].to_numpy()
    line_product = np.empty(len(line_order), dtype=int)
    month_idx = dates[line_day].year * 12 + dates[line_day].month
    for m in np.unique(month_idx):
        sel = np.where(month_idx == m)[0]
        days_in_month = np.unique(line_day[sel])
        w = pop * mult[:, days_in_month].mean(axis=1)
        line_product[sel] = rng.choice(len(products), len(sel), p=w / w.sum())
    qty = rng.choice([1, 2, 3, 4, 5], len(line_order), p=[0.79, 0.14, 0.045, 0.015, 0.01])
    # Genuine bulk purchases (small businesses): statistical outliers.
    bulk = rng.random(len(line_order)) < 0.0002 * 1.0
    qty = np.where(bulk, rng.integers(40, 160, len(line_order)), qty)

    lines = pd.DataFrame({
        "order_idx": line_order, "day": line_day, "product_idx": line_product, "quantity": qty,
    })
    # Same product twice in one order -> merge into one line.
    lines = lines.groupby(["order_idx", "day", "product_idx"], as_index=False)["quantity"].sum()

    # Prices drift up ~4% in 2025 for half the catalogue.
    list_price = products["list_price"].to_numpy()
    uplift = np.where(rng.random(len(products)) < 0.5, 1.04, 1.0)
    lines["unit_price"] = np.round(
        np.where(lines["day"] >= 366, list_price[lines["product_idx"]] * uplift[lines["product_idx"]], list_price[lines["product_idx"]]), 2
    )

    # ---- inventory: daily replenishment, lost sales when out of stock ---------
    lines, inventory = simulate_inventory(rng, products, orders, lines, n_days, mult)

    # Orders that lost every line never happened.
    kept = lines["order_idx"].unique()
    orders = orders.iloc[np.sort(kept)].copy()
    return products, customers, orders, lines, inventory, dates


def simulate_inventory(rng, products, orders, lines, n_days, mult):
    n_p = len(products)
    pop = products["popularity"].to_numpy()
    # Planners size orders from the catalogue-wide average, not each SKU's
    # current trend: declining and discontinued SKUs end up overstocked.
    cancelled = orders["status"].to_numpy()[lines["order_idx"]] == "cancelled"
    demand = np.zeros((n_p, n_days))
    np.add.at(demand, (lines["product_idx"].to_numpy()[~cancelled], lines["day"].to_numpy()[~cancelled]),
              lines["quantity"].to_numpy()[~cancelled])
    lead = products["lead_time"].to_numpy()
    safety = products["safety_factor"].to_numpy()
    cover = products["cover_days"].to_numpy()

    def plan(d):
        # Planners forecast from the last 8 weeks of demand, refreshed weekly.
        lo = max(0, d - 56)
        window = demand[:, lo:max(d, 56)]
        daily = np.maximum(window.mean(axis=1), 0.05)
        return daily * lead * safety, daily * (lead + cover)

    planned_daily = np.maximum(demand[:, :56].mean(axis=1), 0.05)
    reorder_point, order_up_to = plan(0)

    stock = np.ceil(planned_daily * (30 + rng.integers(0, 20, n_p))).astype(int)
    stock = np.where(products["launch_day"].to_numpy() > 0, 0, stock)
    pipeline = np.zeros((n_p, n_days + 40), dtype=int)
    for i in np.where(products["launch_day"].to_numpy() > 0)[0]:
        pipeline[i, products["launch_day"].iat[i]] += int(np.ceil(planned_daily[i] * 45))

    lines = lines.sample(frac=1.0, random_state=7).sort_values("day", kind="stable").reset_index(drop=True)
    line_cancelled = orders["status"].to_numpy()[lines["order_idx"]] == "cancelled"
    fulfilled = np.ones(len(lines), dtype=bool)
    day_arr = lines["day"].to_numpy()
    prod_arr = lines["product_idx"].to_numpy()
    qty_arr = lines["quantity"].to_numpy()
    bounds = np.searchsorted(day_arr, np.arange(n_days + 1))

    snap_stock = np.zeros((n_p, n_days), dtype=int)
    snap_recv = np.zeros((n_p, n_days), dtype=int)
    snap_sold = np.zeros((n_p, n_days), dtype=int)
    for d in range(n_days):
        if d % 7 == 0 and d >= 56:
            reorder_point, order_up_to = plan(d)
        recv = pipeline[:, d]
        stock += recv
        snap_recv[:, d] = recv
        a, b = bounds[d], bounds[d + 1]
        for j in range(a, b):
            if line_cancelled[j]:
                continue  # cancelled before picking: no stock consumed
            p = prod_arr[j]
            if stock[p] >= qty_arr[j]:
                stock[p] -= qty_arr[j]
                snap_sold[p, d] += qty_arr[j]
            else:
                fulfilled[j] = False    # out of stock: the sale is lost
        on_order = pipeline[:, d + 1:].sum(axis=1)
        need = (stock + on_order <= reorder_point) & (mult[:, min(d + 30, n_days - 1)] > 0.05)
        for p in np.where(need)[0]:
            qty = int(np.ceil(order_up_to[p] - stock[p] - on_order[p]))
            if qty > 0:
                pipeline[p, d + int(lead[p])] += qty
        snap_stock[:, d] = stock

    lines = lines[fulfilled].copy()
    inv = pd.DataFrame({
        "product_idx": np.repeat(np.arange(n_p), n_days),
        "day": np.tile(np.arange(n_days), n_p),
        "stock_on_hand": snap_stock.ravel(),
        "units_received": snap_recv.ravel(),
        "units_sold": snap_sold.ravel(),
    })
    launch = products["launch_day"].to_numpy()[inv["product_idx"]]
    inv = inv[inv["day"] >= launch]
    return lines, inv


def _hour_profile():
    h = np.array([1, 0.6, 0.4, 0.3, 0.3, 0.5, 1.2, 2.2, 3.2, 4.0, 4.4, 4.6,
                  4.8, 4.6, 4.3, 4.2, 4.3, 4.6, 5.0, 5.6, 6.0, 5.4, 4.0, 2.2])
    return h / h.sum()


# ---- export with the defects of a real legacy extract ------------------------

def messy_country(rng, values: np.ndarray, share: float) -> np.ndarray:
    out = values.astype(object).copy()
    pick = rng.random(len(out)) < share
    for i in np.where(pick)[0]:
        out[i] = rng.choice(COUNTRY_VARIANTS[out[i]])
    return out


def format_dates(rng, ts: pd.Series) -> np.ndarray:
    """Different source systems wrote timestamps differently."""
    fmt = rng.choice(4, len(ts), p=[0.66, 0.16, 0.10, 0.08])
    iso = ts.dt.strftime("%Y-%m-%d %H:%M:%S").to_numpy()
    eu = ts.dt.strftime("%d/%m/%Y %H:%M").to_numpy()
    slash = ts.dt.strftime("%Y/%m/%d").to_numpy()
    named = ts.dt.strftime("%d-%b-%Y").to_numpy()
    return np.select([fmt == 0, fmt == 1, fmt == 2], [iso, eu, slash], named)


def export(products, customers, orders, lines, inventory, dates, seed):
    rng = np.random.default_rng(seed + 1)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Products master (the reference data used to repair transactions).
    prod_out = products[["product_id", "sku", "product_name", "category", "list_price", "unit_cost", "launch_date",
                         "lead_time", "parcel_size"]].rename(columns={"lead_time": "supplier_lead_time_days"})
    prod_out.to_csv(config.DATA_DIR / "raw_products.csv", index=False)

    # Customers.
    cust = customers.copy()
    cust["country"] = messy_country(rng, cust["country"].to_numpy(), 0.12)
    cust[["customer_id", "signup_date", "country", "acquisition_channel"]].to_csv(
        config.DATA_DIR / "raw_customers.csv", index=False)

    # Transactions: one row per order line, order attributes repeated.
    t = lines.merge(orders, left_on="order_idx", right_index=True, suffixes=("", "_o"))
    t = t.sort_values(["order_ts", "order_id"]).reset_index(drop=True)
    p = products
    t["product_id"] = p["product_id"].to_numpy()[t["product_idx"]]
    t["sku"] = p["sku"].to_numpy()[t["product_idx"]]
    t["product_name"] = p["product_name"].to_numpy()[t["product_idx"]]
    t["category"] = p["category"].to_numpy()[t["product_idx"]]

    t["ship_date"] = (t["order_ts"].dt.normalize() + pd.to_timedelta(t["ship_days"], unit="D"))
    t["delivery_date"] = t["ship_date"] + pd.to_timedelta(t["delivery_days"], unit="D")
    not_shipped = t["status"] == "cancelled"
    # Refunds: whole order or part of it, spread over its lines.
    refunded = t["status"] == "refunded"
    order_refund_share = pd.Series(rng.choice([1.0, 0.5, 0.3], len(orders), p=[0.6, 0.25, 0.15]), index=orders["order_id"])
    line_net = t["quantity"] * t["unit_price"] * (1 - t["discount_pct"])
    t["refund_amount"] = np.where(refunded, np.round(line_net * order_refund_share.reindex(t["order_id"]).to_numpy(), 2), 0.0)

    t["transaction_id"] = [f"TX{i:08d}" for i in range(1, len(t) + 1)]
    t["shipping_cost"] = shipping_costs(t, products, seed)
    out = pd.DataFrame({
        "transaction_id": t["transaction_id"],
        "order_id": t["order_id"],
        "order_date": format_dates(rng, t["order_ts"]),
        "customer_id": t["customer_id"].astype("Int64"),
        "customer_country": messy_country(rng, t["country"].to_numpy(), 0.12),
        "product_id": t["product_id"],
        "sku": t["sku"],
        "product_name": t["product_name"],
        "category": t["category"],
        "quantity": t["quantity"],
        "unit_price": t["unit_price"],
        "discount_pct": t["discount_pct"],
        "payment_method": t["payment_method"],
        "order_status": t["status"],
        "refund_amount": t["refund_amount"],
        "channel": t["channel"],
        "courier": np.where(not_shipped, None, t["courier"]),
        "ship_date": np.where(not_shipped, None, t["ship_date"].dt.strftime("%Y-%m-%d")),
        "delivery_date": np.where(not_shipped, None, t["delivery_date"].dt.strftime("%Y-%m-%d")),
        "shipping_cost": t["shipping_cost"],
    })
    n = len(out)

    # Status written by different systems.
    status_variants = {"completed": ["Completed", "COMPLETE", "complete"], "cancelled": ["Cancelled", "CANCELED"], "refunded": ["Refunded"]}
    pick = rng.random(n) < 0.07
    out.loc[pick, "order_status"] = [rng.choice(status_variants[s]) for s in out.loc[pick, "order_status"]]

    # Guest checkouts: no customer id on the whole order.
    guest_orders = rng.choice(out["order_id"].unique(), int(out["order_id"].nunique() * 0.016), replace=False)
    out.loc[out["order_id"].isin(guest_orders), "customer_id"] = pd.NA

    # Payment method lost by an old integration.
    null_pay = rng.choice(out["order_id"].unique(), int(out["order_id"].nunique() * 0.0026), replace=False)
    out.loc[out["order_id"].isin(null_pay), "payment_method"] = None

    # Category missing on some lines.
    out.loc[rng.random(n) < 0.0019, "category"] = None

    # Pricing errors: zero, negative, or entered in cents.
    bad_price = rng.choice(n, max(1, int(42 * n / 320_000)), replace=False)
    kinds = rng.choice(3, len(bad_price))
    out.loc[bad_price[kinds == 0], "unit_price"] = 0.0
    out.loc[bad_price[kinds == 1], "unit_price"] = -out.loc[bad_price[kinds == 1], "unit_price"]
    out.loc[bad_price[kinds == 2], "unit_price"] = out.loc[bad_price[kinds == 2], "unit_price"] * 100

    # Legacy return adjustments: a negative-quantity copy of a completed line.
    completed_idx = np.where(out["order_status"].str.lower().str.startswith("complete"))[0]
    neg = out.iloc[rng.choice(completed_idx, max(1, int(127 * n / 320_000)), replace=False)].copy()
    neg["quantity"] = -neg["quantity"]
    neg["transaction_id"] = [f"TXR{i:07d}" for i in range(1, len(neg) + 1)]

    # The integration re-sent some records: exact duplicates.
    dups = out.iloc[rng.choice(n, int(n * 0.0072), replace=False)]
    out = pd.concat([out, neg, dups]).sort_values(["order_id", "transaction_id"], kind="stable").reset_index(drop=True)
    out.to_csv(config.DATA_DIR / "raw_transactions.csv", index=False)

    # Inventory snapshots, with stock-count errors and duplicate uploads.
    inv = inventory.copy()
    inv["snapshot_date"] = dates[inv["day"]].strftime("%Y-%m-%d")
    inv["product_id"] = products["product_id"].to_numpy()[inv["product_idx"]]
    inv = inv[["snapshot_date", "product_id", "stock_on_hand", "units_received", "units_sold"]].reset_index(drop=True)
    neg_stock = rng.random(len(inv)) < 0.0015
    inv.loc[neg_stock, "stock_on_hand"] = -rng.integers(1, 15, neg_stock.sum())
    inv = pd.concat([inv, inv.sample(frac=0.002, random_state=3)]).sort_values(["product_id", "snapshot_date"], kind="stable")
    inv.to_csv(config.DATA_DIR / "raw_inventory.csv", index=False)

    return len(out), len(inv)


def shipping_costs(t: pd.DataFrame, products: pd.DataFrame, seed: int) -> np.ndarray:
    """Carrier cost of each order (repeated on its lines, like other order attributes).

    Uses its own random stream so adding it did not change any other simulated value.
    Cancelled orders were never shipped (no cost); ~0.9% of shipped orders have no
    matched courier invoice in the export (missing cost).
    """
    rng = np.random.default_rng(seed + 2)
    size = products["parcel_size"].to_numpy()[t["product_idx"]]
    t = t.assign(unit_charge=t["quantity"] * pd.Series(size).map(PER_UNIT_SHIPPING).to_numpy())
    o = t.groupby("order_id").agg(courier=("courier", "first"), country=("country", "first"),
                                  status=("status", "first"), units_charge=("unit_charge", "sum"))
    base = [BASE_SHIPPING.get(c, BASE_SHIPPING.get((c, k), 0.0)) for c, k in zip(o["courier"], o["country"])]
    cost = np.minimum(np.array(base) + o["units_charge"].to_numpy(), 65.0)   # pallet rate caps bulk orders
    cost = np.round(cost * rng.uniform(0.95, 1.08, len(o)), 2)
    cost = pd.Series(cost, index=o.index, dtype=object)
    cost[o["status"].to_numpy() == "cancelled"] = None
    missing = (rng.random(len(o)) < 0.009) & (o["status"].to_numpy() != "cancelled")
    cost[missing] = None
    return cost.reindex(t["order_id"]).to_numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0, help="1.0 = ~330k transaction records")
    ap.add_argument("--seed", type=int, default=config.SEED)
    args = ap.parse_args()
    products, customers, orders, lines, inventory, dates = simulate(args.scale, args.seed)
    n_tx, n_inv = export(products, customers, orders, lines, inventory, dates, args.seed)
    print(f"products={len(products)} customers={len(customers)} orders={len(orders)} "
          f"transactions={n_tx} inventory_snapshots={n_inv}")


if __name__ == "__main__":
    main()
