"""Dataset-level detectors. Every finding names its rule, severity and decision.

Detectors read only dataset tables - never the ground truth.

  R-RECON-001  statement movement differs from the booked ledger movement (account-day)
  R-FX-001     an expected business-day FX fixing is missing (decision by staleness)
  R-DUP-001/2  a manual forecast item repeats a subledger item
  R-CUR-001/2  a forecast item mixes currencies without conversion
  R-LEAK-001   a forecast run used records recorded after its knowledge cutoff
  R-LIQ-001    business alert: projected available cash below the entity buffer (live run)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashpilot.core import calendar as cal
from cashpilot.core import ids
from cashpilot.core.config import Config
from cashpilot.core.money import format_minor, to_usd
from cashpilot.dataset import Dataset
from cashpilot.engine.fx import FxBook
from cashpilot.quality.rules import duplicate_pairs, mixed_currency

COLUMNS = ["rule_id", "category", "exception_type", "severity", "record_table", "record_id", "related_record_id",
           "entity_id", "account_id", "run_id", "impact_usd", "decision", "details"]


def _usd(fx: FxBook, amounts, ccy: str, dates) -> np.ndarray:
    _, rate = fx.latest(ccy, np.asarray(dates, dtype="datetime64[D]"))
    return to_usd(np.asarray(amounts, dtype=np.int64), ccy, rate)


def reconciliation_breaks(ds: Dataset, cfg: Config, fx: FxBook) -> pd.DataFrame:
    st = ds["bank_statement"]
    booked = ds["ledger_entry"].groupby(["account_id", "posting_date"])["amount"].sum().rename("booked")
    s = st.join(booked, on=["account_id", "statement_date"]).fillna({"booked": 0})
    s["diff"] = (s["closing_balance"] - s["opening_balance"]).astype(np.int64) - s["booked"].astype(np.int64)
    s = s[s["diff"] != 0]
    if s.empty:
        return pd.DataFrame(columns=COLUMNS)
    acc = ds["bank_account"].set_index("account_id")
    rows = []
    for ccy, g in s.groupby("currency"):
        usd = np.abs(_usd(fx, g["diff"], ccy, g["statement_date"]))
        for (_, r), u in zip(g.iterrows(), usd):
            high = u >= cfg.policy["recon_materiality_usd"] * 100
            rows.append({"rule_id": "R-RECON-001", "category": "DATA_QUALITY", "exception_type": "BALANCE_BREAK",
                         "severity": "HIGH" if high else "LOW", "record_table": "bank_statement", "record_id": r.statement_id,
                         "entity_id": acc.at[r.account_id, "entity_id"], "account_id": r.account_id, "impact_usd": int(u),
                         "decision": "RAISE_RECON_BREAK",
                         "details": (f"Bank movement {format_minor([r.closing_balance - r.opening_balance], ccy)[0]} vs booked "
                                     f"{format_minor([int(r.booked)], ccy)[0]} {ccy} on {r.statement_date:%Y-%m-%d}: "
                                     f"difference {format_minor([int(r['diff'])], ccy)[0]}")})
    return pd.DataFrame(rows, columns=COLUMNS)


def missing_fx_rates(ds: Dataset, cfg: Config) -> pd.DataFrame:
    tol = cfg.policy["fx_staleness_business_days"]
    rows = []
    for ccy, g in ds["currency_rate"].groupby("base_currency"):
        have = g["rate_date"].to_numpy(dtype="datetime64[D]")
        expected = cal.business_days(have.min(), have.max())
        missing = np.setdiff1d(expected, have)
        for d in missing:
            prior = have[have < d].max()
            stale = int(cal.business_day_count(prior + 1, d + 1))
            block = stale > tol
            rows.append({"rule_id": "R-FX-001", "category": "DATA_QUALITY", "exception_type": "FX_RATE_MISSING",
                         "severity": "HIGH" if block else "MEDIUM", "record_table": "currency_rate",
                         "record_id": ids.rate_id(d, ccy), "decision": "BLOCK_CONVERSION" if block else "USE_PREVIOUS_RATE",
                         "details": f"No {ccy}/USD fixing on {d}; last fixing {prior} is {stale} business day(s) old "
                                    f"(tolerance {tol})"})
    return pd.DataFrame(rows, columns=COLUMNS)


def duplicate_cash_flows(ds: Dataset, cfg: Config, fx: FxBook) -> pd.DataFrame:
    cf = ds["cash_flow_forecast"]
    pairs = duplicate_pairs(cf, cfg.policy["duplicate_date_tolerance_days"])
    if pairs.empty:
        return pd.DataFrame(columns=COLUMNS)
    m = pairs.merge(cf, on="cf_id")
    rows = []
    for ccy, g in m.groupby("currency"):
        usd = _usd(fx, g["amount"], ccy, g["recorded_at"].dt.normalize())
        for (_, r), u in zip(g.iterrows(), usd):
            how = "same reference" if r.rule_id == "R-DUP-001" else "same counterparty, amount and near date"
            rows.append({"rule_id": r.rule_id, "category": "DATA_QUALITY", "exception_type": "DUPLICATE_CASH_FLOW",
                         "severity": "MEDIUM", "record_table": "cash_flow_forecast", "record_id": r.cf_id,
                         "related_record_id": r.original_cf_id, "entity_id": r.entity_id, "account_id": r.account_id,
                         "impact_usd": int(u), "decision": "EXCLUDE_DUPLICATE",
                         "details": f"Manual item repeats {r.original_cf_id} ({how}); counting both would double the cash flow"})
    return pd.DataFrame(rows, columns=COLUMNS)


def mixed_currency_items(ds: Dataset, cfg: Config, fx: FxBook) -> pd.DataFrame:
    cf = ds["cash_flow_forecast"]
    found = mixed_currency(cf, ds["bank_account"], ds["receivable"], ds["payable"])
    if found.empty:
        return pd.DataFrame(columns=COLUMNS)
    m = found.merge(cf[["cf_id", "entity_id", "account_id", "currency", "amount", "recorded_at"]], on="cf_id")
    m["account_currency"] = m["account_id"].map(ds["bank_account"].set_index("account_id")["currency"])
    rows = []
    for ccy, g in m.groupby("source_currency"):
        usd = _usd(fx, g["source_amount"], ccy, g["recorded_at"].dt.normalize())
        for (_, r), u in zip(g.iterrows(), usd):
            what = (f"item in {r.currency} on a {r.account_currency} account" if r.rule_id == "R-CUR-001"
                    else f"{r.source_currency} invoice amount copied unconverted into {r.currency}")
            rows.append({"rule_id": r.rule_id, "category": "DATA_QUALITY", "exception_type": "MIXED_CURRENCY",
                         "severity": "HIGH", "record_table": "cash_flow_forecast", "record_id": r.cf_id,
                         "entity_id": r.entity_id, "account_id": r.account_id, "impact_usd": int(u),
                         "decision": "CONVERT_AT_CUTOFF_RATE", "details": f"Currency mixed without conversion: {what}"})
    return pd.DataFrame(rows, columns=COLUMNS)


def lookahead_runs(ds: Dataset) -> pd.DataFrame:
    runs = ds["forecast_run"].set_index("run_id")
    items = ds["forecast_run_item"].join(runs["knowledge_cutoff_ts"], on="run_id")
    late_items = items[items["input_recorded_at"] >= items["knowledge_cutoff_ts"]].groupby("run_id").size()
    bal = ds["forecast_run_balance_input"].join(runs["cutoff_date"], on="run_id")
    late_bal = bal[bal["statement_date"] >= bal["cutoff_date"]].groupby("run_id").size()
    fxin = ds["forecast_run_fx_input"].join(runs["cutoff_date"], on="run_id")
    late_fx = fxin[fxin["rate_date"] >= fxin["cutoff_date"]].groupby("run_id").size()
    flagged = sorted(set(late_items.index) | set(late_bal.index) | set(late_fx.index))
    rows = []
    for run_id in flagged:
        n_i, n_b, n_f = int(late_items.get(run_id, 0)), int(late_bal.get(run_id, 0)), int(late_fx.get(run_id, 0))
        rows.append({"rule_id": "R-LEAK-001", "category": "DATA_QUALITY", "exception_type": "LOOKAHEAD_LEAKAGE",
                     "severity": "CRITICAL", "record_table": "forecast_run", "record_id": run_id, "run_id": run_id,
                     "decision": "SUPERSEDE_WITH_RERUN",
                     "details": f"Inputs recorded after the knowledge cutoff: {n_i} forecast items, {n_b} opening balances, {n_f} FX rates"})
    return pd.DataFrame(rows, columns=COLUMNS)


def detect_all(ds: Dataset, cfg: Config, fx: FxBook) -> pd.DataFrame:
    parts = [reconciliation_breaks(ds, cfg, fx), missing_fx_rates(ds, cfg), duplicate_cash_flows(ds, cfg, fx),
             mixed_currency_items(ds, cfg, fx), lookahead_runs(ds)]
    out = pd.concat([p for p in parts if len(p)], ignore_index=True) if any(len(p) for p in parts) else pd.DataFrame(columns=COLUMNS)
    return out.sort_values(["rule_id", "record_id"]).reset_index(drop=True)


def liquidity_alerts(positions: pd.DataFrame, run_id: str) -> pd.DataFrame:
    """R-LIQ-001: one alert per entity and scenario whose projected available cash breaches its buffer."""
    p = positions[(positions["run_id"] == run_id) & positions["breach_flag"].astype(bool)]
    if p.empty:
        return pd.DataFrame(columns=COLUMNS)
    rows = []
    for (sid, ent), g in p.groupby(["scenario_id", "entity_id"]):
        first = g["position_date"].min()
        gap = int((g["min_buffer_usd"] - g["closing_available_usd"]).max())
        sev = {"BASE": "HIGH", "DELAY": "MEDIUM", "STRESS": "LOW"}[sid.split("-")[1]]
        rows.append({"rule_id": "R-LIQ-001", "category": "BUSINESS_ALERT", "exception_type": "LIQUIDITY_BREACH",
                     "severity": sev, "record_table": "forecast_position", "record_id": f"{run_id}|{sid}|{ent}",
                     "entity_id": ent, "run_id": run_id, "impact_usd": gap, "decision": "FUNDING_REVIEW",
                     "details": f"{sid}: available cash below buffer from {first:%Y-%m-%d} on {len(g)} day(s); "
                                f"largest shortfall USD {gap / 100:,.0f}"})
    return pd.DataFrame(rows, columns=COLUMNS)
