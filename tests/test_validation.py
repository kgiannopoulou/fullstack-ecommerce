"""Unit tests for the data-quality rules and the analytical helpers.

No database needed: every rule is a function of DataFrames, so it can be
tested on a handful of hand-made rows where the right answer is obvious.

    pytest tests/test_validation.py
"""
import numpy as np
import pandas as pd
import pytest

import anomaly_detection as ad
import forecast as fc
import validate as v


# --------------------------------------------------------------- fixtures --
def raw_data(**overrides) -> dict[str, pd.DataFrame]:
    tx = pd.DataFrame({
        "transaction_id": ["T1", "T2", "T3"],
        "order_id": ["1", "1", "2"],
        "order_date": ["2025-01-05 10:00:00"] * 3,
        "customer_id": ["100", "100", "101"],
        "customer_country": ["Greece"] * 3,
        "product_id": ["1", "2", "1"],
        "category": ["Audio", "Office", "Audio"],
        "quantity": ["1", "2", "1"],
        "unit_price": ["10.00", "5.00", "10.00"],
        "payment_method": ["Card"] * 3,
        "order_status": ["completed", "completed", "cancelled"],
        "shipping_cost": ["4.10", "4.10", None],          # cancelled: never shipped, no cost
    })
    data = {
        "transactions": tx,
        "products": pd.DataFrame({"product_id": ["1", "2"], "list_price": ["10.00", "5.00"]}),
        "customers": pd.DataFrame({"customer_id": ["100", "101"], "country": ["Greece", "Cyprus"]}),
        "inventory": pd.DataFrame({"product_id": ["1", "2"], "snapshot_date": ["2025-01-05"] * 2,
                                   "stock_on_hand": ["5", "0"]}),
    }
    for table, fn in overrides.items():
        data[table] = fn(data[table].copy())
    return data


def rule(rule_id: str, rules=None) -> v.Rule:
    return next(r for r in (rules or v.raw_rules()) if r.rule_id == rule_id)


def failures(rule_id: str, data, rules=None) -> int:
    return int(rule(rule_id, rules).fails(data).fillna(True).sum())


# ------------------------------------------------------------- raw rules --
def test_clean_fixture_passes_every_raw_rule():
    results = v.run_rules("raw", v.raw_rules(), raw_data())
    assert [r.rule.rule_id for r in results if r.failures] == []


def test_duplicate_transaction_is_caught_once():
    data = raw_data(transactions=lambda t: pd.concat([t, t.iloc[[0]]]))
    assert failures("R01", data) == 1        # the copy fails, the original does not


def test_price_entered_in_cents_is_invalid():
    data = raw_data(transactions=lambda t: t.assign(unit_price=["1000.00", "5.00", "10.00"]))
    assert failures("R07", data) == 1


def test_zero_and_negative_prices_are_invalid():
    data = raw_data(transactions=lambda t: t.assign(unit_price=["0", "-5.00", "10.00"]))
    assert failures("R07", data) == 2


def test_negative_quantity_is_invalid():
    data = raw_data(transactions=lambda t: t.assign(quantity=["1", "-2", "1"]))
    assert failures("R06", data) == 1


def test_non_iso_dates_are_flagged_but_iso_passes():
    data = raw_data(transactions=lambda t: t.assign(order_date=["2025-01-05 10:00:00", "05/01/2025 10:00", "05-Jan-2025"]))
    assert failures("R08", data) == 2


def test_country_variants_are_flagged():
    data = raw_data(transactions=lambda t: t.assign(customer_country=["Greece", "GR", "Ελλάδα"]))
    assert failures("R09", data) == 2


def test_missing_shipping_cost_only_counts_for_shipped_orders():
    data = raw_data(transactions=lambda t: t.assign(shipping_cost=[None, "4.10", None]))
    assert failures("R05", data) == 1        # line 3 is cancelled, so its missing cost is fine


def test_guest_checkouts_pass_below_the_tolerated_rate():
    data = raw_data(transactions=lambda t: t.assign(customer_id=[None, "100", "101"]))
    result = v.run_rules("raw", [rule("R02")], data)[0]
    assert result.failures == 1
    assert not result.passed                 # 1 of 3 = 33% > 3% tolerated
    assert result.rule.critical is False     # ... but only a warning


def test_negative_stock_is_invalid():
    data = raw_data(inventory=lambda i: i.assign(stock_on_hand=["5", "-3"]))
    assert failures("R12", data) == 1


