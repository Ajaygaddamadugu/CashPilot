"""Constants and small helpers shared by the generator modules."""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashpilot.core import calendar as cal

# Illustrative FX starting levels (USD per unit), annual volatility and drift.
# Round numbers chosen by the author; no external data is used (docs/PROVENANCE.md).
FX_START = {"USD": 1.0, "EUR": 1.0850, "GBP": 1.2650, "INR": 0.011900, "JPY": 0.006700}
FX_VOL = {"EUR": 0.07, "GBP": 0.08, "INR": 0.04, "JPY": 0.10}
FX_DRIFT = {"EUR": 0.01, "GBP": 0.0, "INR": -0.03, "JPY": 0.02}
FX_SHOCKS = [("GBP", "2026-05-14", -0.04), ("JPY", "2026-08-06", 0.03)]

COUNTRIES = {"USD": ["US"], "EUR": ["DE", "NL", "FR"], "GBP": ["GB"], "INR": ["IN"], "JPY": ["JP"]}
SUFFIX = {"US": "Inc.", "DE": "GmbH", "NL": "B.V.", "FR": "S.A.S.", "GB": "Ltd", "IN": "Pvt Ltd", "JP": "K.K."}
BANKS = {
    "US": ["Kestrel National Bank", "Harborline Bank"],
    "DE": ["Rhinegate Bank AG"], "NL": ["Lowlands Commerce Bank"], "FR": ["Banque Valmorel"],
    "GB": ["Thamesbury Bank plc"], "IN": ["Deccan Federal Bank"], "JP": ["Sakuragawa Trust Bank"],
}

# Monthly external outflows by size tier (USD, median) and minimum liquidity buffers (USD).
TIER_SCALE_USD = {"S": 1.5e6, "M": 6.0e6, "L": 25.0e6}
TIER_BUFFER_USD = {"S": 250_000, "M": 1_000_000, "L": 5_000_000}
HOLDING_SCALE_USD = 3.0e6
HOLDING_BUFFER_USD = 10_000_000

# Share of monthly outflows by type (debt service only for L-tier entities).
OUTFLOW_MIX = {"trade_ap": 0.50, "payroll": 0.20, "rent": 0.04, "tax_quarterly": 0.18, "debt": 0.05, "operating": 0.15}
INFLOW_MULTIPLIER = 1.03          # entities generate slightly more cash than they spend
INFLOW_MIX = {"ar": 0.75, "operating": 0.25}

DEPOSIT_RATES = {"USD": 0.040, "EUR": 0.025, "GBP": 0.042, "INR": 0.060, "JPY": 0.001}

STEMS = [
    "Arden", "Bexley", "Calder", "Dunmore", "Elmstead", "Fairhaven", "Glenrock", "Harlow", "Ivybridge",
    "Juniper", "Kingsmere", "Larkfield", "Marston", "Northgate", "Oakridge", "Pinecrest", "Queensbury",
    "Redwater", "Stonebridge", "Thornbury", "Upton", "Valemont", "Westbury", "Yarrow", "Ashcombe",
    "Brightwell", "Coldstream", "Driftwood", "Eastwick", "Foxley", "Greywell", "Hollins", "Kenmore",
    "Linwood", "Mayfield", "Newbold", "Orwell", "Penrose", "Ravensworth", "Selwyn",
]
SECTORS = ["Logistics", "Components", "Foods", "Systems", "Retail", "Pharma", "Energy", "Textiles", "Analytics", "Engineering"]
CPTY_ADJ = [
    "Amber", "Atlas", "Beacon", "Cedar", "Cobalt", "Crescent", "Delta", "Ember", "Falcon", "Granite",
    "Harbor", "Horizon", "Iris", "Jade", "Keystone", "Lumen", "Maple", "Meridian", "Nova", "Onyx",
    "Orchid", "Pioneer", "Quarry", "Radiant", "Sable", "Summit", "Tidal", "Umber", "Vantage", "Willow", "Zephyr",
]
CPTY_NOUN = [
    "Foods", "Retail", "Motors", "Textiles", "Pharma", "Logistics", "Electronics", "Packaging", "Chemicals",
    "Furniture", "Media", "Health", "Metals", "Agritech", "Software", "Apparel", "Ceramics", "Optics", "Marine", "Power",
]
CPTY_REGION = ["", "Global ", "Pacific ", "Northern ", "Western "]


def day(value) -> np.datetime64:
    return cal.to_day(value)


def stamp(days, seconds) -> np.ndarray:
    """Business day(s) + seconds after midnight -> datetime64[s]."""
    d = np.asarray(days, dtype="datetime64[D]").astype("datetime64[s]")
    return d + np.asarray(seconds, dtype="int64").astype("timedelta64[s]")


def migration_stamp(effective_from) -> np.datetime64:
    """Open items and schedules are loaded at 20:00 UTC on the eve of an entity's start."""
    return stamp(day(effective_from) - np.timedelta64(1, "D"), 20 * 3600)


def to_pd_dates(values) -> pd.Series:
    return pd.to_datetime(pd.Series(np.asarray(values, dtype="datetime64[D]")))


def round_to(values, step: float) -> np.ndarray:
    return np.round(np.asarray(values, dtype=np.float64) / step) * step


def sig3(x: float) -> float:
    return float(f"{x:.3g}")
