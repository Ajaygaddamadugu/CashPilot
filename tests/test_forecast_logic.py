"""Receipt/payment timing, scenario assumptions, buffers and FX shocks on a hand-sized forecast.

Setup (all USD cents; run cutoff Monday 2026-03-02, horizon 7 days unless stated):

    opening available cash   10,000.00        restricted cash 500.00 (never available)
    minimum buffer           11,000.00
    AR tier A  Mar 3  +1,000.00      AR tier C  Mar 4  +2,000.00
    AP         Mar 5  -3,000.00      AR tier D  Mar 6  +4,000.00

    daily closing available = 10,000 | 11,000 | 13,000 | 10,000 | 14,000 | 14,000 | 14,000
    below buffer (strictly)   yes      no       no       yes      no       no       no
"""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from cashpilot.engine.forecast import Projector, apply_assumption

E = "ENT-000001"
CUTOFF = pd.Timestamp("2026-03-02")


def make_ctx(horizon=7, extra_accounts=()):
    accounts = [("A-OP", False, "USD"), ("A-RES", True, "USD"), *extra_accounts]
    return SimpleNamespace(
        horizon=horizon,
        accounts=pd.DataFrame({"is_restricted": [a[1] for a in accounts], "entity_id": E}, index=[a[0] for a in accounts]),
        entities=pd.DataFrame({"min_liquidity_buffer": [1_100_000], "functional_currency": ["USD"]}, index=[E]),
    )


def balances(*rows):
    return pd.DataFrame(rows, columns=["account_id", "currency", "balance_used"])


BASE_BALANCES = balances(("A-OP", "USD", 1_000_000), ("A-RES", "USD", 50_000))


def item(cf, date, direction, amount, category, tier=None, ccy="USD", treatment="INCLUDED"):
    return {"cf_id": cf, "entity_id": E, "direction": direction, "flow_category": category, "risk_tier": tier,
            "treatment": treatment, "date": pd.Timestamp(date) if date else pd.NaT, "currency_used": ccy, "amount_used": amount}


def standard_items():
    return pd.DataFrame([
        item("i-A", "2026-03-03", "INFLOW", 100_000, "AR_COLLECTION", "A"),
        item("i-C", "2026-03-04", "INFLOW", 200_000, "AR_COLLECTION", "C"),
        item("i-AP", "2026-03-05", "OUTFLOW", 300_000, "AP_PAYMENT"),
        item("i-D", "2026-03-06", "INFLOW", 400_000, "AR_COLLECTION", "D"),
    ])


def project(items, ctx=None, rates=None, mult=None, bal=None):
    ctx = ctx or make_ctx()
    p = Projector(ctx, CUTOFF, BASE_BALANCES if bal is None else bal, rates or {"USD": 1.0}, [E])
    return p.arrays(items, mult or {c: 1.0 for c in (rates or {"USD": 1.0})}), p


def asm(parameter, value, field=None, filter_value=None):
    return {"parameter": parameter, "value": str(value), "filter_field": field, "filter_value": filter_value}


# ------------------------------------------------------------------- base case

def test_base_projection_by_hand():
    (inflow, outflow, closing, restricted, buffer), p = project(standard_items())
    assert inflow[0].tolist() == [0, 100_000, 200_000, 0, 400_000, 0, 0]
    assert outflow[0].tolist() == [0, 0, 0, 300_000, 0, 0, 0]
    assert closing[0].tolist() == [1_000_000, 1_100_000, 1_300_000, 1_000_000, 1_400_000, 1_400_000, 1_400_000]
    assert (restricted[0], buffer[0]) == (50_000, 1_100_000)
    frame = p.frame((inflow, outflow, closing, restricted, buffer))
    assert frame["breach_flag"].tolist() == [True, False, False, True, False, False, False]  # equal to the buffer is not a breach
    assert frame["opening_available_usd"].tolist()[:3] == [1_000_000, 1_000_000, 1_100_000]


def test_excluded_items_never_reach_the_projection():
    items = pd.concat([standard_items(), pd.DataFrame([
        item("dup", "2026-03-03", "INFLOW", 123_456, "OTHER", treatment="EXCLUDED_DUPLICATE"),
        item("stale", None, "INFLOW", 0, "OTHER", treatment="EXCLUDED_STALE"),
        item("quarantined", "2026-03-04", "OUTFLOW", 999_999, "OTHER", treatment="QUARANTINED")])], ignore_index=True)
    (_, _, closing, _, _), _ = project(items)
    assert closing[0].tolist() == [1_000_000, 1_100_000, 1_300_000, 1_000_000, 1_400_000, 1_400_000, 1_400_000]


# ----------------------------------------------------------------- delayed receipts

