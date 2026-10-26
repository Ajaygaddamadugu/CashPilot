"""FX lookups with an explicit staleness rule.

Rates exist for business days only. For a date ``d`` the expected fixing is the last business
day on or before ``d``. If that fixing is missing, the latest earlier rate may be used as a
fallback while no more than ``tolerance`` expected fixings are missing (rule R-FX-001);
beyond that the conversion is blocked (status MISSING).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashpilot.core import calendar as cal

OK, FALLBACK, MISSING, NOT_REQUIRED = "OK", "FALLBACK", "MISSING", "NOT_REQUIRED"


class FxBook:
    def __init__(self, rates: pd.DataFrame, reporting: str, tolerance: int):
        self.reporting = reporting
        self.tolerance = tolerance
        self.by_ccy = {}
        for ccy, g in rates.groupby("base_currency"):
            g = g.sort_values("rate_date")
            self.by_ccy[ccy] = (
                g["rate_date"].to_numpy(dtype="datetime64[D]"),
                g["rate"].to_numpy(dtype=float),
                g["rate_id"].to_numpy(dtype=object),
                g["recorded_at"].to_numpy(dtype="datetime64[s]"),
            )

    def missing_fixings(self, available, expected) -> np.ndarray:
        """Business days in (available, expected] - fixings that should exist but do not."""
        available = np.asarray(available, dtype="datetime64[D]")
        expected = np.asarray(expected, dtype="datetime64[D]")
        return np.maximum(cal.business_day_count(available + 1, expected + 1), 0)

    def as_of(self, ccy: str, dates) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(rate_id, rate, status) for each date, using the staleness rule."""
        dates = np.asarray(dates, dtype="datetime64[D]")
        n = len(dates)
        if ccy == self.reporting:
            return np.full(n, None, dtype=object), np.ones(n), np.full(n, NOT_REQUIRED, dtype=object)
        rdates, rates, rids, _ = self.by_ccy[ccy]
        i = np.searchsorted(rdates, dates, side="right") - 1
        valid = i >= 0
        idx = np.where(valid, i, 0)
        expected = cal.roll_backward(dates)
        missing = np.where(valid, self.missing_fixings(rdates[idx], expected), 10**6)
        status = np.where(missing == 0, OK, np.where(missing <= self.tolerance, FALLBACK, MISSING)).astype(object)
        rate = np.where(status == MISSING, np.nan, rates[idx])
        rid = np.where(status == MISSING, None, rids[idx]).astype(object)
        return rid, rate, status

    def latest(self, ccy: str, dates) -> tuple[np.ndarray, np.ndarray]:
        """Latest available rate on or before each date, ignoring staleness (for policy amounts)."""
        dates = np.asarray(dates, dtype="datetime64[D]")
        if ccy == self.reporting:
            return np.full(len(dates), None, dtype=object), np.ones(len(dates))
        rdates, rates, rids, _ = self.by_ccy[ccy]
        i = np.maximum(np.searchsorted(rdates, dates, side="right") - 1, 0)
        return rids[i], rates[i]

    def known_before(self, ccy: str, ts) -> tuple[str | None, np.datetime64 | None, float]:
        """Latest rate *recorded* before an instant: what a forecast run could have known."""
        if ccy == self.reporting:
            return None, None, 1.0
        rdates, rates, rids, recorded = self.by_ccy[ccy]
        ok = np.nonzero(recorded < np.datetime64(ts, "s"))[0]
        if not len(ok):
            return None, None, float("nan")
        j = ok[np.argmax(rdates[ok])]
        return str(rids[j]), rdates[j], float(rates[j])
