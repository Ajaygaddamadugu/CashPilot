"""Explain a forecast-versus-actual difference: totals per driver and the records behind them.

Used by the CLI (`cashpilot explain`) and the dashboard so both show the same numbers.
Amounts are USD cents; callers format them.
"""

from __future__ import annotations

import pandas as pd

from cashpilot.dataset import Dataset

DRIVER_ORDER = ["TIMING", "AMOUNT", "FX", "NEW_AFTER_CUTOFF", "UNFORECASTED", "NOT_REALIZED", "RUN_RATE", "DATA_QUALITY"]


def variance_breakdown(ds: Dataset, run_id: str, entity_id: str, week_no: int, scenario_prefix: str = "SCN-BASE", top: int = 3) -> dict | None:
    """Forecast, actual, variance and per-driver detail for one run, entity and horizon week.

    Returns ``None`` when there is no comparison (for example the week has not elapsed yet).
    ``drivers`` lists, per driver, the total, the number of records and the ``top`` largest
    contributions with the forecast item and ledger posting behind each.
    """
    fva = ds["forecast_vs_actual"]
    row = fva[(fva["run_id"] == run_id) & (fva["entity_id"] == entity_id) & (fva["week_no"] == week_no)
              & fva["scenario_id"].str.startswith(scenario_prefix)]
    if row.empty:
        return None
    r = row.iloc[0]
    va = ds["variance_attribution"]
    va = va[(va["run_id"] == run_id) & (va["entity_id"] == entity_id) & (va["week_no"] == week_no)
            & va["scenario_id"].str.startswith(scenario_prefix)]
    drivers = []
    for driver, g in va.groupby("driver"):
        largest = g.reindex(g["amount_usd"].abs().sort_values(ascending=False, kind="mergesort").index).head(top)
        drivers.append({
            "driver": driver, "total_usd": int(g["amount_usd"].sum()), "records": int(len(g)),
            "top": [{"amount_usd": int(t.amount_usd), "cf_id": t.cf_id if pd.notna(t.cf_id) else None,
                     "ledger_entry_id": t.ledger_entry_id if pd.notna(t.ledger_entry_id) else None} for t in largest.itertuples()],
        })
    drivers.sort(key=lambda d: DRIVER_ORDER.index(d["driver"]) if d["driver"] in DRIVER_ORDER else 99)
    return {
        "run_id": run_id, "scenario_id": r["scenario_id"], "entity_id": entity_id, "week_no": int(week_no),
        "week_start": r["week_start"], "week_end": r["week_end"],
        "forecast_usd": int(r["forecast_net_usd"]), "actual_usd": int(r["actual_net_usd"]), "variance_usd": int(r["variance_usd"]),
        "residual_usd": int(r["residual_usd"]), "drivers": drivers,
    }
