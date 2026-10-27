"""Read-only data layer for the CashPilot dashboard.

Everything here selects, joins and converts *existing* results - positions, forecast runs, lineage,
exceptions, variance attribution. No financial rule is re-implemented: forecasts are rebuilt with
``engine.compare.scenario_items``, variance with ``engine.explain``, reproducibility with
``engine.forecast.recreate_run``, outlooks with ``evaluate.metrics``. Nothing is written to disk.

Units: functions return **major units** (dollars, euros, yen), not the integer minor units used
inside the engine. Columns ending in ``_usd`` are in the reporting currency (USD in the shipped
profiles; its two decimals are assumed by ``_usd_major``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from cashpilot.core import calendar as cal
from cashpilot.core.config import Config
from cashpilot.core.money import MINOR_UNITS, to_usd
from cashpilot.dashboard.text import PURPOSE_TEXT, plain_change, plain_reason
from cashpilot.dataset import Dataset
from cashpilot.engine.compare import scenario_items
from cashpilot.engine.forecast import LIVE_TREATMENTS, ForecastContext, recreate_run
from cashpilot.engine.positions import fx_book
from cashpilot.evaluate.metrics import evaluate, liquidity_outlook
from cashpilot.pipeline import load_dataset
from cashpilot.quality.detectors import missing_fx_rates

SIGNATURE_FILES = ("manifest.json", "generation_config.json", "csv/forecast_run.csv", "csv/ledger_entry.csv", "csv/exception.csv")

RULE_TEXT = {
    "R-RECON-001": "The bank statement's daily movement differs from the movement booked in the ledger (opening + ledger != closing).",
    "R-FX-001": "A business-day FX fixing is missing. Up to the staleness tolerance the previous rate is used; beyond it conversion is blocked.",
    "R-DUP-001": "A manual forecast item carries the same invoice/bill reference as a subledger item: the same cash flow would be counted twice.",
    "R-DUP-002": "A manual forecast item matches a subledger item on entity, account, direction, currency, counterparty and amount, dated within the tolerance.",
    "R-CUR-001": "The forecast item's currency differs from its bank account's currency and no conversion is recorded.",
    "R-CUR-002": "The item is linked to a foreign-currency document but carries the document's amount without conversion.",
    "R-LEAK-001": "The forecast run used records that were recorded after its knowledge cutoff (it saw the future).",
    "R-LIQ-001": "Projected available cash falls below the entity's minimum liquidity buffer within the horizon.",
}
DECISION_TEXT = {
    "RAISE_RECON_BREAK": "Raise a reconciliation break; the difference stays visible in bank-minus-book until the item is booked.",
    "USE_PREVIOUS_RATE": "Use the previous available rate (within tolerance) and flag the valuation as FALLBACK.",
    "BLOCK_CONVERSION": "Do not convert: the USD value stays empty and the entity total is flagged INCOMPLETE.",
    "EXCLUDE_DUPLICATE": "Exclude the manual duplicate from forecasts; the subledger item stays.",
    "CONVERT_AT_CUTOFF_RATE": "Convert the item at the run's snapshot rate (or quarantine it if no rate is available).",
    "SUPERSEDE_WITH_RERUN": "Re-run the forecast as of its cutoff and supersede the leaky version; the old version stays in the history.",
    "FUNDING_REVIEW": "Review funding for the entity (for example an intra-group top-up from the pool header).",
}


# ------------------------------------------------------------------ loading

@dataclass
class Bundle:
    """A loaded dataset folder plus lazily built engine helpers."""
    ds: Dataset
    cfg: Config
    path: Path | None = None

    @cached_property
    def fx(self):
        return fx_book(self.ds, self.cfg.policy, self.cfg.reporting_currency)

    @cached_property
    def ctx(self) -> ForecastContext:
        return ForecastContext(self.ds, self.cfg, self.fx)

    @cached_property
    def entity_names(self) -> dict:
        return self.ds["legal_entity"].set_index("entity_id")["entity_name"].to_dict()

    @property
    def reporting(self) -> str:
        return self.cfg.reporting_currency


def load_bundle(path) -> Bundle:
    ds, cfg = load_dataset(Path(path))
    return Bundle(ds, cfg, Path(path))


def dataset_signature(path) -> tuple:
    """Changes whenever the dataset files change, so cached results are never stale."""
    root = Path(path)
    parts = []
    for rel in SIGNATURE_FILES:
        f = root / rel
        parts.append((rel, f.stat().st_mtime_ns, f.stat().st_size) if f.is_file() else (rel, None, None))
    return tuple(parts)


def discover_datasets(root: Path | str = ".") -> list[Path]:
    root = Path(root)
    found = []
    for base in ("data", "out"):
        for child in sorted((root / base).glob("*")):
            if (child / "generation_config.json").is_file() and (child / "csv" / "forecast_run.csv").is_file():
                found.append(child)
    return found


# -------------------------------------------------------------------- units

def _f(series: pd.Series) -> pd.Series:
    """Nullable integer minor units -> float (NA -> NaN)."""
    return series.astype("Float64").astype("float64")


def _usd_major(series: pd.Series) -> pd.Series:
    return _f(series) / 100.0


def major(amount: pd.Series, currency: pd.Series) -> pd.Series:
    """Minor units -> major units, per row currency (JPY has none)."""
    return _f(amount) / (10.0 ** currency.map(MINOR_UNITS).astype(float))


def _ts(value) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


# ----------------------------------------------------------- consolidated cash

def complete_dates(ds: Dataset) -> list[pd.Timestamp]:
    """Dates on which every entity could be fully converted to the reporting currency."""
    e = ds["entity_cash_position"]
    bad = set(e.loc[e["fx_status"] == "INCOMPLETE", "position_date"])
    return sorted(set(e["position_date"]) - bad)


def default_date(ds: Dataset) -> pd.Timestamp:
    dates = complete_dates(ds)
    return dates[-1] if dates else ds["entity_cash_position"]["position_date"].max()


def cash_overview(b: Bundle, on) -> pd.DataFrame:
    e = b.ds["entity_cash_position"]
    e = e[e["position_date"] == _ts(on)]
    ent = b.ds["legal_entity"].set_index("entity_id")
    out = pd.DataFrame({
        "entity_id": e["entity_id"].to_numpy(),
        "entity_name": e["entity_id"].map(ent["entity_name"]).to_numpy(),
        "size_tier": e["entity_id"].map(ent["size_tier"]).to_numpy(),
        "total_usd": _usd_major(e["total_usd"]).to_numpy(),
        "available_usd": _usd_major(e["available_usd"]).to_numpy(),
        "restricted_usd": _usd_major(e["restricted_usd"]).to_numpy(),
        "min_buffer_usd": _usd_major(e["min_buffer_usd"]).to_numpy(),
        "headroom_usd": _usd_major(e["headroom_usd"]).to_numpy(),
        "fx_status": e["fx_status"].to_numpy(),
        "accounts_active": e["accounts_active"].astype(int).to_numpy(),
    })
    out["buffer_status"] = np.where(out["fx_status"] == "INCOMPLETE", "INCOMPLETE FX",
                                    np.where(out["headroom_usd"] < 0, "BELOW BUFFER", "OK"))
    return out.sort_values(["headroom_usd", "entity_id"]).reset_index(drop=True)


def group_summary(overview: pd.DataFrame) -> dict:
    return {
        "total_usd": float(overview["total_usd"].sum()),
        "available_usd": float(overview["available_usd"].sum()),
        "restricted_usd": float(overview["restricted_usd"].sum()),
        "min_buffer_usd": float(overview["min_buffer_usd"].sum()),
        "headroom_usd": float(overview["headroom_usd"].sum()),
        "entities": int(len(overview)),
        "entities_below_buffer": int((overview["buffer_status"] == "BELOW BUFFER").sum()),
        "entities_incomplete_fx": int((overview["buffer_status"] == "INCOMPLETE FX").sum()),
    }


def cash_history(b: Bundle, entity: str | None = None) -> pd.DataFrame:
    """Daily actual cash (group, or one entity) in the reporting currency."""
    e = b.ds["entity_cash_position"]
    if entity:
        e = e[e["entity_id"] == entity]
    g = e.groupby("position_date").agg(
        total_usd=("total_usd", "sum"), available_usd=("available_usd", "sum"), restricted_usd=("restricted_usd", "sum"),
        min_buffer_usd=("min_buffer_usd", "sum"), headroom_usd=("headroom_usd", "sum"),
        incomplete=("fx_status", lambda s: bool((s == "INCOMPLETE").any()))).reset_index()
    for c in ("total_usd", "available_usd", "restricted_usd", "min_buffer_usd", "headroom_usd"):
        g[c] = g[c].astype("float64") / 100.0
    return g


def account_balances(b: Bundle, on) -> pd.DataFrame:
    """Every active account on a date: local balance, rate used and its reporting-currency value."""
    d = b.ds["daily_cash_position"]
    d = d[d["position_date"] == _ts(on)]
    acc = b.ds["bank_account"].set_index("account_id")
    rates = b.ds["currency_rate"].set_index("rate_id")
    out = pd.DataFrame({
        "account_id": d["account_id"].to_numpy(),
        "entity_id": d["entity_id"].to_numpy(),
        "entity_name": d["entity_id"].map(b.entity_names).to_numpy(),
        "bank_name": d["account_id"].map(acc["bank_name"]).to_numpy(),
        "account_type": d["account_id"].map(acc["account_type"]).to_numpy(),
        "restricted": d["account_id"].map(acc["is_restricted"]).astype(bool).to_numpy(),
        "currency": d["currency"].to_numpy(),
        "local_balance": major(d["closing_balance"], d["currency"]).to_numpy(),
        "fx_rate_id": d["fx_rate_id"].to_numpy(),
        "rate_usd_per_unit": d["fx_rate_id"].map(rates["rate"]).astype("float64").to_numpy(),
        "rate_date": d["fx_rate_id"].map(rates["rate_date"]).to_numpy(),
        "fx_status": d["fx_status"].to_numpy(),
        "balance_usd": _usd_major(d["closing_balance_usd"]).to_numpy(),
        "bank_minus_book_local": major(d["bank_minus_book"], d["currency"]).to_numpy(),
    })
    out.loc[out["currency"] == b.reporting, "rate_usd_per_unit"] = 1.0
    return out.sort_values(["entity_id", "account_id"]).reset_index(drop=True)


def currency_exposure(b: Bundle, on, shock_pct: float = -10.0) -> pd.DataFrame:
    """Cash by currency with its reporting-currency value and a simple sensitivity to a uniform FX move.

    The sensitivity is plain arithmetic (value x shock), labelled as such in the app; it is not a forecast.
    """
    a = account_balances(b, on)
    g = a.groupby("currency").agg(
        accounts=("account_id", "size"), local_total=("local_balance", "sum"), usd_value=("balance_usd", "sum"),
        accounts_without_rate=("balance_usd", lambda s: int(s.isna().sum())), rate=("rate_usd_per_unit", "first"),
        worst_fx_status=("fx_status", lambda s: "MISSING" if (s == "MISSING").any() else ("FALLBACK" if (s == "FALLBACK").any() else "OK"))).reset_index()
    total = g["usd_value"].sum()
    g["share_of_total"] = g["usd_value"] / total if total else np.nan
    g["usd_impact_of_shock"] = np.where(g["currency"] == b.reporting, 0.0, g["usd_value"] * shock_pct / 100.0)
    return g.sort_values("usd_value", ascending=False).reset_index(drop=True)


def exposure_matrix(b: Bundle, on) -> pd.DataFrame:
    a = account_balances(b, on)
    m = a.pivot_table(index=["entity_id", "entity_name"], columns="currency", values="balance_usd", aggfunc="sum", fill_value=0.0)
    return m.reset_index()


def fx_history(b: Bundle) -> pd.DataFrame:
    r = b.ds["currency_rate"]
    return r.pivot(index="rate_date", columns="base_currency", values="rate").astype("float64").reset_index()


def fx_gaps(b: Bundle) -> pd.DataFrame:
    g = missing_fx_rates(b.ds, b.cfg)
    if g.empty:
        return pd.DataFrame(columns=["record_id", "rate_date", "currency", "decision", "details"])
    g = g.assign(rate_date=pd.to_datetime(g["record_id"].str.slice(4, 14)), currency=g["record_id"].str.slice(15, 18))
    return g[["record_id", "rate_date", "currency", "decision", "details"]].sort_values(["currency", "rate_date"]).reset_index(drop=True)


# ----------------------------------------------------------------- forecasts

def run_catalog(ds: Dataset) -> pd.DataFrame:
    r = ds["forecast_run"].copy()
    r["label"] = r["run_id"] + "  ·  " + r["run_purpose"].map(lambda x: PURPOSE_TEXT.get(x, x.lower())) + "  ·  " + r["status_at_end"].str.lower()
    return r.sort_values(["cutoff_date", "version"]).reset_index(drop=True)


def default_run(ds: Dataset) -> str:
    r = run_catalog(ds)
    live = r[r["run_purpose"] == "LIVE"]
    return str((live if len(live) else r)["run_id"].iloc[-1])


def runs_with_actuals(ds: Dataset) -> list[str]:
    """Run IDs that have at least one fully elapsed week to compare with actuals, oldest first."""
    have = set(ds["forecast_vs_actual"]["run_id"])
    r = run_catalog(ds)
    return r.loc[r["run_id"].isin(have), "run_id"].tolist()


def default_accuracy_run(ds: Dataset, min_weeks: int = 4) -> str:
    """The latest past run with several elapsed weeks (a one-week comparison makes a poor first view)."""
    f = ds["forecast_vs_actual"]
    weeks = f[f["scenario_id"].str.startswith("SCN-BASE")].groupby("run_id")["week_no"].nunique()
    ids = runs_with_actuals(ds)
    return ([r for r in ids if weeks.get(r, 0) >= min_weeks] or ids)[-1]


def run_scenarios(ds: Dataset, run_id: str) -> list[str]:
    s = ds["forecast_run_scenario"]
    ids = s.loc[s["run_id"] == run_id, "scenario_id"].tolist()
    return sorted(ids, key=lambda x: {"BASE": 0, "DELAY": 1, "STRESS": 2}.get(x.split("-")[1], 9))


def forecast_series(ds: Dataset, run_id: str, scenario_id: str, entity: str | None = None) -> pd.DataFrame:
    p = ds["forecast_position"]
    p = p[(p["run_id"] == run_id) & (p["scenario_id"] == scenario_id)]
    if entity:
        p = p[p["entity_id"] == entity]
    p = p.assign(breach=p["breach_flag"].astype(int))
    g = p.groupby("position_date").agg(
        opening_usd=("opening_available_usd", "sum"), inflows_usd=("inflows_usd", "sum"), outflows_usd=("outflows_usd", "sum"),
        closing_available_usd=("closing_available_usd", "sum"), restricted_usd=("restricted_usd", "sum"),
        min_buffer_usd=("min_buffer_usd", "sum"), entities_below_buffer=("breach", "sum")).reset_index()
    g["entities_below_buffer"] = g["entities_below_buffer"].astype(int)
    for c in ("opening_usd", "inflows_usd", "outflows_usd", "closing_available_usd", "restricted_usd", "min_buffer_usd"):
        g[c] = g[c].astype("float64") / 100.0
    g["headroom_usd"] = g["closing_available_usd"] - g["min_buffer_usd"]
    return g


def weekly_view(series: pd.DataFrame) -> pd.DataFrame:
    s = series.copy()
    start = s["position_date"].min()
    s["week_no"] = (s["position_date"] - start).dt.days // 7 + 1
    w = s.groupby("week_no").agg(
        week_start=("position_date", "min"), week_end=("position_date", "max"), inflows_usd=("inflows_usd", "sum"),
        outflows_usd=("outflows_usd", "sum"), closing_available_usd=("closing_available_usd", "last"),
        lowest_available_usd=("closing_available_usd", "min"), min_buffer_usd=("min_buffer_usd", "last"),
        days_below_buffer=("headroom_usd", lambda h: int((h < 0).sum()))).reset_index()
    w["net_usd"] = w["inflows_usd"] - w["outflows_usd"]
    return w


def scenario_curves(ds: Dataset, run_id: str, entity: str | None = None) -> pd.DataFrame:
    wide = {}
    for sid in run_scenarios(ds, run_id):
        s = forecast_series(ds, run_id, sid, entity)
        wide[sid] = s.set_index("position_date")["closing_available_usd"]
    out = pd.DataFrame(wide)
    s0 = forecast_series(ds, run_id, run_scenarios(ds, run_id)[0], entity).set_index("position_date")
    out["minimum buffer"] = s0["min_buffer_usd"]
    return out.reset_index()


def scenario_comparison(ds: Dataset, run_id: str) -> pd.DataFrame:
    outlook = liquidity_outlook(ds, run_id)
    rows = []
    for sid, s in outlook.get("scenarios", {}).items():
        rows.append({"scenario_id": sid, "opening_available_usd": s["opening_available_usd"], "lowest_available_usd": s["lowest_available_usd"],
                     "lowest_on": s["lowest_on"], "closing_available_usd": s["closing_available_usd"],
                     "entities_below_buffer": s["entities_breaching"], "funding_gap_usd": s["funding_gap_usd"]})
    out = pd.DataFrame(rows)
    if len(out):
        out["lowest_vs_base_usd"] = out["lowest_available_usd"] - out["lowest_available_usd"].iloc[0]
        out["funding_gap_vs_base_usd"] = out["funding_gap_usd"] - out["funding_gap_usd"].iloc[0]
    return out


def entity_breaches(ds: Dataset, run_id: str, scenario_id: str) -> pd.DataFrame:
    s = liquidity_outlook(ds, run_id).get("scenarios", {}).get(scenario_id, {})
    return pd.DataFrame(s.get("breaches", []), columns=["entity_id", "entity_name", "first_breach", "days_below_buffer", "max_shortfall_usd"])


def assumption_table(ds: Dataset, run_id: str) -> pd.DataFrame:
    eff = ds["scenario_assumption_effect"]
    eff = eff[eff["run_id"] == run_id].merge(
        ds["scenario_assumption"][["assumption_id", "parameter", "filter_field", "filter_value", "value", "unit", "rationale"]], on="assumption_id")
    out = eff.sort_values(["scenario_id", "apply_order"])[["scenario_id", "apply_order", "assumption_id", "parameter", "filter_field",
                                                           "filter_value", "value", "unit", "rationale", "items_affected",
                                                           "delta_net_flow_usd", "delta_min_available_usd"]].copy()
    out["delta_net_flow_usd"] = out["delta_net_flow_usd"].astype("float64") / 100.0
    out["delta_min_available_usd"] = out["delta_min_available_usd"].astype("float64") / 100.0
    return out.reset_index(drop=True)


# -------------------------------------------------------- cash-flow drivers

def cashflow_items(b: Bundle, run_id: str, scenario_id: str) -> pd.DataFrame:
    """Every forecast item of a run as the scenario sees it (dates and amounts after its assumptions)."""
    ds = b.ds
    run = ds["forecast_run"].set_index("run_id", drop=False).loc[run_id]
    lineage = ds["forecast_run_item"]
    lineage = lineage[lineage["run_id"] == run_id]
    fxin = ds["forecast_run_fx_input"]
    fxin = fxin[fxin["run_id"] == run_id]
    items, rates = scenario_items(b.ctx, run, lineage, fxin, scenario_id)
    base_id = run_scenarios(ds, run_id)[0]
    base_items, _ = scenario_items(b.ctx, run, lineage, fxin, base_id)
    items = items.copy()
    items["base_date"] = base_items["date"].to_numpy()          # same lineage, same order
    usd = np.zeros(len(items))
    for ccy, idx in items.groupby("currency_used").groups.items():
        pos = items.index.get_indexer(idx)
        usd[pos] = to_usd(items.loc[idx, "amount_used"].to_numpy(dtype=np.int64), ccy, np.full(len(idx), rates[ccy])) / 100.0
    sign = np.where(items["direction"] == "INFLOW", 1.0, -1.0)
    items["usd"] = usd
    items["signed_usd"] = usd * sign
    items["amount_local"] = major(items["amount_used"], items["currency_used"]).to_numpy()
    cf = b.ctx.cf
    for col in ("counterparty_id", "source_reference"):
        items[col] = items["cf_id"].map(cf[col]) if cf.index.name == "cf_id" else items["cf_id"].map(cf.set_index("cf_id")[col])
    items["shifted_days"] = (items["date"] - items["base_date"]).dt.days
    horizon_end = _ts(run["horizon_end"])
    items["live"] = items["treatment"].isin(LIVE_TREATMENTS)
    items["in_horizon"] = items["live"] & (items["date"] <= horizon_end)
    items["week_no"] = ((items["date"] - _ts(run["cutoff_date"])).dt.days // 7 + 1).where(items["live"])
    items["entity_name"] = items["entity_id"].map(b.entity_names)
    cols = ["cf_id", "entity_id", "entity_name", "direction", "flow_category", "source_system", "counterparty_id", "source_reference",
            "risk_tier", "treatment", "date", "base_date", "shifted_days", "currency_used", "amount_local", "usd", "signed_usd",
            "week_no", "live", "in_horizon"]
    return items[cols].reset_index(drop=True)


def driver_summary(items: pd.DataFrame, entity: str | None = None) -> pd.DataFrame:
    """Weekly net cash by flow category inside the horizon (positive = inflow)."""
    i = items[items["in_horizon"]]
    if entity:
        i = i[i["entity_id"] == entity]
    return i.pivot_table(index="week_no", columns="flow_category", values="signed_usd", aggfunc="sum", fill_value=0.0).reset_index()


def run_diff(b: Bundle, run_a: str, run_b: str) -> dict:
    """Why did the forecast change between two runs? Item, rate and balance differences with their reasons."""
    ds = b.ds
    runs = ds["forecast_run"].set_index("run_id")
    li = ds["forecast_run_item"]
    la = li[li["run_id"] == run_a].set_index("cf_id")
    lb = li[li["run_id"] == run_b].set_index("cf_id")
    fx = ds["forecast_run_fx_input"]
    rate_a = fx[fx["run_id"] == run_a].set_index("currency_code")["rate_used"].to_dict() | {b.reporting: 1.0}
    rate_b = fx[fx["run_id"] == run_b].set_index("currency_code")["rate_used"].to_dict() | {b.reporting: 1.0}
    cf = ds["cash_flow_forecast"].set_index("cf_id")
    rev = ds["cf_revision"]
    k_a, k_b = runs.at[run_a, "knowledge_cutoff_ts"], runs.at[run_b, "knowledge_cutoff_ts"]

    def signed(rows: pd.DataFrame, rates: dict) -> pd.Series:
        vals = pd.Series(0.0, index=rows.index)
        for ccy, idx in rows.groupby("currency").groups.items():
            vals.loc[idx] = to_usd(rows.loc[idx, "amount_used"].to_numpy(dtype=np.int64), ccy, np.full(len(idx), rates[ccy])) / 100.0
        sign = rows.index.map(lambda c: 1.0 if cf.at[c, "direction"] == "INFLOW" else -1.0)
        return vals * np.asarray(sign)

    sa, sb = signed(la, rate_a), signed(lb, rate_b)
    rows = []
    for cf_id in la.index.union(lb.index):
        in_a, in_b = cf_id in la.index, cf_id in lb.index
        live_a = in_a and la.at[cf_id, "treatment"] in LIVE_TREATMENTS
        live_b = in_b and lb.at[cf_id, "treatment"] in LIVE_TREATMENTS
        va, vb = (sa[cf_id] if live_a else 0.0), (sb[cf_id] if live_b else 0.0)
        da = la.at[cf_id, "expected_date_used"] if live_a else pd.NaT
        db = lb.at[cf_id, "expected_date_used"] if live_b else pd.NaT
        if not live_a and not live_b:
            continue
        if live_a and not live_b:
            kind = "REMOVED"
            r = rev[(rev["cf_id"] == cf_id) & (rev["recorded_at"] >= k_a) & (rev["recorded_at"] < k_b)].sort_values("revision_no")
            reason = (f"{r['revision_type'].iloc[-1]}: {r['reason'].iloc[-1]}" if len(r) else
                      ("EXCLUDED_BY_RULE: " + lb.at[cf_id, "treatment"] if in_b else "LEFT_THE_SNAPSHOT_OR_HORIZON"))
        elif live_b and not live_a:
            kind = "ADDED"
            reason = ("NEW_AFTER_PREVIOUS_CUTOFF" if cf.at[cf_id, "recorded_at"] >= k_a else "ENTERED_THE_HORIZON")
        else:
            changed = []
            if lb.at[cf_id, "treatment"] != la.at[cf_id, "treatment"]:
                changed.append("TREATMENT")
            if da != db:
                changed.append("DATE")
            if va != vb:
                changed.append("AMOUNT_OR_FX")
            if not changed:
                continue
            kind = "CHANGED_" + "+".join(changed)
            rv = lb.at[cf_id, "revision_id"]
            r = rev[rev["revision_id"] == rv] if pd.notna(rv) else rev.iloc[0:0]
            reason = f"{r['revision_type'].iloc[0]}: {r['reason'].iloc[0]}" if len(r) else (
                "OVERDUE_ROLLED" if lb.at[cf_id, "treatment"] == "OVERDUE_ROLLED" else "RATE_OR_ROLL_RULE")
        rows.append({"change_type": kind, "reason": reason, "cf_id": cf_id, "entity_id": cf.at[cf_id, "entity_id"],
                     "flow_category": cf.at[cf_id, "flow_category"], "direction": cf.at[cf_id, "direction"],
                     "counterparty_id": cf.at[cf_id, "counterparty_id"], "reference": cf.at[cf_id, "source_reference"],
                     "date_a": da, "date_b": db, "net_usd_a": va, "net_usd_b": vb, "change_usd": vb - va})
    items = pd.DataFrame(rows, columns=["change_type", "reason", "cf_id", "entity_id", "flow_category", "direction", "counterparty_id",
                                        "reference", "date_a", "date_b", "net_usd_a", "net_usd_b", "change_usd"])
    items = items.reindex(items["change_usd"].abs().sort_values(ascending=False, kind="mergesort").index).reset_index(drop=True)
    items.insert(1, "what_happened", items["reason"].map(plain_reason))
    items["change"] = items["change_type"].map(plain_change)
    fx_rows = pd.DataFrame([{"currency": c, "rate_a": rate_a.get(c), "rate_b": rate_b.get(c),
                             "change_pct": (rate_b[c] / rate_a[c] - 1) * 100 if c in rate_a and c in rate_b else np.nan}
                            for c in sorted((set(rate_a) | set(rate_b)) - {b.reporting})])

    bal = ds["forecast_run_balance_input"]
    restricted = ds["bank_account"].set_index("account_id")["is_restricted"]

    def opening(run_id, rates):
        x = bal[(bal["run_id"] == run_id)]
        x = x[~x["account_id"].map(restricted).astype(bool)]
        return float(sum(to_usd(x.loc[x["currency"] == c, "balance_used"].to_numpy(dtype=np.int64), c,
                                np.full((x["currency"] == c).sum(), rates[c])).sum() for c in x["currency"].unique())) / 100.0

    base_a, base_b = run_scenarios(ds, run_a)[0], run_scenarios(ds, run_b)[0]
    low = lambda rid, sid: forecast_series(ds, rid, sid)["closing_available_usd"].min()
    return {
        "items": items, "fx": fx_rows,
        "summary": {"items_added": int((items["change_type"] == "ADDED").sum()), "items_removed": int((items["change_type"] == "REMOVED").sum()),
                    "items_changed": int(items["change_type"].str.startswith("CHANGED").sum()),
                    "net_item_effect_usd": float(items["change_usd"].sum()),
                    "opening_available_a_usd": opening(run_a, rate_a), "opening_available_b_usd": opening(run_b, rate_b),
                    "lowest_available_a_usd": float(low(run_a, base_a)), "lowest_available_b_usd": float(low(run_b, base_b))},
    }


# ----------------------------------------------------- exceptions and tracing

def exceptions_table(b: Bundle) -> pd.DataFrame:
    e = b.ds["exception"].copy()
    e["entity_name"] = e["entity_id"].map(b.entity_names)
    e["impact_usd"] = _usd_major(e["impact_usd"])
    cols = ["exception_id", "rule_id", "exception_type", "category", "severity", "status_at_end", "entity_id", "entity_name", "account_id",
            "run_id", "record_table", "record_id", "related_record_id", "impact_usd", "decision", "details", "detected_at"]
    return e[cols].sort_values(["exception_id"]).reset_index(drop=True)


def _row(ds: Dataset, table: str, key: str, value) -> pd.Series | None:
    df = ds[table]
    hit = df[df[key] == value]
    return None if hit.empty else hit.iloc[0]


def _frame(rows: dict | pd.Series | None) -> pd.DataFrame:
    if rows is None:
        return pd.DataFrame(columns=["field", "value"])
    return pd.DataFrame({"field": list(rows.keys() if isinstance(rows, dict) else rows.index),
                         "value": [("" if pd.isna(v) else str(v)) if not isinstance(v, (list, dict)) else str(v)
                                   for v in (rows.values() if isinstance(rows, dict) else rows.values)]})


def exception_trace(b: Bundle, exception_id: str) -> dict:
    """Everything needed to understand one exception: the rule, the decision, the records and the history."""
    ds = b.ds
    exc = _row(ds, "exception", "exception_id", exception_id)
    if exc is None:
        raise KeyError(exception_id)
    events = ds["exception_event"]
    events = events[events["exception_id"] == exception_id].sort_values(["event_ts", "event_id"])[
        ["event_ts", "event_type", "from_status", "to_status", "actor_id", "comment"]].reset_index(drop=True)
    evidence: list[tuple[str, pd.DataFrame]] = []
    rid, etype = exc["record_id"], exc["exception_type"]

    if etype == "BALANCE_BREAK":
        s = _row(ds, "bank_statement", "statement_id", rid)
        led = ds["ledger_entry"]
        day = led[(led["account_id"] == s["account_id"]) & (led["posting_date"] == s["statement_date"])]
        ccy = s["currency"]
        booked = int(day["amount"].sum())
        bank = int(s["closing_balance"] - s["opening_balance"])
        sc = pd.Series({"account": s["account_id"], "statement date": f"{s['statement_date']:%Y-%m-%d}", "currency": ccy})
        evidence.append(("Bank statement vs ledger (local currency, major units)", pd.DataFrame({
            "measure": ["bank opening", "bank credits", "bank debits", "bank closing", "bank movement", "booked ledger movement", "difference (bank - book)"],
            "amount": [v / 10 ** MINOR_UNITS[ccy] for v in (s["opening_balance"], s["total_credits"], s["total_debits"], s["closing_balance"], bank, booked, bank - booked)]})))
        evidence.append(("Ledger entries booked on that account and day", day[["ledger_entry_id", "entry_type", "amount", "description"]]
                         .assign(amount=major(day["amount"], day["currency"])).reset_index(drop=True)))
        evidence.append(("Statement", _frame(sc)))
    elif etype == "FX_RATE_MISSING":
        ccy, day = rid[15:18], pd.Timestamp(rid[4:14])
        r = ds["currency_rate"]
        prev = r[(r["base_currency"] == ccy) & (r["rate_date"] < day)].sort_values("rate_date").tail(1)
        stale = int(cal.business_day_count(np.datetime64(prev["rate_date"].iloc[0].date()) + 1, np.datetime64(day.date()) + 1)) if len(prev) else None
        evidence.append(("Last available fixing before the gap", prev[["rate_id", "rate_date", "rate"]].reset_index(drop=True)))
        evidence.append(("Gap", pd.DataFrame({"measure": ["missing fixing", "business days since last fixing", "staleness tolerance (business days)"],
                                              "value": [rid, stale, b.cfg.policy["fx_staleness_business_days"]]}).astype({"value": str})))
        d = ds["daily_cash_position"]
        d = d[(d["currency"] == ccy) & (d["position_date"] == day)]
        note = "" if len(d) else " (none: no account held this currency on that date, so no balance was affected)"
        evidence.append((f"{ccy} account valuations on {day:%Y-%m-%d}{note}", pd.DataFrame({
            "account_id": d["account_id"], "balance_local": major(d["closing_balance"], d["currency"]), "fx_status": d["fx_status"],
            "fx_rate_id": d["fx_rate_id"], "balance_usd": _usd_major(d["closing_balance_usd"])}).reset_index(drop=True)))
    elif etype == "DUPLICATE_CASH_FLOW":
        cf = ds["cash_flow_forecast"].set_index("cf_id")
        a, o = cf.loc[rid], cf.loc[exc["related_record_id"]]
        fields = ["source_system", "direction", "flow_category", "counterparty_id", "source_reference", "currency", "amount", "expected_date",
                  "recorded_at", "created_by", "entity_id", "account_id"]
        evidence.append(("Suspected duplicate vs the original item", pd.DataFrame({
            "field": fields, "duplicate": [str(a[f]) for f in fields], "original": [str(o[f]) for f in fields]})))
    elif etype == "MIXED_CURRENCY":
        cf = ds["cash_flow_forecast"].set_index("cf_id")
        a = cf.loc[rid]
        acct_ccy = ds["bank_account"].set_index("account_id").at[a["account_id"], "currency"]
        doc_id = a["receivable_id"] if pd.notna(a["receivable_id"]) else a["payable_id"]
        doc = (_row(ds, "receivable", "receivable_id", doc_id) if pd.notna(a["receivable_id"]) else _row(ds, "payable", "payable_id", doc_id)) if pd.notna(doc_id) else None
        evidence.append(("Forecast item", pd.DataFrame({"field": ["currency", "amount", "account currency", "conversion recorded", "linked document"],
                                                        "value": [a["currency"], a["amount"] / 10 ** MINOR_UNITS[a["currency"]], acct_ccy,
                                                                  "no" if pd.isna(a["original_currency"]) else "yes", doc_id]}).astype({"value": str})))
        if doc is not None:
            evidence.append(("Source document", pd.DataFrame({"field": ["currency", "amount", "due date"],
                                                              "value": [doc["currency"], doc["amount"] / 10 ** MINOR_UNITS[doc["currency"]], f"{doc['due_date']:%Y-%m-%d}"]}).astype({"value": str})))
    elif etype == "LOOKAHEAD_LEAKAGE":
        run = _row(ds, "forecast_run", "run_id", rid)
        li = ds["forecast_run_item"]
        late = li[(li["run_id"] == rid) & (li["input_recorded_at"] >= run["knowledge_cutoff_ts"])]
        evidence.append((f"Run claims knowledge cutoff {run['knowledge_cutoff_ts']}; these inputs were recorded later", late[
            ["cf_id", "input_recorded_at", "treatment"]].assign(minutes_after_cutoff=lambda x: ((x["input_recorded_at"] - run["knowledge_cutoff_ts"]).dt.total_seconds() // 60).astype(int)
                                                              ).sort_values("input_recorded_at").head(50).reset_index(drop=True)))
        bal = ds["forecast_run_balance_input"]
        bal = bal[(bal["run_id"] == rid) & (bal["statement_date"] >= run["cutoff_date"])]
        fxi = ds["forecast_run_fx_input"]
        fxi = fxi[(fxi["run_id"] == rid) & (fxi["rate_date"] >= run["cutoff_date"])]
        evidence.append(("Opening balances taken from statements dated on/after the cutoff", bal[["account_id", "statement_id", "statement_date"]].reset_index(drop=True)))
        evidence.append(("FX rates dated on/after the cutoff", fxi[["currency_code", "rate_id", "rate_date"]].reset_index(drop=True)))
        runs = ds["forecast_run"]
        evidence.append(("Runs that supersede it", runs[runs["supersedes_run_id"] == rid][["run_id", "process", "run_purpose", "status_at_end", "created_at"]].reset_index(drop=True)))
    elif etype == "LIQUIDITY_BREACH":
        run_id, sid, ent = rid.split("|")
        p = ds["forecast_position"]
        p = p[(p["run_id"] == run_id) & (p["scenario_id"] == sid) & (p["entity_id"] == ent) & p["breach_flag"].astype(bool)]
        evidence.append(("Days below the buffer", pd.DataFrame({
            "date": p["position_date"], "available_usd": _usd_major(p["closing_available_usd"]), "buffer_usd": _usd_major(p["min_buffer_usd"]),
            "shortfall_usd": _usd_major(p["min_buffer_usd"] - p["closing_available_usd"])}).reset_index(drop=True)))
        items = cashflow_items(b, run_id, sid)
        items = items[(items["entity_id"] == ent) & items["in_horizon"]].copy()
        items["abs_usd"] = items["usd"]
        evidence.append(("Largest cash flows in the horizon for this entity (scenario view)", items.sort_values("abs_usd", ascending=False).head(10)[
            ["cf_id", "direction", "flow_category", "counterparty_id", "date", "shifted_days", "usd"]].reset_index(drop=True)))

    return {"exception": exc.to_dict(), "rule_text": RULE_TEXT.get(exc["rule_id"], ""), "decision_text": DECISION_TEXT.get(exc["decision"], ""),
            "events": events, "evidence": evidence}


def reconciliation_overview(b: Bundle) -> dict:
    d = b.ds["daily_cash_position"]
    open_diff = d[d["bank_minus_book"].fillna(0) != 0]
    by_acct = open_diff.groupby(["account_id", "currency"]).agg(days_with_difference=("position_date", "size"),
                                                                 latest_difference=("bank_minus_book", "last")).reset_index()
    by_acct["latest_difference"] = major(by_acct["latest_difference"], by_acct["currency"])
    exc = b.ds["exception"]
    breaks = exc[exc["exception_type"] == "BALANCE_BREAK"]
    return {"statements": int(len(b.ds["bank_statement"])), "breaks": int(len(breaks)), "breaks_high": int((breaks["severity"] == "HIGH").sum()),
            "account_days_with_open_difference": int(len(open_diff)), "accounts": by_acct.sort_values("days_with_difference", ascending=False).reset_index(drop=True)}


# ---------------------------------------------------- forecast vs actual, audit

def forecast_vs_actual(ds: Dataset, run_id: str, scenario_id: str, entity: str | None = None) -> pd.DataFrame:
    f = ds["forecast_vs_actual"]
    f = f[(f["run_id"] == run_id) & (f["scenario_id"] == scenario_id)]
    if entity:
        f = f[f["entity_id"] == entity]
    money_cols = [c for c in f.columns if c.endswith("_usd")]
    g = f.groupby(["week_no", "week_start", "week_end"])[money_cols].sum().reset_index()
    for c in money_cols:
        g[c] = g[c].astype("float64") / 100.0
    return g


def evaluation(b: Bundle) -> dict:
    """Ground-truth evaluation. The ground truth is read here only to score detections after the fact."""
    return evaluate(b.ds, b.cfg, b.ds.ground_truth)


def audit_trail(ds: Dataset, run_id: str) -> dict:
    run = _row(ds, "forecast_run", "run_id", run_id)
    ev = ds["forecast_run_event"]
    ev = ev[ev["run_id"] == run_id].sort_values(["event_ts", "event_id"])[["event_ts", "event_type", "from_status", "to_status", "actor_id", "comment"]]
    au = ds["audit_event"]
    au = au[au["target_id"] == run_id][["event_ts", "actor_id", "action", "outcome", "detail"]]
    li = ds["forecast_run_item"]
    lineage = li[li["run_id"] == run_id].groupby("treatment").size().rename("items").reset_index()
    return {"run": run.to_dict(), "events": ev.reset_index(drop=True), "audit": au.reset_index(drop=True), "lineage": lineage,
            "scenarios": run_scenarios(ds, run_id)}


def verify_reproducibility(b: Bundle, run_id: str) -> dict:
    """Re-run a stored run from the data as of its claimed knowledge cutoff and compare its hashes."""
    ds = b.ds
    run = ds["forecast_run"].set_index("run_id", drop=False).loc[run_id]
    result = recreate_run(b.ctx, run, run_scenarios(ds, run_id))
    same_in, same_out = result.run["input_hash"] == run["input_hash"], result.run["result_hash"] == run["result_hash"]
    return {"run_id": run_id, "reproduced": bool(same_in and same_out), "input_hash_matches": bool(same_in), "result_hash_matches": bool(same_out),
            "stored_input_hash": run["input_hash"], "recomputed_input_hash": result.run["input_hash"],
            "stored_result_hash": run["result_hash"], "recomputed_result_hash": result.run["result_hash"]}


def validation_overview(path) -> dict:
    f = Path(path) / "validation_summary.json"
    if not f.is_file():
        return {}
    d = json.loads(f.read_text(encoding="utf-8"))
    return {"overall": d["overall"], "checks": d["checks"], "by_status": d["by_status"], "baseline": d.get("baseline", {})}


def manifest_files(path) -> pd.DataFrame:
    f = Path(path) / "manifest.json"
    if not f.is_file():
        return pd.DataFrame(columns=["path", "rows", "bytes", "sha256"])
    return pd.DataFrame(json.loads(f.read_text(encoding="utf-8"))["files"])


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, lineterminator="\n").encode("utf-8")


def to_json_bytes(df: pd.DataFrame) -> bytes:
    return df.to_json(orient="records", date_format="iso", indent=1).encode("utf-8")
