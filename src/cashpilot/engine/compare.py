"""Actual versus forecast, with every unit of variance attributed to a driver.

For each run, scenario, entity and horizon week that has fully elapsed, the forecast net
external cash flow (F) is compared with the actual one (A). Internal transfers, FX conversions
between pool accounts and restricted accounts are excluded on both sides.

Actual cash is cut into *parts*: one per settlement allocation for invoices and bills, one per
posting otherwise. Each forecast item i (forecast in week w_f at the run's rate r_c) and each
actual part p (in week w_p, valued at its own day's rate r_p and, for comparison, at r_c) is
assigned as follows (docs/VARIANCE_METHOD.md):

  matched item     TIMING  +T_p in w_p and -T_p in w_f      (T_p = part at r_c)
                   AMOUNT  (sum T_p - F_i) in w_f
                   FX      (A_p - T_p) in w_p               (A_p = part at r_p)
  unrealised item  NOT_REALIZED -F_i (TIMING if it was paid after the compared window)
  flagged item     DATA_QUALITY -F_i and +A_p               (duplicates, mixed currency)
  run-rate item    RUN_RATE -F_i, small operating flows RUN_RATE +A_p
  other parts      NEW_AFTER_CUTOFF (item recorded after the cutoff), TIMING (item known but
                   forecast outside the window), UNFORECASTED (fees, interest)

Summed per week these terms equal A - F exactly, so the residual is always zero.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashpilot.core.money import to_usd
from cashpilot.dataset import Dataset
from cashpilot.engine.forecast import LIVE_TREATMENTS, ForecastContext, apply_assumption
from cashpilot.engine.fx import FxBook

INTERNAL = ("POOL_SWEEP", "POOL_FUNDING", "FX_CONVERSION", "ACCOUNT_CLOSURE")
OPERATING = ("OPERATING_RECEIPT", "OPERATING_PAYMENT")
DRIVERS = ["TIMING", "AMOUNT", "FX", "NEW_AFTER_CUTOFF", "UNFORECASTED", "NOT_REALIZED", "RUN_RATE", "DATA_QUALITY"]
COLUMN_OF = {"TIMING": "timing_usd", "AMOUNT": "amount_usd", "FX": "fx_usd", "NEW_AFTER_CUTOFF": "new_after_cutoff_usd",
             "UNFORECASTED": "unforecasted_usd", "NOT_REALIZED": "not_realized_usd", "RUN_RATE": "run_rate_usd",
             "DATA_QUALITY": "data_quality_usd"}


def actual_parts(ds: Dataset) -> pd.DataFrame:
    """External actual cash cut into parts, each linked to the forecast item it realises (if any)."""
    led = ds["ledger_entry"]
    restricted = led["account_id"].map(ds["bank_account"].set_index("account_id")["is_restricted"]).astype(bool)
    ext = led[~led["entry_type"].isin(INTERNAL) & ~restricted]
    cf = ds["cash_flow_forecast"]
    system = cf[cf["source_system"].isin(["AR_SUBLEDGER", "AP_SUBLEDGER"])]
    doc_item = pd.concat([system.dropna(subset=["receivable_id"]).set_index("receivable_id")["cf_id"],
                          system.dropna(subset=["payable_id"]).set_index("payable_id")["cf_id"]])
    al = ds["settlement_allocation"].merge(
        ext[["ledger_entry_id", "entity_id", "account_id", "currency", "posting_date", "amount"]],
        on="ledger_entry_id", suffixes=("_doc", ""))
    sign = np.where(al["amount"] > 0, 1, -1)
    same = al["currency_doc"] == al["currency"]
    al["part_amount"] = np.where(same, al["allocated_amount"].astype(np.int64) * sign, al["amount"].astype(np.int64))
    al["cf_id"] = al["receivable_id"].fillna(al["payable_id"]).map(doc_item)
    docs = al[["ledger_entry_id", "cf_id", "entity_id", "account_id", "currency", "posting_date", "part_amount"]].assign(kind="ITEM")
    rest = ext[~ext["ledger_entry_id"].isin(al["ledger_entry_id"])]
    linked = rest[rest["cf_id"].notna()].assign(kind="ITEM")
    ops = rest[rest["cf_id"].isna() & rest["entry_type"].isin(OPERATING)].assign(kind="OPS")
    other = rest[rest["cf_id"].isna() & ~rest["entry_type"].isin(OPERATING)].assign(kind="OTHER")
    cols = ["ledger_entry_id", "cf_id", "entity_id", "account_id", "currency", "posting_date", "amount", "kind"]
    singles = pd.concat([linked[cols], ops[cols], other[cols]]).rename(columns={"amount": "part_amount"})
    parts = pd.concat([docs, singles], ignore_index=True)
    parts["part_amount"] = parts["part_amount"].astype(np.int64)
    parts["item_recorded_at"] = parts["cf_id"].map(cf.set_index("cf_id")["recorded_at"])
    return parts.sort_values(["posting_date", "ledger_entry_id", "cf_id"], na_position="first").reset_index(drop=True)


def scenario_items(ctx: ForecastContext, run: pd.Series, lineage: pd.DataFrame, fx_inputs: pd.DataFrame, scenario_id: str):
    """Rebuild the scenario-adjusted items and effective rates of a stored run from its lineage."""
    cf = ctx.cf.set_index("cf_id")
    items = lineage.rename(columns={"expected_date_used": "date", "currency": "currency_used"}).copy()
    for col in ("entity_id", "direction", "flow_category", "risk_tier", "source_system"):
        items[col] = items["cf_id"].map(cf[col])
    items["amount_used"] = items["amount_used"].astype(np.int64)
    rates = {ctx.reporting: 1.0} | dict(zip(fx_inputs["currency_code"], fx_inputs["rate_used"]))
    mult = {c: 1.0 for c in rates}
    for asm in ctx.assumptions.get(scenario_id, []):
        apply_assumption(items, mult, asm, pd.Timestamp(run["cutoff_date"]))
    return items, {c: rates[c] * mult[c] for c in rates}


def _usd(amounts, currencies, rate_of) -> np.ndarray:
    out = np.zeros(len(amounts), dtype=np.int64)
    amounts = np.asarray(amounts, dtype=np.int64)
    currencies = np.asarray(currencies, dtype=object)
    for c in np.unique(currencies):
        m = currencies == c
        out[m] = to_usd(amounts[m], c, np.full(m.sum(), rate_of(c)))
    return out


def compare_run(ctx: ForecastContext, fx: FxBook, parts: pd.DataFrame, run: pd.Series, lineage: pd.DataFrame,
                fx_inputs: pd.DataFrame, scenario_id: str, dq_items: set, actuals_end) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff = pd.Timestamp(run["cutoff_date"])
    weeks = min(int(run["horizon_days"]) // 7, ((pd.Timestamp(actuals_end) - cutoff).days + 1) // 7)  # fully elapsed weeks
    if weeks <= 0:
        return pd.DataFrame(), pd.DataFrame()
    last_day = cutoff + pd.Timedelta(days=7 * weeks - 1)
    k_ts = pd.Timestamp(run["knowledge_cutoff_ts"])
    items, rates = scenario_items(ctx, run, lineage, fx_inputs, scenario_id)
    entities = set(ctx.entities.index[ctx.entities["effective_from"] <= cutoff])

    live_all = items[items["treatment"].isin(LIVE_TREATMENTS)]
    live = live_all[live_all["date"] <= last_day].copy()
    sign_f = np.where(live["direction"] == "INFLOW", 1, -1)
    live["F"] = _usd(live["amount_used"], live["currency_used"], lambda c: rates[c]) * sign_f
    live["week"] = (live["date"] - cutoff).dt.days // 7 + 1

    pw = parts[parts["entity_id"].isin(entities) & (parts["posting_date"] >= cutoff) & (parts["posting_date"] <= last_day)].copy()
    pw["week"] = (pw["posting_date"] - cutoff).dt.days // 7 + 1
    pw["T"] = _usd(pw["part_amount"], pw["currency"], lambda c: rates[c])
    actual_rate = np.ones(len(pw))
    for c, idx in pw.groupby("currency").groups.items():
        pos = pw.index.get_indexer(idx)
        _, r = fx.latest(c, pw.loc[idx, "posting_date"].to_numpy(dtype="datetime64[D]"))
        actual_rate[pos] = r
    pw["A"] = 0
    for c, idx in pw.groupby("currency").groups.items():
        pos = pw.index.get_indexer(idx)
        pw.loc[idx, "A"] = to_usd(pw.loc[idx, "part_amount"].to_numpy(), c, actual_rate[pos])
    pw["A"] = pw["A"].astype(np.int64)

    rows = []  # (entity, week, driver, cf_id, ledger_entry_id, amount)

    def emit(df, week_col, driver, amount_col, with_led=True):
        for e, w, cf_id, led_id, amt in zip(df["entity_id"], df[week_col], df["cf_id"],
                                            df["ledger_entry_id"] if with_led else [None] * len(df), df[amount_col]):
            if amt:
                rows.append((e, int(w), driver, cf_id, led_id, int(amt)))

    rr_items = live["flow_category"] == "OPERATING_RUN_RATE"
    dq = live["cf_id"].isin(dq_items) & ~rr_items
    normal = live[~rr_items & ~dq]
    live_ids, all_live_ids = set(normal["cf_id"]), set(live_all["cf_id"])

    # actual side
    is_ops, is_other = pw["kind"] == "OPS", pw["kind"] == "OTHER"
    is_dq = (pw["kind"] == "ITEM") & pw["cf_id"].isin(dq_items)
    matched = (pw["kind"] == "ITEM") & pw["cf_id"].isin(live_ids) & ~is_dq
    known_elsewhere = (pw["kind"] == "ITEM") & ~matched & ~is_dq & (pw["item_recorded_at"] < k_ts)
    new = (pw["kind"] == "ITEM") & ~matched & ~is_dq & ~known_elsewhere
    ops_agg = pw[is_ops].groupby(["entity_id", "week"])["A"].sum().reset_index().assign(cf_id=None, ledger_entry_id=None)
    emit(ops_agg, "week", "RUN_RATE", "A")
    emit(pw[is_other], "week", "UNFORECASTED", "A")
    emit(pw[is_dq], "week", "DATA_QUALITY", "A")
    emit(pw[new], "week", "NEW_AFTER_CUTOFF", "A")
    emit(pw[known_elsewhere], "week", "TIMING", "A")
    m = pw[matched].assign(FX=lambda d: d["A"] - d["T"])
    m["forecast_week"] = m["cf_id"].map(normal.set_index("cf_id")["week"])
    moved = m[m["week"] != m["forecast_week"]]  # timing only where cash landed in another week
    emit(moved, "week", "TIMING", "T")
    emit(m, "week", "FX", "FX")

    # forecast side
    emit(live[rr_items].assign(negF=lambda d: -d["F"]), "week", "RUN_RATE", "negF", with_led=False)
    emit(live[dq].assign(negF=lambda d: -d["F"]), "week", "DATA_QUALITY", "negF", with_led=False)
    t_sum = m.groupby("cf_id")["T"].sum()
    t_moved = moved.groupby("cf_id")["T"].sum()
    got = normal["cf_id"].isin(t_sum.index)
    hit = normal[got].assign(T=lambda d: d["cf_id"].map(t_sum), T_moved=lambda d: d["cf_id"].map(t_moved).fillna(0))
    emit(hit.assign(negT=lambda d: -d["T_moved"]), "week", "TIMING", "negT", with_led=False)
    emit(hit.assign(diff=lambda d: d["T"] - d["F"]), "week", "AMOUNT", "diff", with_led=False)
    miss = normal[~got]
    later = set(parts.loc[(parts["posting_date"] > last_day) & (parts["posting_date"] <= pd.Timestamp(actuals_end)), "cf_id"].dropna())
    slipped = miss["cf_id"].isin(later)
    emit(miss[slipped].assign(negF=lambda d: -d["F"]), "week", "TIMING", "negF", with_led=False)
    emit(miss[~slipped].assign(negF=lambda d: -d["F"]), "week", "NOT_REALIZED", "negF", with_led=False)

    attr = pd.DataFrame(rows, columns=["entity_id", "week_no", "driver", "cf_id", "ledger_entry_id", "amount_usd"])
    attr = attr.groupby(["entity_id", "week_no", "driver", "cf_id", "ledger_entry_id"], dropna=False, sort=True)["amount_usd"].sum().reset_index()
    attr = attr[attr["amount_usd"] != 0]

    grid = pd.MultiIndex.from_product([sorted(entities), range(1, weeks + 1)], names=["entity_id", "week_no"]).to_frame(index=False)
    f = live.groupby(["entity_id", "week"])["F"].sum().rename("forecast_net_usd")
    a = pw.groupby(["entity_id", "week"])["A"].sum().rename("actual_net_usd")
    comp = attr.pivot_table(index=["entity_id", "week_no"], columns="driver", values="amount_usd", aggfunc="sum", fill_value=0)
    out = grid.join(f, on=["entity_id", "week_no"]).join(a, on=["entity_id", "week_no"]).fillna(0)
    out = out.join(comp, on=["entity_id", "week_no"])
    for d in DRIVERS:
        out[COLUMN_OF[d]] = out[d].fillna(0).astype(np.int64) if d in out else 0
    out["forecast_net_usd"] = out["forecast_net_usd"].astype(np.int64)
    out["actual_net_usd"] = out["actual_net_usd"].astype(np.int64)
    out["variance_usd"] = out["actual_net_usd"] - out["forecast_net_usd"]
    out["residual_usd"] = out["variance_usd"] - out[[COLUMN_OF[d] for d in DRIVERS]].sum(axis=1)
    out["week_start"] = cutoff + pd.to_timedelta((out["week_no"] - 1) * 7, unit="D")
    out["week_end"] = out["week_start"] + pd.Timedelta(days=6)
    out = out.assign(run_id=run["run_id"], scenario_id=scenario_id)
    keep = ["run_id", "scenario_id", "entity_id", "week_no", "week_start", "week_end", "forecast_net_usd", "actual_net_usd",
            "variance_usd"] + [COLUMN_OF[d] for d in DRIVERS] + ["residual_usd"]
    return out[keep], attr.assign(run_id=run["run_id"], scenario_id=scenario_id)


def compare_all(ctx: ForecastContext, fx: FxBook, ds: Dataset, dq_items: set, actuals_end, attribution_scenario_prefix="SCN-BASE"):
    parts = actual_parts(ds)
    runs = ds["forecast_run"]
    lineage = ds["forecast_run_item"]
    fxin = ds["forecast_run_fx_input"]
    scen = ds["forecast_run_scenario"]
    l_by_run = dict(tuple(lineage.groupby("run_id")))
    fx_by_run = dict(tuple(fxin.groupby("run_id")))
    fva, attr = [], []
    for _, run in runs.sort_values("run_id").iterrows():
        for sid in scen.loc[scen["run_id"] == run["run_id"], "scenario_id"]:
            out, at = compare_run(ctx, fx, parts, run, l_by_run.get(run["run_id"], lineage.iloc[0:0]),
                                  fx_by_run.get(run["run_id"], fxin.iloc[0:0]), sid, dq_items, actuals_end)
            if len(out):
                fva.append(out)
                if sid.startswith(attribution_scenario_prefix):
                    attr.append(at)
    fva = pd.concat(fva, ignore_index=True) if fva else pd.DataFrame()
    attr = pd.concat(attr, ignore_index=True) if attr else pd.DataFrame()
    if len(attr):
        attr = attr.sort_values(["run_id", "entity_id", "week_no", "driver", "cf_id", "ledger_entry_id"], na_position="first").reset_index(drop=True)
        attr.insert(0, "attribution_id", [f"VA-{i + 1:09d}" for i in range(len(attr))])
    return fva, attr
