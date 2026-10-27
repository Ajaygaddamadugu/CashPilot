"""The dashboard's data layer: every figure must reconcile with the engine's own results.

These tests need no Streamlit. They use the processed starter dataset from the session fixture.
"""

import numpy as np
import pandas as pd
import pytest

from cashpilot.dashboard import data as D
from cashpilot.engine.explain import variance_breakdown
from cashpilot.evaluate.metrics import liquidity_outlook


@pytest.fixture(scope="module")
def bundle(pipeline, starter_cfg):
    _, _, final = pipeline
    return D.Bundle(final, starter_cfg)


@pytest.fixture(scope="module")
def live(bundle):
    return D.default_run(bundle.ds)


# ----------------------------------------------------------------- cash

def test_cash_overview_matches_the_entity_positions(bundle):
    on = D.default_date(bundle.ds)
    ov = D.cash_overview(bundle, on)
    e = bundle.ds["entity_cash_position"]
    raw = e[e["position_date"] == on].set_index("entity_id")
    assert set(ov["entity_id"]) == set(raw.index)
    for r in ov.itertuples():
        assert round(r.total_usd * 100) == raw.at[r.entity_id, "total_usd"]
        assert round((r.available_usd + r.restricted_usd) * 100) == raw.at[r.entity_id, "total_usd"]
        assert (r.buffer_status == "BELOW BUFFER") == (raw.at[r.entity_id, "headroom_usd"] < 0)
    g = D.group_summary(ov)
    assert g["total_usd"] == pytest.approx(raw["total_usd"].sum() / 100)
    assert g["headroom_usd"] == pytest.approx(g["available_usd"] - g["min_buffer_usd"])


def test_default_date_is_a_complete_date_and_incomplete_days_are_flagged(bundle):
    ds = bundle.ds
    assert D.default_date(ds) in D.complete_dates(ds)
    e = ds["entity_cash_position"]
    bad_days = set(e.loc[e["fx_status"] == "INCOMPLETE", "position_date"])
    assert bad_days and not (bad_days & set(D.complete_dates(ds)))
    hist = D.cash_history(bundle)
    assert set(hist.loc[hist["incomplete"], "position_date"]) == bad_days
    day = sorted(bad_days)[0]
    assert (D.cash_overview(bundle, day)["buffer_status"] == "INCOMPLETE FX").any()


def test_account_balances_convert_local_amounts_at_the_stated_rate(bundle):
    on = D.default_date(bundle.ds)
    a = D.account_balances(bundle, on)
    priced = a[(a["currency"] != "USD") & a["balance_usd"].notna()]
    assert len(priced)
    jpy = priced[priced["currency"] == "JPY"]
    assert len(jpy)
    assert (jpy["local_balance"] * jpy["rate_usd_per_unit"] - jpy["balance_usd"]).abs().max() < 0.02      # yen are whole units
    other = priced[priced["currency"] != "JPY"]
    assert (other["local_balance"] * other["rate_usd_per_unit"] - other["balance_usd"]).abs().max() < 0.02
    assert (a.loc[a["currency"] == "USD", "balance_usd"] == a.loc[a["currency"] == "USD", "local_balance"]).all()


def test_exposure_adds_up_and_never_mixes_local_currencies(bundle):
    on = D.default_date(bundle.ds)
    a = D.account_balances(bundle, on)
    ex = D.currency_exposure(bundle, on, shock_pct=-10)
    assert ex["usd_value"].sum() == pytest.approx(a["balance_usd"].sum())
    assert ex["usd_value"].sum() == pytest.approx(D.cash_overview(bundle, on)["total_usd"].sum(), abs=0.05)
    assert ex["share_of_total"].sum() == pytest.approx(1.0)
    usd_row = ex[ex["currency"] == "USD"].iloc[0]
    assert usd_row["usd_impact_of_shock"] == 0
    foreign = ex[ex["currency"] != "USD"]
    assert np.allclose(foreign["usd_impact_of_shock"], foreign["usd_value"] * -0.10)
    for r in ex.itertuples():                       # each currency's local total is the sum of that currency's accounts only
        assert r.local_total == pytest.approx(a.loc[a["currency"] == r.currency, "local_balance"].sum())
    m = D.exposure_matrix(bundle, on)
    assert m.drop(columns=["entity_id", "entity_name"]).to_numpy().sum() == pytest.approx(a["balance_usd"].sum())


