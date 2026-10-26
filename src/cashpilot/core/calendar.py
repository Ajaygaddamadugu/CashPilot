"""Business-day calendar shared by the generator and the engine.

Business days are Monday to Friday minus a small set of global holidays.
Bank postings, bank statements and FX fixings only happen on business days.
All helpers accept scalars or arrays and return numpy ``datetime64[D]`` values.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

HOLIDAYS = ("2025-12-25", "2026-01-01", "2026-12-25", "2027-01-01")
_HOLIDAYS = np.array(HOLIDAYS, dtype="datetime64[D]")
ONE_DAY = np.timedelta64(1, "D")


def to_day(value) -> np.datetime64:
    """Any date-like scalar -> numpy day."""
    return np.datetime64(pd.Timestamp(value).date(), "D")


def as_date(value) -> date:
    return pd.Timestamp(value).date()


def days_array(values) -> np.ndarray:
    """Date-like array/Series -> datetime64[D] array."""
    if isinstance(values, (pd.Series, pd.Index)):
        return values.to_numpy(dtype="datetime64[D]")
    return np.asarray(values, dtype="datetime64[D]")


def is_business_day(values):
    return np.is_busday(days_array(values), holidays=_HOLIDAYS)


def business_days(start, end) -> np.ndarray:
    """Business days in [start, end]."""
    days = np.arange(to_day(start), to_day(end) + ONE_DAY, dtype="datetime64[D]")
    return days[np.is_busday(days, holidays=_HOLIDAYS)]


def calendar_days(start, end) -> np.ndarray:
    """Every calendar day in [start, end]."""
    return np.arange(to_day(start), to_day(end) + ONE_DAY, dtype="datetime64[D]")


def roll_forward(values):
    """Same day if it is a business day, else the next business day."""
    return np.busday_offset(days_array(values), 0, roll="forward", holidays=_HOLIDAYS)


def roll_backward(values):
    """Same day if it is a business day, else the previous business day."""
    return np.busday_offset(days_array(values), 0, roll="backward", holidays=_HOLIDAYS)


def add_business_days(values, n):
    """Shift by ``n`` business days; ``n=-1`` gives the last business day strictly before."""
    return np.busday_offset(days_array(values), n, roll="forward", holidays=_HOLIDAYS)


def business_day_count(start, end):
    """Number of business days in [start, end)."""
    return np.busday_count(days_array(start), days_array(end), holidays=_HOLIDAYS)


def month_starts(start, end) -> list[np.datetime64]:
    """First calendar day of every month that intersects [start, end]."""
    first = pd.Timestamp(start).to_period("M")
    last = pd.Timestamp(end).to_period("M")
    return [np.datetime64(p.start_time.date(), "D") for p in pd.period_range(first, last, freq="M")]


def first_business_days_of_months(start, end) -> np.ndarray:
    out = [roll_forward(m) for m in month_starts(start, end)]
    days = np.array(out, dtype="datetime64[D]")
    return days[(days >= to_day(start)) & (days <= to_day(end))]


def last_business_days_of_months(start, end) -> np.ndarray:
    out = []
    for m in month_starts(start, end):
        month_end = np.datetime64(pd.Timestamp(m).to_period("M").end_time.date(), "D")
        out.append(roll_backward(month_end))
    days = np.array(out, dtype="datetime64[D]")
    return days[(days >= to_day(start)) & (days <= to_day(end))]
