"""Multi-currency arithmetic, the FX staleness rule and consolidated positions, on the micro dataset.

Every expected value is worked out by hand (see tests/micro.py for the setup).
"""

import numpy as np
import pandas as pd
import pytest

from cashpilot.core import money
from cashpilot.engine.fx import FALLBACK, MISSING, NOT_REQUIRED, OK
from cashpilot.engine.positions import daily_cash_positions, entity_cash_positions
from micro import ACTUALS_END, EUR, JPY, RES, USD, micro_dataset, micro_fx

D = pd.Timestamp


# ----------------------------------------------------------------- conversions

def test_conversion_rounds_half_to_even_in_minor_units():
    # 1, 3 and 5 EUR cents at 1.5 USD/EUR are 1.5, 4.5 and 7.5 USD cents: ties go to the even cent
    assert money.to_usd([1, 3, 5], "EUR", [1.5, 1.5, 1.5]).tolist() == [2, 4, 8]


def test_jpy_has_no_minor_units():
    # 100,000 JPY at 0.007 USD/JPY = 700.00 USD = 70,000 cents (not 7,000,000)
    assert money.to_usd([100_000], "JPY", [0.007]).tolist() == [70_000]
    # and 700.00 USD buys back 100,000 yen
    assert money.from_usd([70_000], "JPY", [0.007]).tolist() == [100_000]


def test_inverse_conversion_round_trips():
    usd = money.to_usd([100_000], "EUR", [1.25])  # 1,000.00 EUR -> 1,250.00 USD
    assert usd.tolist() == [125_000]
    assert money.from_usd(usd, "EUR", [1.25]).tolist() == [100_000]


def test_cross_conversion_goes_through_usd_without_intermediate_rounding():
    # 1,000.00 EUR = 1,100.00 USD = 880.00 GBP at 1.25
    assert money.convert([100_000], "EUR", "GBP", [1.10], [1.25]).tolist() == [88_000]
    # 100,000 JPY = 700 USD = 636.3636... EUR -> 636.36 EUR
    assert money.convert([100_000], "JPY", "EUR", [0.007], [1.10]).tolist() == [63_636]


# --------------------------------------------------------------- staleness rule

@pytest.fixture(scope="module")
def micro():
    ds = micro_dataset()
    return ds, micro_fx(ds)


@pytest.mark.parametrize("day, status, rate_id, rate", [
    ("2026-01-02", OK, "FXR-2026-01-02-EUR-USD", 1.10),
    ("2026-01-03", OK, "FXR-2026-01-02-EUR-USD", 1.10),       # Saturday: the Friday fixing is the expected one
    ("2026-01-05", OK, "FXR-2026-01-05-EUR-USD", 1.20),
    ("2026-01-06", FALLBACK, "FXR-2026-01-05-EUR-USD", 1.20),  # 1 expected fixing missing
    ("2026-01-08", FALLBACK, "FXR-2026-01-05-EUR-USD", 1.20),  # 3 missing: still within tolerance
])
def test_fx_lookup_within_tolerance(micro, day, status, rate_id, rate):
    _, fx = micro
    rid, r, st = fx.as_of("EUR", [np.datetime64(day)])
    assert (st[0], rid[0], r[0]) == (status, rate_id, rate)


@pytest.mark.parametrize("day", ["2026-01-09", "2026-01-10", "2026-01-13", "2026-01-01"])
def test_fx_lookup_beyond_tolerance_is_missing_not_zero_and_not_stale(micro, day):
    _, fx = micro
    rid, r, st = fx.as_of("EUR", [np.datetime64(day)])
    assert st[0] == MISSING and rid[0] is None and np.isnan(r[0])  # 4th missing fixing (or none before): no silent rate


def test_reporting_currency_needs_no_rate(micro):
    _, fx = micro
    rid, r, st = fx.as_of("USD", [np.datetime64("2026-01-09")])
    assert (rid[0], r[0], st[0]) == (None, 1.0, NOT_REQUIRED)


def test_run_can_only_use_a_rate_recorded_before_its_cutoff_instant(micro):
    _, fx = micro  # fixings are recorded at 16:00 on their date
    assert fx.known_before("EUR", pd.Timestamp("2026-01-05 10:00"))[0] == "FXR-2026-01-02-EUR-USD"
    assert fx.known_before("EUR", pd.Timestamp("2026-01-05 17:00"))[0] == "FXR-2026-01-05-EUR-USD"
    assert fx.known_before("EUR", pd.Timestamp("2026-01-02 10:00"))[0] is None  # nothing known yet


# ------------------------------------------------------------ daily positions

@pytest.fixture(scope="module")
def positions(micro):
    ds, fx = micro
    daily = daily_cash_positions(ds, ACTUALS_END, fx)
    return ds, fx, daily, entity_cash_positions(ds, daily, fx)