def test_fx_gaps_list_exactly_the_missing_fixings(bundle):
    gaps = D.fx_gaps(bundle)
    assert len(gaps) and set(gaps["decision"]) <= {"USE_PREVIOUS_RATE", "BLOCK_CONVERSION"}
    rates = set(bundle.ds["currency_rate"]["rate_id"])
    assert not (set(gaps["record_id"]) & rates)     # a "missing" fixing is genuinely absent from the rate table
    hist = D.fx_history(bundle)
    assert {"EUR", "GBP", "INR", "JPY"} <= set(hist.columns)


# ------------------------------------------------------------ forecasts

def test_forecast_series_equals_the_sum_of_entity_positions(bundle, live):
    ds = bundle.ds
    sid = D.run_scenarios(ds, live)[0]
    s = D.forecast_series(ds, live, sid)
    p = ds["forecast_position"]
    p = p[(p["run_id"] == live) & (p["scenario_id"] == sid)]
    assert len(s) == int(ds["forecast_run"].set_index("run_id").at[live, "horizon_days"])
    day = p.groupby("position_date")["closing_available_usd"].sum() / 100
    assert np.allclose(s.set_index("position_date")["closing_available_usd"], day)
    assert np.allclose(s["closing_available_usd"], s["opening_usd"] + s["inflows_usd"] - s["outflows_usd"])
    ent = p["entity_id"].iloc[0]
    one = D.forecast_series(ds, live, sid, ent)
    assert np.allclose(one["closing_available_usd"], p[p["entity_id"] == ent].sort_values("position_date")["closing_available_usd"] / 100)


def test_weekly_view_adds_up_the_daily_series(bundle, live):
    s = D.forecast_series(bundle.ds, live, D.run_scenarios(bundle.ds, live)[0])
    w = D.weekly_view(s)
    assert w["inflows_usd"].sum() == pytest.approx(s["inflows_usd"].sum())
    assert w["outflows_usd"].sum() == pytest.approx(s["outflows_usd"].sum())
    assert w["closing_available_usd"].iloc[-1] == pytest.approx(s["closing_available_usd"].iloc[-1])
    assert w["lowest_available_usd"].min() == pytest.approx(s["closing_available_usd"].min())
    assert w["week_no"].tolist() == list(range(1, len(w) + 1))


def test_scenario_comparison_matches_the_engines_outlook_and_assumption_effects_telescope(bundle, live):
    ds = bundle.ds
    comp = D.scenario_comparison(ds, live)
    outlook = liquidity_outlook(ds, live)["scenarios"]
    assert comp["scenario_id"].tolist() == D.run_scenarios(ds, live)
    for r in comp.itertuples():
        assert r.lowest_available_usd == outlook[r.scenario_id]["lowest_available_usd"]
    assert comp["lowest_vs_base_usd"].iloc[0] == 0 and (comp["lowest_vs_base_usd"].iloc[1:] <= 0).all()   # stress/delay never improve the low point
    eff = D.assumption_table(ds, live)
    for sid in comp["scenario_id"].iloc[1:]:
        base_net = (ds["forecast_position"].query("run_id == @live and scenario_id == @sid")[["inflows_usd", "outflows_usd"]].sum())
        base_id = comp["scenario_id"].iloc[0]
        b_net = (ds["forecast_position"].query("run_id == @live and scenario_id == @base_id")[["inflows_usd", "outflows_usd"]].sum())
        diff = ((base_net["inflows_usd"] - base_net["outflows_usd"]) - (b_net["inflows_usd"] - b_net["outflows_usd"])) / 100
        assert eff.loc[eff["scenario_id"] == sid, "delta_net_flow_usd"].sum() == pytest.approx(diff, abs=0.01)


