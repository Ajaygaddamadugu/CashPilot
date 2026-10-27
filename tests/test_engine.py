"""Engine acceptance checks on the clean starter baseline.

* Daily balances reconcile (roll-forward, ledger, entity consolidation).
* Scenarios differ only by documented assumptions.
* Forecasts are reproducible and strictly as-of their knowledge cutoff.
"""

import numpy as np
import pandas as pd
import pytest

from cashpilot.dataset import Dataset
from cashpilot.engine.forecast import ForecastContext, RunSpec, apply_assumption, create_run, project
from cashpilot.engine.positions import daily_cash_positions, entity_cash_positions, fx_book

CUTOFF = pd.Timestamp("2026-03-05")


@pytest.fixture(scope="module")
def engine(baseline, starter_cfg):
    ds, _ = baseline
    fx = fx_book(ds, starter_cfg.policy)
    ctx = ForecastContext(ds, starter_cfg, fx)
    spec = RunSpec(CUTOFF, 1, "CASHPILOT", "SCHEDULED", "USR-0003", CUTOFF + pd.Timedelta(hours=8, minutes=15),
                   ctx.effective_scenarios(CUTOFF))
    return ds, fx, ctx, spec, create_run(ctx, spec)


def test_daily_positions_roll_forward_and_match_the_ledger(baseline, starter_cfg):
    ds, _ = baseline
    fx = fx_book(ds, starter_cfg.policy)
    daily = daily_cash_positions(ds, starter_cfg.actuals_end, fx)
    assert (daily["closing_balance"] == daily["opening_balance"] + daily["inflows"] - daily["outflows"]).all()
    d = daily.sort_values(["account_id", "position_date"])
    prev = d.groupby("account_id")["closing_balance"].shift()
    assert (d["opening_balance"][prev.notna()] == prev[prev.notna()]).all()
    # closing balance = opening balance + every ledger posting up to that day
    last = d.groupby("account_id").tail(1).set_index("account_id")["closing_balance"]
    acc = ds["bank_account"].set_index("account_id")
    total = ds["ledger_entry"].groupby("account_id")["amount"].sum()
    assert (last == acc.loc[last.index, "opening_balance"] + total.reindex(last.index, fill_value=0)).all()
    # the clean baseline has no bank/book differences
    assert (daily["bank_minus_book"].dropna() == 0).all()
    ent = entity_cash_positions(ds, daily, fx)
    assert (ent["available_usd"] + ent["restricted_usd"] == ent["total_usd"]).all()
    summed = daily.groupby(["entity_id", "position_date"])["closing_balance_usd"].sum().astype("int64")
    assert (ent.set_index(["entity_id", "position_date"])["total_usd"] == summed.reindex(ent.set_index(["entity_id", "position_date"]).index)).all()


def test_forecast_positions_roll_forward_over_the_horizon(engine):
    *_, run = engine
    p = run.positions
    assert (p["closing_available_usd"] == p["opening_available_usd"] + p["inflows_usd"] - p["outflows_usd"]).all()
    assert (p.groupby(["scenario_id", "entity_id"]).size() == run.run["horizon_days"]).all()
    assert p["position_date"].min() == CUTOFF and p["position_date"].max() == run.run["horizon_end"]


def test_scenario_without_its_assumptions_equals_base(engine):
    """No hidden scenario logic: strip a scenario's assumptions and it becomes the base case."""
    ds, fx, ctx, spec, run = engine
    stripped = ForecastContext(ds, ctx.cfg, fx)
    for sid in spec.scenario_ids[1:]:
        stripped.assumptions[sid] = []
    rebuilt = create_run(stripped, spec).positions
    base = rebuilt[rebuilt["scenario_id"] == spec.scenario_ids[0]].drop(columns="scenario_id").reset_index(drop=True)
    for sid in spec.scenario_ids[1:]:
        other = rebuilt[rebuilt["scenario_id"] == sid].drop(columns="scenario_id").reset_index(drop=True)
        assert other.equals(base), sid
    # ...and with the assumptions in place the scenarios do differ
    real = run.positions
    assert not real[real["scenario_id"] == spec.scenario_ids[-1]]["closing_available_usd"].reset_index(drop=True).equals(
        base["closing_available_usd"])


def test_assumption_effects_add_up_to_the_scenario_difference(engine):
    *_, spec, run = engine
    p = run.positions
    def stats(sid):
        s = p[p["scenario_id"] == sid]
        return s["inflows_usd"].sum() - s["outflows_usd"].sum(), s.groupby("position_date")["closing_available_usd"].sum().min()
    base_net, base_min = stats(spec.scenario_ids[0])
    for sid in spec.scenario_ids[1:]:
        net, mn = stats(sid)
        eff = run.effects[run.effects["scenario_id"] == sid]
        assert eff["delta_net_flow_usd"].sum() == net - base_net
        assert eff["delta_min_available_usd"].sum() == mn - base_min


