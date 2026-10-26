"""Deterministic identifiers.

Required conventions from the brief:
    ENT-000001, BANKACC-<entity-id>-001, LED-2026-00000001, CF-2026-000001,
    FCAST-2026-01-01-001
The remaining tables follow the same pattern: a type prefix, the cycle year and a
zero-padded counter. Counters are assigned once, in a documented sort order, and
never re-used or re-assigned.
"""

from __future__ import annotations

from cashpilot.core.calendar import as_date


def entity_id(n: int) -> str:
    return f"ENT-{n:06d}"


def account_id(entity: str, n: int) -> str:
    return f"BANKACC-{entity}-{n:03d}"


def run_id(cutoff, version: int) -> str:
    return f"FCAST-{as_date(cutoff):%Y-%m-%d}-{version:03d}"


def rate_id(day, base: str, quote: str = "USD") -> str:
    return f"FXR-{as_date(day):%Y-%m-%d}-{base}-{quote}"


def scenario_id(code: str, version: int) -> str:
    return f"SCN-{code}-V{version:02d}"


def simple(prefix: str, n: int, width: int) -> str:
    return f"{prefix}-{n:0{width}d}"


def sequence(prefix: str, year: int, width: int, count: int, start: int = 1) -> list[str]:
    """``count`` consecutive IDs like ``LED-2026-00000001``."""
    return [f"{prefix}-{year}-{i:0{width}d}" for i in range(start, start + count)]


def simple_sequence(prefix: str, width: int, count: int, start: int = 1) -> list[str]:
    """``count`` consecutive IDs like ``CPTY-000001`` (no year)."""
    return [f"{prefix}-{i:0{width}d}" for i in range(start, start + count)]


# Widths used per table (prefix -> counter width); documented in docs/ID_CONVENTIONS.md.
WIDTHS = {
    "LED": 8, "CF": 6, "AR": 6, "AP": 6, "CFR": 7, "SETL": 7, "STM": 7,
    "ARE": 7, "APE": 7, "BAE": 6, "FRE": 6, "EXC": 6, "EXE": 6, "AUD": 6, "TRF": 6,
}