def test_cashflow_items_reproduce_the_engines_daily_flows_exactly(bundle, live):
    """The drivers shown to a user are the same cash the projection uses, in every scenario."""
    ds = bundle.ds
    p = ds["forecast_position"]
    for sid in D.run_scenarios(ds, live):
        items = D.cashflow_items(bundle, live, sid)
        eng = p[(p["run_id"] == live) & (p["scenario_id"] == sid)]
        mine = items[items["in_horizon"]]
        for direction, col in (("INFLOW", "inflows_usd"), ("OUTFLOW", "outflows_usd")):
            got = mine[mine["direction"] == direction].groupby(["entity_id", "date"])["usd"].sum()
            want = (eng.groupby(["entity_id", "position_date"])[col].sum() / 100)
            want = want[want != 0]
            assert len(got) == len(want)
            assert np.allclose(got.sort_index().to_numpy(), want.sort_index().to_numpy(), atol=0.011), (sid, direction)


def test_delayed_scenario_moves_dates_and_never_drops_the_item_list(bundle, live):
    ds = bundle.ds
    base_id, delay_id = D.run_scenarios(ds, live)[:2]
    base, delay = D.cashflow_items(bundle, live, base_id), D.cashflow_items(bundle, live, delay_id)
    assert len(base) == len(delay) and (base["cf_id"].to_numpy() == delay["cf_id"].to_numpy()).all()
    assert (base["shifted_days"].fillna(0) == 0).all()                                    # base moves nothing
    moved = delay[delay["shifted_days"].fillna(0) != 0]
    assert len(moved) and (moved["direction"] == "INFLOW").all() and (moved["flow_category"] == "AR_COLLECTION").all()
    assert (moved["shifted_days"] > 0).all() and set(moved["risk_tier"]) <= {"B", "C", "D"}


def test_run_diff_explains_every_change_with_a_reason(bundle):
    ds = bundle.ds
    runs = D.run_catalog(ds)
    a, b = runs["run_id"].iloc[-3], runs["run_id"].iloc[-1]
    diff = D.run_diff(bundle, a, b)
    items = diff["items"]
    assert len(items) and items["reason"].notna().all() and (items["reason"] != "").all()
    assert diff["summary"]["items_added"] == (items["change_type"] == "ADDED").sum()
    assert items["change_usd"].abs().is_monotonic_decreasing
    added = items[items["change_type"] == "ADDED"]
    assert (added["net_usd_a"] == 0).all() and (added["reason"].isin(["NEW_AFTER_PREVIOUS_CUTOFF", "ENTERED_THE_HORIZON"])).all()
    same = D.run_diff(bundle, b, b)
    assert same["items"].empty and same["summary"]["net_item_effect_usd"] == 0           # a run never differs from itself


# ----------------------------------------------------- exceptions, accuracy

def test_every_exception_has_a_rule_decision_history_and_evidence(bundle):
    exc = D.exceptions_table(bundle)
    assert len(exc) == len(bundle.ds["exception"])
    for et in exc["exception_type"].unique():
        row = exc[exc["exception_type"] == et].iloc[0]
        t = D.exception_trace(bundle, row["exception_id"])
        assert t["rule_text"] and t["decision_text"] and len(t["events"]) >= 2 and t["evidence"], et
        assert t["events"]["event_type"].iloc[0] == "RAISED"


def test_leakage_trace_shows_inputs_recorded_after_the_cutoff(bundle):
    exc = D.exceptions_table(bundle)
    leak = exc[exc["exception_type"] == "LOOKAHEAD_LEAKAGE"].iloc[0]
    t = D.exception_trace(bundle, leak["exception_id"])
    late_items = t["evidence"][0][1]
    assert len(late_items) > 0 and (late_items["minutes_after_cutoff"] >= 0).all()
    superseding = [df for title, df in t["evidence"] if title == "Runs that supersede it"][0]
    assert len(superseding) == 1 and superseding["status_at_end"].iloc[0] == "APPROVED"