def test_every_changed_item_matches_a_documented_assumption(engine):
    ds, fx, ctx, spec, run = engine
    base_items, _ = run.detail[spec.scenario_ids[0]]
    for sid in spec.scenario_ids[1:]:
        items, _ = run.detail[sid]
        moved = items["date"].ne(base_items["date"]) & items["date"].notna()
        rescaled = items["amount_used"].ne(base_items["amount_used"])
        asms = ctx.assumptions[sid]
        delay_tiers = {a["filter_value"] for a in asms if a["parameter"] == "AR_DELAY_DAYS" and float(a["value"]) != 0}
        rate_tiers = {a["filter_value"] for a in asms if a["parameter"] == "AR_COLLECTION_RATE"}
        ap_shift = any(a["parameter"] == "AP_TIMING_SHIFT_DAYS" for a in asms)
        rr = any(a["parameter"] == "RUN_RATE_INFLOW_FACTOR" for a in asms)
        ar = (items["flow_category"] == "AR_COLLECTION") & (items["direction"] == "INFLOW")
        ap = (items["flow_category"] == "AP_PAYMENT") & (items["direction"] == "OUTFLOW")
        explained_move = (ar & items["risk_tier"].isin(delay_tiers)) | (ap & ap_shift)
        explained_amount = (ar & items["risk_tier"].isin(rate_tiers)) | (
            rr & (items["flow_category"] == "OPERATING_RUN_RATE") & (items["direction"] == "INFLOW"))
        assert not (moved & ~explained_move).any(), sid
        assert not (rescaled & ~explained_amount).any(), sid


def test_rerunning_a_stored_run_reproduces_its_hashes(engine):
    ds, fx, ctx, spec, run = engine
    again = create_run(ForecastContext(ds, ctx.cfg, fx), spec)
    assert again.run["input_hash"] == run.run["input_hash"]
    assert again.run["result_hash"] == run.run["result_hash"]


def test_data_recorded_after_the_cutoff_does_not_change_an_old_run(engine):
    ds, fx, ctx, spec, run = engine
    later = Dataset({k: v.copy() for k, v in ds.tables.items()})
    cf = later["cash_flow_forecast"]
    extra = cf.iloc[[0]].copy()
    extra["cf_id"] = "CF-2026-999999"
    extra["recorded_at"] = CUTOFF + pd.Timedelta(days=2)
    extra["expected_date"] = CUTOFF + pd.Timedelta(days=10)
    later["cash_flow_forecast"] = pd.concat([cf, extra], ignore_index=True)
    rev = later["cf_revision"]
    bump = rev.iloc[[0]].copy()
    bump["revision_id"], bump["cf_id"], bump["revision_no"] = "CFR-2026-9999999", cf.iloc[0]["cf_id"], 99
    bump["recorded_at"] = CUTOFF + pd.Timedelta(hours=9)  # one hour after the knowledge cutoff
    later["cf_revision"] = pd.concat([rev, bump], ignore_index=True)
    again = create_run(ForecastContext(later, ctx.cfg, fx), spec)
    assert again.run["input_hash"] == run.run["input_hash"]
    assert again.run["result_hash"] == run.run["result_hash"]


def test_lineage_only_contains_records_known_before_the_cutoff(engine):
    *_, run = engine
    k = run.run["knowledge_cutoff_ts"]
    assert (run.items["input_recorded_at"] < k).all()
    assert (run.balances["statement_date"] < CUTOFF).all()
    assert (run.fx["rate_date"] < CUTOFF).all()


def test_the_same_cash_flow_is_never_counted_twice_in_a_cashpilot_run(pipeline, starter_cfg):
    generated, _, _ = pipeline
    ctx = ForecastContext(generated, starter_cfg, fx_book(generated, starter_cfg.policy))
    gt = generated.ground_truth
    dups = gt[(gt["issue_type"] == "DUPLICATE_CASH_FLOW") & (gt["sub_type"] == "EXACT_REFERENCE")]["record_id"]
    cf = generated["cash_flow_forecast"].set_index("cf_id")
    cand = cf.loc[dups].sort_values("recorded_at")
    pick = cand.index[0]
    cutoff = cand.loc[pick, "recorded_at"].normalize() + pd.Timedelta(days=1)     # the day after the duplicate was keyed in
    scenarios = ["SCN-BASE-V01"]
    legacy = create_run(ctx, RunSpec(cutoff, 1, "LEGACY", "SCHEDULED", "USR-0003", cutoff + pd.Timedelta(hours=9), scenarios))
    gated = create_run(ctx, RunSpec(cutoff, 1, "CASHPILOT", "SCHEDULED", "USR-0003", cutoff + pd.Timedelta(hours=9), scenarios))
    old = legacy.items.set_index("cf_id").loc[pick]
    new = gated.items.set_index("cf_id").loc[pick]
    assert old["treatment"] in ("INCLUDED", "OVERDUE_ROLLED") and old["amount_used"] > 0       # the legacy run double counts it
    assert new["treatment"] == "EXCLUDED_DUPLICATE" and new["amount_used"] == 0                # the gate removes it
    entity = cand.loc[pick, "entity_id"]
    flow = "inflows_usd" if cand.loc[pick, "direction"] == "INFLOW" else "outflows_usd"
    total = lambda r: r.positions.loc[r.positions["entity_id"] == entity, flow].sum()
    assert total(legacy) > total(gated)                                                        # and it shows in the projection