def row(df, account, day):
    return df[(df["account_id"] == account) & (df["position_date"] == D(day))].iloc[0]


def test_account_balances_roll_forward_by_hand(positions):
    _, _, daily, _ = positions
    eur = row(daily, EUR, "2026-01-05")
    # 1,000.00 opening + 500.00 - 200.00 = 1,300.00 EUR
    assert (eur.opening_balance, eur.inflows, eur.outflows, eur.closing_balance) == (100_000, 50_000, 20_000, 130_000)
    assert row(daily, EUR, "2026-01-02").closing_balance == 100_000      # opening balance day, no postings
    assert row(daily, EUR, "2026-01-06").opening_balance == 130_000      # next day starts from the previous close
    assert row(daily, USD, "2026-01-05").closing_balance == 95_000       # 1,000.00 - 50.00
    assert row(daily, JPY, "2026-01-05").closing_balance == 101_000      # 101,000 yen
    assert (daily["bank_minus_book"].dropna() == 0).all()                # statements agree with the ledger


def test_usd_values_use_each_days_rate_and_each_currencys_precision(positions):
    _, _, daily, _ = positions
    assert row(daily, EUR, "2026-01-02").closing_balance_usd == 110_000   # 1,000.00 EUR x 1.10
    assert row(daily, EUR, "2026-01-04").closing_balance_usd == 110_000   # Sunday uses Friday's fixing
    assert row(daily, EUR, "2026-01-05").closing_balance_usd == 156_000   # 1,300.00 EUR x 1.20
    assert row(daily, JPY, "2026-01-05").closing_balance_usd == 70_700    # 101,000 JPY x 0.007 = 707.00 USD
    assert row(daily, USD, "2026-01-05").closing_balance_usd == 95_000
    assert row(daily, EUR, "2026-01-06").fx_status == FALLBACK
    assert row(daily, EUR, "2026-01-06").closing_balance_usd == 156_000   # fallback = previous rate, flagged


def test_missing_rate_leaves_the_usd_value_empty_instead_of_zero(positions):
    _, _, daily, _ = positions
    gap = row(daily, EUR, "2026-01-09")
    assert gap.fx_status == MISSING and pd.isna(gap.closing_balance_usd)
    assert gap.closing_balance == 130_000                                  # the local balance itself is still known


# ----------------------------------------------------------- consolidation

def test_entity_consolidation_by_hand(positions):
    _, _, _, ent = positions
    e = ent.set_index("position_date")
    # 2026-01-02: 1,000.00 + 200.00 (restricted) + 1,100.00 + 700.00 = 3,000.00 USD
    assert (e.at[D("2026-01-02"), "total_usd"], e.at[D("2026-01-02"), "restricted_usd"],
            e.at[D("2026-01-02"), "available_usd"]) == (300_000, 20_000, 280_000)
    # buffer 500.00 USD -> headroom 2,300.00
    assert (e.at[D("2026-01-02"), "min_buffer_usd"], e.at[D("2026-01-02"), "headroom_usd"]) == (50_000, 230_000)
    # 2026-01-05: 950.00 + 200.00 + 1,560.00 + 707.00 = 3,417.00; 3,217.00 available
    assert (e.at[D("2026-01-05"), "total_usd"], e.at[D("2026-01-05"), "available_usd"]) == (341_700, 321_700)
    assert e.at[D("2026-01-06"), "fx_status"] == FALLBACK and e.at[D("2026-01-06"), "total_usd"] == 341_700


def test_a_missing_rate_marks_the_entity_total_incomplete(positions):
    _, _, daily, ent = positions
    e = ent.set_index("position_date")
    # EUR cannot be converted on 2026-01-09: the total holds only what *could* be converted, and says so
    assert e.at[D("2026-01-09"), "fx_status"] == "INCOMPLETE"
    assert e.at[D("2026-01-09"), "total_usd"] == 95_000 + 20_000 + 70_700
    # the flag is exactly "some account has no USD value", in both directions
    missing_days = set(daily.loc[daily["fx_status"] == MISSING, "position_date"])
    assert set(ent.loc[ent["fx_status"] == "INCOMPLETE", "position_date"]) == missing_days


def test_totals_are_sums_of_usd_values_never_of_mixed_local_amounts(positions):
    _, _, daily, ent = positions
    day = daily[daily["position_date"] == D("2026-01-05")]
    mixed_local_sum = int(day["closing_balance"].sum())  # EUR cents + JPY yen + USD cents: meaningless
    total = int(ent.loc[ent["position_date"] == D("2026-01-05"), "total_usd"].iloc[0])
    assert mixed_local_sum == 346_000 and total == 341_700 and total == int(day["closing_balance_usd"].sum())
    assert bool(day.loc[day["account_id"] == RES, "closing_balance_usd"].iloc[0] == 20_000)
