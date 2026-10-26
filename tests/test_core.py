from datetime import date

import numpy as np

from cashpilot.core import calendar as cal
from cashpilot.core import ids, money
from cashpilot.core.rng import stream


def test_rounding_is_half_to_even_in_minor_units():
    assert money.major_to_minor([0.125, 0.375], "USD").tolist() == [12, 38]
    assert money.major_to_minor([2.5, 3.5], "JPY").tolist() == [2, 4]


def test_format_and_parse_round_trip_respects_currency_decimals():
    assert money.format_minor([-12345, 0, 7], "USD") == ["-123.45", "0.00", "0.07"]
    assert money.format_minor([1500], "JPY") == ["1500"]
    assert money.parse_major(["-123.45", "0.07", "12"], "USD") == [-12345, 7, 1200]
    assert money.parse_major(["1500", None], ["JPY", "JPY"]) == [1500, None]


def test_usd_conversion_uses_currency_exponents():
    # 100,000 JPY at 0.0067 USD/JPY = 670.00 USD
    assert money.to_usd([100_000], "JPY", [0.0067]).tolist() == [67_000]
    # 1,000.00 EUR at 1.085 USD/EUR = 1,085.00 USD; and back again
    assert money.to_usd([100_000], "EUR", [1.085]).tolist() == [108_500]
    assert money.from_usd([108_500], "EUR", [1.085]).tolist() == [100_000]


def test_business_calendar():
    assert not cal.is_business_day(date(2026, 1, 1))  # holiday
    assert cal.is_business_day(date(2026, 1, 2))
    assert cal.roll_forward(np.datetime64("2026-01-03")) == np.datetime64("2026-01-05")
    assert cal.add_business_days(np.datetime64("2026-01-05"), -1) == np.datetime64("2026-01-02")
    days = cal.business_days(date(2026, 1, 1), date(2026, 1, 9))
    assert [str(d) for d in days] == ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]


def test_id_conventions_from_the_brief():
    assert ids.entity_id(1) == "ENT-000001"
    assert ids.account_id("ENT-000001", 1) == "BANKACC-ENT-000001-001"
    assert ids.sequence("LED", 2026, 8, 2) == ["LED-2026-00000001", "LED-2026-00000002"]
    assert ids.sequence("CF", 2026, 6, 1) == ["CF-2026-000001"]
    assert ids.run_id(date(2026, 1, 1), 1) == "FCAST-2026-01-01-001"


def test_named_random_streams_are_reproducible_and_independent():
    a1 = stream(20261022, "fx").integers(0, 10**9, 5)
    a2 = stream(20261022, "fx").integers(0, 10**9, 5)
    b = stream(20261022, "ledger").integers(0, 10**9, 5)
    assert a1.tolist() == a2.tolist()
    assert a1.tolist() != b.tolist()