def test_balance_break_trace_reconciles_bank_and_book(bundle):
    exc = D.exceptions_table(bundle)
    br = exc[exc["exception_type"] == "BALANCE_BREAK"].iloc[0]
    t = D.exception_trace(bundle, br["exception_id"])
    m = t["evidence"][0][1].set_index("measure")["amount"]
    assert m["difference (bank - book)"] == pytest.approx(m["bank movement"] - m["booked ledger movement"])
    assert abs(m["difference (bank - book)"]) > 0                      # a real break, not a formatting artefact


def test_variance_breakdown_drivers_sum_to_the_variance(bundle):
    ds = bundle.ds
    fva = ds["forecast_vs_actual"]
    row = fva[fva["scenario_id"].str.startswith("SCN-BASE") & (fva["variance_usd"].abs() > 0)].iloc[0]
    br = variance_breakdown(ds, row["run_id"], row["entity_id"], int(row["week_no"]), top=2)
    assert sum(d["total_usd"] for d in br["drivers"]) == br["variance_usd"] == br["actual_usd"] - br["forecast_usd"]
    assert br["residual_usd"] == 0 and all(len(d["top"]) <= 2 for d in br["drivers"])
    assert variance_breakdown(ds, "FCAST-2026-10-01-001", row["entity_id"], 1) is None   # nothing has elapsed for the live run


def test_forecast_vs_actual_view_matches_the_stored_table(bundle):
    ds = bundle.ds
    fva = ds["forecast_vs_actual"]
    run = fva["run_id"].iloc[0]
    sid = fva["scenario_id"].iloc[0]
    v = D.forecast_vs_actual(ds, run, sid)
    raw = fva[(fva["run_id"] == run) & (fva["scenario_id"] == sid)]
    assert v["variance_usd"].sum() == pytest.approx(raw["variance_usd"].sum() / 100)
    assert v["residual_usd"].abs().sum() == 0


def test_evaluation_keeps_ground_truth_out_of_the_dataset_views(bundle):
    ev = D.evaluation(bundle)
    assert "detection" in ev and ev["detection"]["negative_controls_flagged"] == 0
    for df in bundle.ds.tables.values():
        assert not {"label", "issue_type", "injection_rule"} & set(df.columns)


# ------------------------------------------------------ audit, caching, files

def test_reproducibility_check_passes_for_clean_runs_and_fails_for_the_leaky_one(bundle, pipeline):
    generated, _, _ = pipeline
    ds = bundle.ds
    assert D.verify_reproducibility(bundle, D.default_run(ds))["reproduced"]
    leaky = generated.ground_truth.query("issue_type == 'LOOKAHEAD_LEAKAGE'")["record_id"].iloc[0]
    v = D.verify_reproducibility(bundle, leaky)
    assert not v["reproduced"] and not v["result_hash_matches"]


def test_audit_trail_lists_lifecycle_and_lineage(bundle, live):
    t = D.audit_trail(bundle.ds, live)
    assert t["events"]["event_type"].tolist() == ["CREATED", "COMPLETED", "SUBMITTED", "APPROVED"]
    assert t["lineage"]["items"].sum() == (bundle.ds["forecast_run_item"]["run_id"] == live).sum()
    assert t["run"]["input_hash"] and t["run"]["result_hash"]


def test_dataset_signature_changes_when_the_data_changes(tmp_path):
    root = tmp_path / "ds"
    (root / "csv").mkdir(parents=True)
    for rel in D.SIGNATURE_FILES:
        (root / rel).write_text("a", encoding="utf-8")
    first = D.dataset_signature(root)
    assert D.dataset_signature(root) == first
    (root / "csv" / "forecast_run.csv").write_text("changed", encoding="utf-8")
    assert D.dataset_signature(root) != first                       # a cached bundle would be rebuilt, never served stale
    assert D.discover_datasets(tmp_path) == []                       # needs generation_config.json and csv/forecast_run.csv


def test_money_helpers_respect_currency_precision():
    a = pd.Series([123456, 123456], dtype="Int64")
    assert D.major(a, pd.Series(["USD", "JPY"])).tolist() == [1234.56, 123456.0]
    assert np.isnan(D.major(pd.Series([pd.NA], dtype="Int64"), pd.Series(["EUR"])).iloc[0])
    assert D.to_csv_bytes(pd.DataFrame({"x": [1]})) == b"x\n1\n"
