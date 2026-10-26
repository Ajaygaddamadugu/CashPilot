"""Money as integer minor units (cents, paise, yen).

All arithmetic on amounts uses int64 minor units, so reconciliations are exact.
Amounts only become decimal strings at export time.

FX conversion multiplies by a float rate (USD per one unit of currency) and rounds
half-to-even with ``np.rint``. IEEE-754 multiplication is correctly rounded on every
platform, so conversions are deterministic everywhere.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MINOR_UNITS = {"USD": 2, "EUR": 2, "GBP": 2, "INR": 2, "JPY": 0}


def exponent(currency: str) -> int:
    return MINOR_UNITS[currency]


def exponents(currencies) -> np.ndarray:
    if isinstance(currencies, str):
        return np.array([MINOR_UNITS[currencies]], dtype=np.int64)
    return pd.Series(currencies, dtype="object").map(MINOR_UNITS).to_numpy(dtype=np.int64)


def _broadcast_exponents(currencies, n: int) -> np.ndarray:
    exps = exponents(currencies)
    return np.full(n, exps[0], dtype=np.int64) if exps.size == 1 and n != 1 else exps


def major_to_minor(values, currencies) -> np.ndarray:
    """Float major units -> int64 minor units, rounding half-to-even."""
    vals = np.asarray(values, dtype=np.float64)
    exps = _broadcast_exponents(currencies, vals.size)
    return np.rint(vals * np.power(10.0, exps)).astype(np.int64)


def to_usd(minor, currencies, rates) -> np.ndarray:
    """Minor units of ``currencies`` -> USD cents, given USD-per-unit ``rates``."""
    amt = np.asarray(minor, dtype=np.float64)
    exps = _broadcast_exponents(currencies, amt.size)
    return np.rint(amt * np.asarray(rates, dtype=np.float64) * np.power(10.0, 2 - exps)).astype(np.int64)


def from_usd(usd_cents, currencies, rates) -> np.ndarray:
    """USD cents -> minor units of ``currencies``."""
    amt = np.asarray(usd_cents, dtype=np.float64)
    exps = _broadcast_exponents(currencies, amt.size)
    return np.rint(amt / np.asarray(rates, dtype=np.float64) * np.power(10.0, exps - 2)).astype(np.int64)


def convert(minor, from_currencies, to_currencies, from_rates, to_rates) -> np.ndarray:
    """Cross conversion through USD without intermediate rounding."""
    amt = np.asarray(minor, dtype=np.float64)
    e_from = _broadcast_exponents(from_currencies, amt.size)
    e_to = _broadcast_exponents(to_currencies, amt.size)
    usd = amt * np.power(10.0, -e_from) * np.asarray(from_rates, dtype=np.float64)
    return np.rint(usd / np.asarray(to_rates, dtype=np.float64) * np.power(10.0, e_to)).astype(np.int64)


def scale(minor, factor) -> np.ndarray:
    """Multiply minor units by a factor and round half-to-even."""
    return np.rint(np.asarray(minor, dtype=np.float64) * np.asarray(factor, dtype=np.float64)).astype(np.int64)


def format_minor(values, currencies) -> list:
    """Minor units -> fixed-decimal strings (``None`` for missing values). Vectorised."""
    v = pd.array(pd.Series(values, dtype="object").tolist(), dtype="Int64")
    n = len(v)
    if isinstance(currencies, str):
        exps = np.full(n, MINOR_UNITS[currencies], dtype=np.int64)
        known = np.ones(n, dtype=bool)
    else:
        mapped = pd.Series(currencies, dtype="object").map(MINOR_UNITS)
        known = mapped.notna().to_numpy()
        exps = mapped.fillna(-1).to_numpy(dtype=np.int64)
    missing = np.asarray(v.isna()) | ~known
    raw = v.fillna(0).to_numpy(dtype=np.int64)
    neg, mag = raw < 0, np.abs(raw)
    out = np.full(n, None, dtype=object)
    for e in np.unique(exps[~missing]):
        sel = (exps == e) & ~missing
        if e == 0:
            text = mag[sel].astype(str)
        else:
            whole = (mag[sel] // 10**e).astype(str)
            frac = np.char.zfill((mag[sel] % 10**e).astype(str), int(e))
            text = np.char.add(np.char.add(whole, "."), frac)
        out[sel] = np.where(neg[sel], np.char.add("-", text), text)
    return out.tolist()


def parse_major(texts, currencies) -> list:
    """Fixed-decimal strings -> exact minor units (``None`` for blanks)."""
    vals = pd.Series(texts, dtype="object").tolist()
    if isinstance(currencies, str):
        exps = [MINOR_UNITS[currencies]] * len(vals)
    else:
        exps = [MINOR_UNITS.get(c) if isinstance(c, str) else None for c in pd.Series(currencies, dtype="object")]
    out = []
    for s, e in zip(vals, exps):
        if s is None or (isinstance(s, float) and np.isnan(s)) or s == "" or e is None:
            out.append(None)
            continue
        s = str(s).strip()
        neg = s.startswith("-")
        s = s.lstrip("+-")
        whole, _, frac = s.partition(".")
        if len(frac) > e and set(frac[e:]) - {"0"}:
            raise ValueError(f"{s!r} has more than {e} decimal places")
        frac = (frac + "0" * e)[:e]
        v = int(whole or "0") * 10**e + (int(frac) if frac else 0)
        out.append(-v if neg else v)
    return out