def test_a_delayed_receipt_moves_to_its_new_date_and_the_cash_is_not_lost():
    ctx = make_ctx(horizon=30)
    items = standard_items()
    changed = apply_assumption(items, {"USD": 1.0}, asm("AR_DELAY_DAYS", 21, "risk_tier", "C"), CUTOFF)
    assert changed == 1
    assert items.loc[items["cf_id"] == "i-C", "date"].iloc[0] == pd.Timestamp("2026-03-25")
    (inflow, _, closing, _, _), _ = project(items, ctx)
    assert inflow[0][2] == 0 and inflow[0][23] == 200_000      # gone from Mar 4, back on Mar 25 (day 23)
    delayed_base, _ = project(standard_items(), ctx)
    assert closing[0][22] == delayed_base[2][0][22] - 200_000   # the shortfall in between
    assert closing[0][23] == delayed_base[2][0][23]             # fully caught up once it arrives


def test_a_receipt_delayed_beyond_the_horizon_leaves_the_window_but_stays_a_receivable():
    items = standard_items()
    assert apply_assumption(items, {"USD": 1.0}, asm("AR_DELAY_DAYS", 21, "risk_tier", "C"), CUTOFF) == 1
    assert apply_assumption(items, {"USD": 1.0}, asm("AR_DELAY_DAYS", 45, "risk_tier", "D"), CUTOFF) == 1
    assert apply_assumption(items, {"USD": 1.0}, asm("AR_DELAY_DAYS", 0, "risk_tier", "A"), CUTOFF) == 0
    assert len(items) == 4 and (items["treatment"] == "INCLUDED").all()      # nothing deleted from the item list
    (_, _, closing, _, _), p = project(items)
    assert closing[0].tolist() == [1_000_000, 1_100_000, 1_100_000, 800_000, 800_000, 800_000, 800_000]
    assert p.frame(project(items)[0])["breach_flag"].tolist() == [True, False, False, True, True, True, True]


def test_collection_haircut_scales_the_amount_half_to_even():
    items = pd.concat([standard_items(), pd.DataFrame([item("tiny", "2026-03-03", "INFLOW", 5, "AR_COLLECTION", "C")])], ignore_index=True)
    n = apply_assumption(items, {"USD": 1.0}, asm("AR_COLLECTION_RATE", 0.9, "risk_tier", "C"), CUTOFF)
    amounts = items.set_index("cf_id")["amount_used"]
    assert n == 2 and amounts["i-C"] == 180_000 and amounts["tiny"] == 4   # 4.5 cents -> 4 (even)
    assert amounts["i-D"] == 400_000                                       # other tiers untouched


# ---------------------------------------------------------------- supplier payments

def test_earlier_supplier_payment_is_shifted_but_never_before_the_cutoff():
    items = standard_items()
    assert apply_assumption(items, {"USD": 1.0}, asm("AP_TIMING_SHIFT_DAYS", -5), CUTOFF) == 1
    assert items.loc[items["cf_id"] == "i-AP", "date"].iloc[0] == CUTOFF          # Mar 5 - 5 days = Feb 28, clipped to Mar 2
    (_, outflow, closing, _, _), _ = project(items)
    assert outflow[0][0] == 300_000 and closing[0][0] == 700_000


def test_supplier_payment_reduces_cash_on_its_expected_date_only():
    (_, outflow, closing, _, _), _ = project(standard_items())
    assert outflow[0].nonzero()[0].tolist() == [3]            # Mar 5 is day 3
    assert closing[0][3] == closing[0][2] - 300_000


# ----------------------------------------------------------------------- FX

def test_fx_shock_changes_usd_value_of_foreign_items_and_balances_but_not_usd():
    ctx = make_ctx(extra_accounts=[("A-EUR", False, "EUR")])
    bal = balances(("A-OP", "USD", 1_000_000), ("A-RES", "USD", 50_000), ("A-EUR", "EUR", 100_000))
    items = pd.DataFrame([item("eur-in", "2026-03-03", "INFLOW", 200_000, "AR_COLLECTION", "A", ccy="EUR")])
    rates = {"USD": 1.0, "EUR": 1.10}
    (inflow, _, closing, _, _), _ = project(items, ctx, rates, {"USD": 1.0, "EUR": 1.0}, bal)
    assert inflow[0][1] == 220_000                    # 2,000.00 EUR x 1.10
    assert closing[0][0] == 1_000_000 + 110_000       # opening: 10,000.00 USD + 1,000.00 EUR x 1.10
    mult = {"USD": 1.0, "EUR": 1.0}
    assert apply_assumption(items, mult, asm("FX_SHOCK_PCT", -10, "currency_not", "USD"), CUTOFF) == 1
    assert mult == {"USD": 1.0, "EUR": pytest.approx(0.9)}
    (inflow, _, closing, _, _), _ = project(items, ctx, rates, mult, bal)
    assert inflow[0][1] == 198_000                    # 2,000.00 EUR x 1.10 x 0.90
    assert closing[0][0] == 1_000_000 + 99_000        # the EUR balance loses 10% of its USD value too


def test_restricted_cash_is_reported_but_excluded_from_available_cash():
    (_, _, closing, restricted, _), _ = project(standard_items())
    assert closing[0][0] == 1_000_000 and restricted[0] == 50_000
    only_restricted = balances(("A-RES", "USD", 50_000))
    (_, _, closing, restricted, _), _ = project(pd.DataFrame([item("i", "2026-03-03", "INFLOW", 10, "OTHER")]), bal=only_restricted)
    assert closing[0][0] == 0 and restricted[0] == 50_000