# ----------------------------------------------------------- clean rules --
def clean_data(**overrides):
    data = {
        "products": pd.DataFrame({"product_id": [1, 2]}),
        "orders": pd.DataFrame({
            "order_id": [1, 2], "customer_id": [100, None], "payment_method": ["Card", "PayPal"],
            "status": ["completed", "cancelled"], "country": ["Greece", "Cyprus"],
            "shipping_cost": [4.1, 0.0], "refund_amount": [0.0, 0.0],
            "order_date": ["2025-01-05", "2025-01-06"], "delivery_date": ["2025-01-08", None],
        }),
        "order_items": pd.DataFrame({
            "transaction_id": ["T1", "T2"], "order_id": [1, 2], "product_id": [1, 2], "quantity": [1, 2],
            "unit_price": [10.0, 5.0], "gross_amount": [10.0, 10.0], "discount_amount": [1.0, 0.0],
            "net_amount": [9.0, 10.0],
        }),
        "inventory_daily": pd.DataFrame({"product_id": [1], "stock_on_hand": [3]}),
    }
    for table, fn in overrides.items():
        data[table] = fn(data[table].copy())
    return data


def test_clean_fixture_passes_every_critical_rule():
    results = v.run_rules("clean", v.clean_rules(), clean_data())
    assert [r.rule.rule_id for r in results if r.rule.critical and not r.passed] == []


def test_orphan_line_breaks_the_gate():
    data = clean_data(order_items=lambda i: i.assign(product_id=[1, 99]))
    results = v.run_rules("clean", v.clean_rules(), data)
    failed = {r.rule.rule_id for r in results if not r.passed and r.rule.critical}
    assert failed == {"C11"}


def test_net_amount_must_equal_gross_minus_discount():
    data = clean_data(order_items=lambda i: i.assign(net_amount=[10.0, 10.0]))
    assert failures("C15", data, v.clean_rules()) == 1


def test_refund_on_a_non_refunded_order_is_inconsistent():
    data = clean_data(orders=lambda o: o.assign(refund_amount=[5.0, 0.0]))
    assert failures("C14", data, v.clean_rules()) == 1


def test_scorecard_counts_failed_checks_and_completeness():
    data = raw_data(transactions=lambda t: t.assign(category=[None, "Office", "Audio"], unit_price=["0", "5.00", "10.00"]))
    results = v.run_rules("raw", v.raw_rules(), data)
    card = v.scorecard("raw", results, data)
    assert card["failed_checks"] == 2                         # R03 category, R07 price
    assert card["completeness_pct"] == pytest.approx(100 * 2 / 3, abs=0.01)
    assert card["validity_pct"] == pytest.approx(100 * 2 / 3, abs=0.01)
    assert card["duplicates_pct"] == 0


# ---------------------------------------------------- anomaly detection --
def test_same_weekday_zscore_flags_a_drop():
    days = pd.date_range("2025-01-01", periods=70, freq="D")
    rng = np.random.default_rng(0)
    s = pd.Series(1000 + rng.normal(0, 30, len(days)), index=days)
    s.iloc[-1] = 200                                         # an obvious collapse
    out = ad.same_weekday_zscores(s)
    assert out["z"].iloc[-1] < -ad.Z
    assert out["gap_pct"].iloc[-1] == pytest.approx(-80, abs=5)
    assert (out["z"].iloc[:-1].abs() < ad.Z).all()           # no false alarms on normal days


def test_zscore_needs_a_full_baseline():
    days = pd.date_range("2025-01-01", periods=30, freq="D")
    out = ad.same_weekday_zscores(pd.Series(100.0, index=days))
    assert out.empty                                          # < 8 weeks of history: no verdict


def test_black_friday_is_a_known_event():
    assert ad.calendar_event(pd.Timestamp("2025-11-28")) == "Black Friday weekend"
    assert ad.calendar_event(pd.Timestamp("2025-06-10")) == ""


# -------------------------------------------------------------- forecast --
def toy_inventory(stockout_days: int = 0) -> pd.DataFrame:
    """One product selling 10/day for a year; optionally sold out for the last N days."""
    days = pd.date_range("2024-01-01", "2025-12-31", freq="D")
    sold = np.full(len(days), 10)
    stock = np.full(len(days), 200)
    if stockout_days:
        sold[-stockout_days:] = 0
        stock[-stockout_days:] = 0
    return pd.DataFrame({"snapshot_date": days, "product_id": 1, "category": "Audio",
                         "units_sold": sold, "stock_on_hand": stock})


def test_forecast_of_flat_demand_is_flat():
    f = fc.forecast(toy_inventory(), pd.Timestamp("2025-12-31"))
    assert f.loc[1, "forecast"] == pytest.approx(300, rel=0.01)


def test_sold_out_days_do_not_drag_the_forecast_down():
    f = fc.forecast(toy_inventory(stockout_days=20), pd.Timestamp("2025-12-31"))
    assert f.loc[1, "forecast"] == pytest.approx(300, rel=0.01)   # demand was still 10/day
