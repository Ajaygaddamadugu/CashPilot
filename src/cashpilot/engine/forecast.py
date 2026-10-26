"""13-week liquidity forecast runs.

A run is a pure function of (records known before its knowledge cutoff, scenario versions,
engine rules):

1. Snapshot - forecast items with their latest revisions, opening balances (bank statements)
   and FX rates, each *recorded* before the knowledge cutoff (08:00 UTC on the cutoff date).
2. Projection rules - overdue items are rolled forward (F-ROLL-*); stale manual items are dropped.
3. Data-quality gate (CASHPILOT runs only) - manual duplicates are excluded, mixed-currency
   items are converted at the snapshot rate (or quarantined).
4. Scenarios - each scenario applies its documented assumptions, in order, to the *same*
   snapshot. Base has no assumptions.
5. Projection - daily available cash per entity in USD; a breach is available cash below the
   entity's minimum buffer. Restricted cash is reported separately.

Inputs (lineage) and outputs are hashed so any run can be re-created and compared byte for byte.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from cashpilot.core import ids
from cashpilot.core.config import Config
from cashpilot.core.money import convert, scale, to_usd
from cashpilot.dataset import Dataset, conform, to_text
from cashpilot.engine.fx import FxBook
from cashpilot.quality.rules import duplicate_pairs, mixed_currency
from cashpilot.schema import load_schema

ROLL_AR_DAYS = {"A": 3, "B": 7, "C": 14, "D": 30}   # F-ROLL-001: overdue receivables by customer tier
ROLL_AP_DAYS = 3                                     # F-ROLL-002: overdue payables
SCHEDULED = ("PAYROLL", "RENT", "TAX", "DEBT_SERVICE")  # F-ROLL-003: due today if overdue
STALE_MANUAL_DAYS = 7                                # F-ROLL-004: manual items this late are dropped
LIVE_TREATMENTS = ("INCLUDED", "OVERDUE_ROLLED", "CONVERTED")
DAY = pd.Timedelta(days=1)


@dataclass
class RunSpec:
    cutoff: pd.Timestamp
    version: int
    process: str
    purpose: str
    created_by: str
    created_at: pd.Timestamp
    scenario_ids: list[str]
    supersedes: str | None = None
    leak_days: int = 0  # >0 only to simulate the legacy look-ahead defect

    @property
    def run_id(self) -> str:
        return ids.run_id(self.cutoff, self.version)


@dataclass
class RunResult:
    run: dict
    scenarios: pd.DataFrame
    items: pd.DataFrame
    balances: pd.DataFrame
    fx: pd.DataFrame
    positions: pd.DataFrame
    effects: pd.DataFrame
    detail: dict = field(default_factory=dict)  # scenario_id -> adjusted items (for comparisons)


class ForecastContext:
    """Pre-indexed inputs shared by many runs over the same dataset."""

    def __init__(self, ds: Dataset, cfg: Config, fx: FxBook):
        self.cfg = cfg
        self.policy = cfg.policy
        self.horizon = int(cfg.forecast["horizon_days"])
        self.knowledge_hour = int(cfg.forecast["knowledge_hour_utc"])
        self.reporting = cfg.reporting_currency
        self.fx = fx
        self.accounts = ds["bank_account"].set_index("account_id")
        self.entities = ds["legal_entity"].set_index("entity_id")
        tier = ds["counterparty"].set_index("counterparty_id")["risk_tier"]
        cf = ds["cash_flow_forecast"].copy()
        cf["risk_tier"] = cf["counterparty_id"].map(tier)
        cf["account_currency"] = cf["account_id"].map(self.accounts["currency"])
        self.cf = cf
        self.rev = ds["cf_revision"].sort_values(["cf_id", "revision_no"]).reset_index(drop=True)
        self.statements = ds["bank_statement"].sort_values(["account_id", "statement_date"]).reset_index(drop=True)
        self.receivables = ds["receivable"]
        self.payables = ds["payable"]
        links = ds["scenario_assumption_link"].merge(ds["scenario_assumption"], on="assumption_id")
        self.assumptions = {s: g.sort_values("apply_order").to_dict("records") for s, g in links.groupby("scenario_id")}
        self.scenarios = ds["liquidity_scenario"]

    def knowledge_ts(self, cutoff) -> pd.Timestamp:
        return pd.Timestamp(cutoff).normalize() + pd.Timedelta(hours=self.knowledge_hour)

    def effective_scenarios(self, cutoff) -> list[str]:
        sc = self.scenarios
        c = pd.Timestamp(cutoff)
        live = sc[(sc["effective_from"] <= c) & (sc["effective_to"].isna() | (sc["effective_to"] >= c))]
        order = {"BASE": 0, "DELAY": 1, "STRESS": 2}
        return sorted(live["scenario_id"], key=lambda s: order[s.split("-")[1]])


# --------------------------------------------------------------------- snapshot

def _snapshot_items(ctx: ForecastContext, cutoff: pd.Timestamp, k_ts: pd.Timestamp, process: str, fx_rates: dict) -> pd.DataFrame:
    cf = ctx.cf[ctx.cf["recorded_at"] < k_ts]
    rev = ctx.rev[ctx.rev["recorded_at"] < k_ts]
    last = rev.groupby("cf_id").tail(1)[["cf_id", "revision_id", "recorded_at"]].rename(columns={"recorded_at": "rev_recorded_at"})
    dates = rev[rev["revision_type"] == "DATE_CHANGE"].groupby("cf_id").tail(1)[["cf_id", "new_expected_date"]]
    amounts = rev[rev["revision_type"] == "AMOUNT_CHANGE"].groupby("cf_id").tail(1)[["cf_id", "new_amount"]]
    closed = rev.loc[rev["revision_type"].isin(["SETTLED", "CANCELLED"]), "cf_id"]
    st = cf[~cf["cf_id"].isin(closed)].merge(last, on="cf_id", how="left").merge(dates, on="cf_id", how="left").merge(amounts, on="cf_id", how="left")
    st["date"] = st["new_expected_date"].fillna(st["expected_date"])
    st["amount_now"] = st["new_amount"].fillna(st["amount"]).astype(np.int64)
    st["input_recorded_at"] = st[["recorded_at", "rev_recorded_at"]].max(axis=1)

    horizon_end = cutoff + (ctx.horizon - 1) * DAY
    overdue = st["date"] < cutoff
    cat = st["flow_category"]
    treatment = pd.Series("INCLUDED", index=st.index, dtype=object)
    date = st["date"].copy()
    roll_ar = cutoff + pd.to_timedelta(st["risk_tier"].map(ROLL_AR_DAYS).fillna(7), unit="D")
    date = date.mask(overdue & (cat == "AR_COLLECTION"), roll_ar)
    date = date.mask(overdue & (cat == "AP_PAYMENT"), cutoff + ROLL_AP_DAYS * DAY)
    date = date.mask(overdue & cat.isin(SCHEDULED), cutoff)
    stale = overdue & (cat == "OTHER") & (st["date"] < cutoff - STALE_MANUAL_DAYS * DAY)
    date = date.mask(overdue & (cat == "OTHER") & ~stale, cutoff + ROLL_AP_DAYS * DAY)
    treatment = treatment.mask(overdue, "OVERDUE_ROLLED").mask(stale, "EXCLUDED_STALE")
    keep = ~(overdue & (cat == "OPERATING_RUN_RATE")) & ((date <= horizon_end) | stale)
    st = st.assign(date=date, treatment=treatment)[keep].reset_index(drop=True)

    st["currency_used"] = st["account_currency"]
    st["amount_used"] = st["amount_now"]
    if process == "CASHPILOT":
        # Compare against every item known at the cutoff: the original may already be settled.
        dups = duplicate_pairs(cf, ctx.policy["duplicate_date_tolerance_days"])
        st.loc[st["cf_id"].isin(dups["cf_id"]), "treatment"] = "EXCLUDED_DUPLICATE"
        mixed = mixed_currency(st, ctx.accounts.reset_index(), ctx.receivables, ctx.payables).set_index("cf_id")
        for cf_id, m in mixed.iterrows():
            i = st.index[st["cf_id"] == cf_id][0]
            src_rate, dst_rate = fx_rates.get(m.source_currency), fx_rates.get(st.at[i, "account_currency"])
            if src_rate is None or dst_rate is None or np.isnan(src_rate) or np.isnan(dst_rate):
                st.at[i, "treatment"] = "QUARANTINED"
                continue
            st.at[i, "amount_used"] = int(convert([m.source_amount], m.source_currency, st.at[i, "account_currency"], [src_rate], [dst_rate])[0])
            st.at[i, "treatment"] = "CONVERTED"
    excluded = ~st["treatment"].isin(LIVE_TREATMENTS)
    st.loc[excluded, "amount_used"] = 0
    st["date"] = st["date"].where(~excluded, pd.NaT)
    return st


def _snapshot_balances(ctx: ForecastContext, cutoff, k_ts, entities_in_scope) -> pd.DataFrame:
    st = ctx.statements[ctx.statements["recorded_at"] < k_ts]
    latest = st.groupby("account_id").tail(1)
    acc = ctx.accounts.loc[latest["account_id"]]
    keep = acc["entity_id"].isin(entities_in_scope).to_numpy() & ~(acc["closed_on"].notna() & (acc["closed_on"] < cutoff)).to_numpy()
    latest = latest[keep]
    return pd.DataFrame({
        "account_id": latest["account_id"].to_numpy(),
        "statement_id": latest["statement_id"].to_numpy(),
        "statement_date": latest["statement_date"].to_numpy(),
        "currency": latest["currency"].to_numpy(),
        "balance_used": latest["closing_balance"].to_numpy(dtype=np.int64),
    })


# -------------------------------------------------------------------- scenarios

def apply_assumption(items: pd.DataFrame, mult: dict, asm: dict, cutoff: pd.Timestamp) -> int:
    """Apply one assumption in place; return the number of items it changed."""
    live = items["treatment"].isin(LIVE_TREATMENTS)
    value = float(asm["value"])
    param = asm["parameter"]
    if param in ("AR_DELAY_DAYS", "AR_COLLECTION_RATE"):
        m = live & (items["direction"] == "INFLOW") & (items["flow_category"] == "AR_COLLECTION") & (items["risk_tier"] == asm["filter_value"])
        if param == "AR_DELAY_DAYS":
            if value == 0:
                return 0
            items.loc[m, "date"] = items.loc[m, "date"] + pd.Timedelta(days=int(value))
            return int(m.sum())
        new = scale(items["amount_used"], np.where(m, value, 1.0))
        changed = m & (new != items["amount_used"].to_numpy())
        items["amount_used"] = new
        return int(changed.sum())
    if param == "AP_TIMING_SHIFT_DAYS":
        m = live & (items["direction"] == "OUTFLOW") & (items["flow_category"] == "AP_PAYMENT")
        new = (items["date"] + pd.Timedelta(days=int(value))).clip(lower=cutoff)
        changed = m & (new != items["date"])
        items.loc[m, "date"] = new[m]
        return int(changed.sum())
    if param == "RUN_RATE_INFLOW_FACTOR":
        m = live & (items["direction"] == "INFLOW") & (items["flow_category"] == "OPERATING_RUN_RATE")
        new = scale(items["amount_used"], np.where(m, value, 1.0))
        changed = m & (new != items["amount_used"].to_numpy())
        items["amount_used"] = new
        return int(changed.sum())
    if param == "FX_SHOCK_PCT":
        excluded = asm["filter_value"] if asm["filter_field"] == "currency_not" else None
        for c in mult:
            if c != excluded:
                mult[c] *= 1 + value / 100
        return int((live & (items["currency_used"] != excluded)).sum())
    raise ValueError(f"unknown assumption parameter {param}")


# ------------------------------------------------------------------- projection

def project(ctx: ForecastContext, cutoff: pd.Timestamp, items: pd.DataFrame, balances: pd.DataFrame,
            rates: dict, mult: dict, entities: list[str]) -> pd.DataFrame:
    days = pd.date_range(cutoff, periods=ctx.horizon, freq="D")
    e_idx = {e: i for i, e in enumerate(entities)}
    n_e, n_d = len(entities), len(days)
    eff_rate = {c: rates[c] * mult.get(c, 1.0) for c in rates}

    live = items[items["treatment"].isin(LIVE_TREATMENTS) & (items["date"] <= days[-1])]
    inflow = np.zeros((n_e, n_d), dtype=np.int64)
    outflow = np.zeros((n_e, n_d), dtype=np.int64)
    if len(live):
        usd = np.zeros(len(live), dtype=np.int64)
        for c, idx in live.groupby("currency_used").groups.items():
            pos = live.index.get_indexer(idx)
            usd[pos] = to_usd(live.loc[idx, "amount_used"].to_numpy(), c, np.full(len(idx), eff_rate[c]))
        ei = live["entity_id"].map(e_idx).to_numpy()
        di = ((live["date"] - cutoff).dt.days).to_numpy()
        is_in = (live["direction"] == "INFLOW").to_numpy()
        np.add.at(inflow, (ei[is_in], di[is_in]), usd[is_in])
        np.add.at(outflow, (ei[~is_in], di[~is_in]), usd[~is_in])

    bal_usd = np.zeros(len(balances), dtype=np.int64)
    for c, idx in balances.groupby("currency").groups.items():
        pos = balances.index.get_indexer(idx)
        bal_usd[pos] = to_usd(balances.loc[idx, "balance_used"].to_numpy(), c, np.full(len(idx), eff_rate[c]))
    restricted = balances["account_id"].map(ctx.accounts["is_restricted"]).astype(bool).to_numpy()
    owner = balances["account_id"].map(ctx.accounts["entity_id"]).map(e_idx).to_numpy()
    opening = np.bincount(owner[~restricted], weights=bal_usd[~restricted], minlength=n_e).astype(np.int64) if len(balances) else np.zeros(n_e, np.int64)
    restr = np.bincount(owner[restricted], weights=bal_usd[restricted], minlength=n_e).astype(np.int64) if restricted.any() else np.zeros(n_e, np.int64)

    closing = opening[:, None] + np.cumsum(inflow - outflow, axis=1)
    opening_d = closing - (inflow - outflow)
    ent = ctx.entities.loc[entities]
    buffer = np.array([int(to_usd([b], f, [eff_rate[f]])[0]) for b, f in zip(ent["min_liquidity_buffer"], ent["functional_currency"])])
    return pd.DataFrame({
        "entity_id": np.repeat(entities, n_d),
        "position_date": np.tile(days, n_e),
        "opening_available_usd": opening_d.ravel(),
        "inflows_usd": inflow.ravel(),
        "outflows_usd": outflow.ravel(),
        "closing_available_usd": closing.ravel(),
        "restricted_usd": np.repeat(restr, n_d),
        "min_buffer_usd": np.repeat(buffer, n_d),
        "breach_flag": (closing < buffer[:, None]).ravel(),
    })


def _group_stats(pos: pd.DataFrame) -> tuple[int, int]:
    net = int(pos["inflows_usd"].sum() - pos["outflows_usd"].sum())
    min_avail = int(pos.groupby("position_date")["closing_available_usd"].sum().min()) if len(pos) else 0
    return net, min_avail


# -------------------------------------------------------------------------- run

def frame_hash(df: pd.DataFrame, table: str) -> str:
    t = load_schema().table(table)
    text = to_text(conform(df, t), t).sort_values(list(t.primary_key)).reset_index(drop=True)
    return hashlib.sha256(text.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()


def create_run(ctx: ForecastContext, spec: RunSpec) -> RunResult:
    if not spec.scenario_ids or not spec.scenario_ids[0].startswith("SCN-BASE"):
        raise ValueError("the base scenario must be evaluated first; other scenarios are measured against it")
    cutoff = pd.Timestamp(spec.cutoff).normalize()
    claimed_ts = ctx.knowledge_ts(cutoff)
    k_ts = claimed_ts + pd.Timedelta(days=spec.leak_days)  # equals the claimed cutoff unless simulating the defect
    run_id = spec.run_id
    entities = [e for e, f in ctx.entities["effective_from"].items() if f <= cutoff]

    fx_rows, rates = [], {ctx.reporting: 1.0}
    for c in sorted(set(ctx.accounts["currency"]) - {ctx.reporting}):
        rid, rdate, rate = ctx.fx.known_before(c, k_ts)
        rates[c] = rate
        if rid is not None:
            fx_rows.append({"run_id": run_id, "currency_code": c, "rate_id": rid, "rate_date": pd.Timestamp(rdate), "rate_used": rate})
    items = _snapshot_items(ctx, cutoff, k_ts, spec.process, rates)
    items = items[items["entity_id"].isin(entities)].reset_index(drop=True)
    balances = _snapshot_balances(ctx, cutoff, k_ts, entities)

    lineage_items = pd.DataFrame({
        "run_id": run_id, "cf_id": items["cf_id"], "revision_id": items["revision_id"],
        "input_recorded_at": items["input_recorded_at"], "treatment": items["treatment"],
        "expected_date_used": items["date"], "currency": items["currency_used"], "amount_used": items["amount_used"],
    })
    lineage_bal = balances.assign(run_id=run_id)
    lineage_fx = pd.DataFrame(fx_rows, columns=["run_id", "currency_code", "rate_id", "rate_date", "rate_used"])

    positions, effects, detail = [], [], {}
    base_stats = None
    for sid in spec.scenario_ids:
        it = items.copy()
        mult = {c: 1.0 for c in rates}
        stats_prev = base_stats
        for asm in ctx.assumptions.get(sid, []):
            n = apply_assumption(it, mult, asm, cutoff)
            pos_k = project(ctx, cutoff, it, balances, rates, mult, entities)
            stats_k = _group_stats(pos_k)
            effects.append({"run_id": run_id, "scenario_id": sid, "assumption_id": asm["assumption_id"], "apply_order": asm["apply_order"],
                            "items_affected": n, "delta_net_flow_usd": stats_k[0] - stats_prev[0],
                            "delta_min_available_usd": stats_k[1] - stats_prev[1]})
            stats_prev = stats_k
        pos = project(ctx, cutoff, it, balances, rates, mult, entities).assign(run_id=run_id, scenario_id=sid)
        if base_stats is None:
            base_stats = _group_stats(pos)
        positions.append(pos)
        detail[sid] = (it, {c: rates[c] * mult[c] for c in rates})
    positions = pd.concat(positions, ignore_index=True)
    scen = pd.DataFrame({"run_id": run_id, "scenario_id": spec.scenario_ids})

    input_hash = hashlib.sha256("|".join([
        frame_hash(lineage_items, "forecast_run_item"), frame_hash(lineage_bal, "forecast_run_balance_input"),
        frame_hash(lineage_fx, "forecast_run_fx_input"), frame_hash(scen, "forecast_run_scenario"),
    ]).encode()).hexdigest()
    run = {
        "run_id": run_id, "cutoff_date": cutoff, "knowledge_cutoff_ts": claimed_ts, "horizon_start": cutoff,
        "horizon_end": cutoff + (ctx.horizon - 1) * DAY, "horizon_days": ctx.horizon, "version": spec.version,
        "supersedes_run_id": spec.supersedes, "process": spec.process, "run_purpose": spec.purpose,
        "reporting_currency": ctx.reporting, "created_by": spec.created_by, "created_at": spec.created_at,
        "input_hash": input_hash, "result_hash": frame_hash(positions, "forecast_position"),
    }
    return RunResult(run, scen, lineage_items, lineage_bal, lineage_fx, positions,
                     pd.DataFrame(effects, columns=["run_id", "scenario_id", "assumption_id", "apply_order", "items_affected",
                                                    "delta_net_flow_usd", "delta_min_available_usd"]), detail)


def recreate_run(ctx: ForecastContext, run_row: pd.Series, scenario_ids: list[str]) -> RunResult:
    """Re-run a stored run from the data as of its claimed knowledge cutoff."""
    spec = RunSpec(cutoff=run_row["cutoff_date"], version=int(run_row["version"]), process=run_row["process"],
                   purpose=run_row["run_purpose"], created_by=run_row["created_by"], created_at=run_row["created_at"],
                   scenario_ids=scenario_ids, supersedes=run_row["supersedes_run_id"])
    return create_run(ctx, spec)
