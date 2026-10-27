"""Input -> calculation -> result explanations: every number must come from the engine's own results and add up (no Streamlit needed)."""

import pandas as pd
import pytest

from cashpilot.dashboard import charts as C
from cashpilot.dashboard import data as D
from cashpilot.dashboard import insights as I


@pytest.fixture(scope="module")
def bundle(pipeline, starter_cfg):
    _, _, final = pipeline
    return D.Bundle(final, starter_cfg)


@pytest.fixture(scope="module")
def live(bundle):
    ds = bundle.ds
    run = D.default_run(ds)
    scenario = D.run_scenarios(ds, run)[0]
    return run, scenario, D.cashflow_items(bundle, run, scenario)


# ------------------------------------------------------------------ cash overview

def test_headroom_insight_uses_the_summary_figures_and_adds_up(bundle):
    g = D.group_summary(D.cash_overview(bundle, D.default_date(bundle.ds)))
    ins = I.headroom_insight(g, "USD")
    assert g["total_usd"] - g["restricted_usd"] == pytest.approx(g["available_usd"])
    assert g["available_usd"] - g["min_buffer_usd"] == pytest.approx(g["headroom_usd"])
    assert f"{g['headroom_usd']:,.0f}" in ins["result"] and f"{g['available_usd']:,.0f}" in ins["calculation"][1]
    assert ins["level"] == ("success" if g["headroom_usd"] >= 0 else "error")


def test_liquidity_status_follows_the_documented_buffer_rule():
    ok = {"entities": 5, "entities_below_buffer": 0, "entities_incomplete_fx": 0, "headroom_usd": 1000.0}
    assert I.liquidity_status(ok, "USD")["level"] == "success"
    low = I.liquidity_status({**ok, "entities_below_buffer": 2}, "USD")
    assert low["level"] == "error" and low["headline"].startswith("2 of 5")
    assert I.liquidity_status({**ok, "entities_incomplete_fx": 1}, "USD")["level"] == "warning"       # missing FX: not claimed as fine


# ------------------------------------------------------------------ forecast

def test_forecast_headline_matches_the_stored_projection(bundle, live):
    run, scenario, _ = live
    series = D.forecast_series(bundle.ds, run, scenario)
    head = I.forecast_headline(series)
    assert head["lowest_usd"] == series["closing_available_usd"].min()
    assert series.set_index("position_date").at[head["lowest_on"], "closing_available_usd"] == head["lowest_usd"]
    assert head["days_below"] == int((series["headroom_usd"] < 0).sum())


def test_every_breach_is_explained_by_items_that_add_up_to_the_stored_projection(bundle):
    ds = bundle.ds
    explained = 0
    for run in D.run_catalog(ds)["run_id"].tolist()[-3:]:
        for scenario in D.run_scenarios(ds, run):
            items = D.cashflow_items(bundle, run, scenario)
            for _, breach in D.entity_breaches(ds, run, scenario).iterrows():
                story = I.breach_story(ds, items, run, scenario, breach["entity_id"], breach["first_breach"], "USD")
                assert story["reconciles"], (run, scenario, breach["entity_id"])
                assert story["opening"] + story["receipts"] - story["payments"] == pytest.approx(story["projected"], abs=0.01)
                assert story["gap"] == pytest.approx(story["projected"] - story["buffer"]) and story["gap"] < 0       # it really is a shortfall
                assert len(story["biggest"]) and (story["biggest"]["date"] <= pd.Timestamp(breach["first_breach"])).all()
                explained += 1
    assert explained >= 3


# ------------------------------------------------------------------ cash-flow drivers

def test_cash_bridge_adds_the_flows_to_the_stored_closing_cash_for_every_scenario_and_entity(bundle, live):
    run, _, _ = live
    ds = bundle.ds
    for scenario in D.run_scenarios(ds, run):
        items = D.cashflow_items(bundle, run, scenario)
        for entity in (None, *ds["legal_entity"]["entity_id"].tolist()[:3]):
            series = D.forecast_series(ds, run, scenario, entity)
            bridge = I.cash_bridge(items, series, entity)
            assert bridge.attrs["reconciles"], (scenario, entity)
            assert bridge["amount"].iloc[0] == series["opening_usd"].iloc[0] and bridge["amount"].iloc[-1] == series["closing_available_usd"].iloc[-1]
            assert bridge["amount"].iloc[1:-1].sum() + bridge["amount"].iloc[0] == pytest.approx(bridge["amount"].iloc[-1], abs=0.01)


def test_bridge_steps_are_labelled_with_plain_names_and_each_bar_can_be_inspected(bundle, live):
    run, scenario, items = live
    bridge = I.cash_bridge(items, D.forecast_series(bundle.ds, run, scenario))
    steps = bridge[bridge["code"] != ""]
    assert set(steps["code"]) <= set(items["flow_category"]) and "_" not in " ".join(steps["step"])
    for _, step in steps.iterrows():                         # the transactions behind a bar add up to the bar
        behind = items[items["in_horizon"] & (items["flow_category"] == step["code"])]
        assert behind["signed_usd"].sum() == pytest.approx(step["amount"], abs=0.01)
    ins = I.bridge_insight(bridge, "USD")
    assert f"{bridge['amount'].iloc[-1]:,.0f}" in ins["result"]


# ------------------------------------------------------------------ accounts and currencies

def test_account_conversion_shows_balance_times_rate_and_the_effect_of_a_move(bundle):
    acc = D.account_balances(bundle, D.default_date(bundle.ds))
    foreign = acc[(acc["currency"] != "USD") & acc["balance_usd"].notna()].iloc[0]
    ins = I.account_conversion(foreign, -10, "USD")
    assert foreign["local_balance"] * foreign["rate_usd_per_unit"] == pytest.approx(foreign["balance_usd"], abs=0.01)
    assert f"{foreign['balance_usd']:,.2f}" in ins["calculation"][0] and f"{foreign['rate_usd_per_unit']:,.4f}" in ins["calculation"][0]
    assert f"{foreign['balance_usd'] * 0.9:,.2f}" in ins["result"]
    usd_account = acc[acc["currency"] == "USD"].iloc[0]
    assert "reporting currency" in " ".join(v for _, v in I.account_conversion(usd_account, -10, "USD")["inputs"])


def test_account_with_a_missing_rate_is_not_converted_or_guessed():
    row = pd.Series({"currency": "EUR", "local_balance": 1000.0, "rate_usd_per_unit": float("nan"), "balance_usd": float("nan"), "fx_status": "MISSING", "rate_date": pd.NaT})
    ins = I.account_conversion(row, -10, "USD")
    assert "not available" in ins["result"] and ins["level"] == "warning" and "never guessed" in ins["calculation"][0]


def test_fx_move_insight_matches_the_exposure_table_and_can_target_one_currency(bundle):
    on = D.default_date(bundle.ds)
    everything = D.currency_exposure(bundle, on, -10)
    only_eur = D.currency_exposure(bundle, on, -10, ["EUR"])
    eur = everything.set_index("currency").at["EUR", "usd_value"]
    assert only_eur["usd_impact_of_shock"].sum() == pytest.approx(-eur * 0.10)
    assert only_eur.set_index("currency").at["JPY", "usd_impact_of_shock"] == 0
    assert everything["usd_impact_of_shock"].sum() == pytest.approx(-0.10 * everything.loc[everything["currency"] != "USD", "usd_value"].sum())
    ins = I.fx_move_insight(only_eur, -10, "USD", ["EUR"])
    assert f"{only_eur['usd_impact_of_shock'].sum():,.0f}" in ins["calculation"][0] and "not a forecast" in ins["result"]


# ------------------------------------------------------------------ actual vs forecast

def test_variance_insight_explains_the_whole_difference(bundle):
    ds = bundle.ds
    run = D.default_accuracy_run(ds)
    scenario = D.run_scenarios(ds, run)[0]
    fva = D.forecast_vs_actual(ds, run, scenario)
    for _, row in fva.iterrows():
        ins = I.variance_insight(row, "USD")
        parts = row["timing_usd"] + row["amount_usd"] + row["fx_usd"] + sum(row[c] for c in I.OTHER_DRIVERS)
        assert parts == pytest.approx(row["variance_usd"], abs=0.01) and row["actual_net_usd"] - row["forecast_net_usd"] == pytest.approx(row["variance_usd"], abs=0.01)
        assert f"{row['variance_usd']:,.0f}" in ins["calculation"][0]
    totals = I.variance_totals(fva)
    assert totals["timing"] + totals["amount"] + totals["fx"] + totals["other"] == pytest.approx(totals["variance"], abs=0.05)


# ------------------------------------------------------------------ exceptions

def test_exception_list_is_plain_and_keeps_the_affected_record(bundle):
    exc = D.exceptions_table(bundle)
    plain = I.exception_list(exc)
    assert len(plain) == len(exc) and list(plain.columns) == ["Severity", "Problem", "Company", "Affected record", "Status", "impact_usd"]
    assert not plain["Problem"].str.contains("_").any() and not plain["Severity"].str.isupper().any()
    assert plain["Affected record"].str.contains(exc["record_id"].iloc[0]).iloc[0]
    assert set(plain["Status"].str.split(" ", n=1).str[1]) <= {"Resolved", "Waived", "Open", "Assigned", "Escalated", "Raised"}


# ------------------------------------------------------------------ charts

def visible_titles(node) -> list[str]:
    """Every axis, legend and tooltip title in a chart specification: what a person can read on screen."""
    found = []
    if isinstance(node, dict):
        found += [node["title"]] if isinstance(node.get("title"), str) else []
        for value in node.values():
            found += visible_titles(value)
    elif isinstance(node, list):
        for value in node:
            found += visible_titles(value)
    return found


def test_new_charts_validate_and_carry_titles_and_formats():
    steps = pd.DataFrame({"step": ["Cash at the start", "Customer receipts", "Payroll", "Cash after 13 weeks"], "amount": [100.0, 50.0, -30.0, 120.0],
                          "start": [0.0, 100.0, 150.0, 0.0], "end": [100.0, 150.0, 120.0, 120.0], "kind": ["Cash at start", "Increase", "Decrease", "Cash at end"]})
    weeks = pd.DataFrame({"week_no": [1, 2], "week_start": pd.to_datetime(["2026-01-01", "2026-01-08"]), "closing_available_usd": [5.0, 3.0],
                          "lowest_available_usd": [4.0, 2.0], "min_buffer_usd": [3.5, 3.5], "days_below_buffer": [0, 2]})
    days = pd.DataFrame({"position_date": pd.date_range("2026-01-01", periods=3), "cash": [5.0, 3.0, 4.0], "buffer": [3.5] * 3})
    expo = pd.DataFrame({"currency": ["EUR", "USD"], "usd_value": [3.0, 4.0], "share": [43.0, 57.0], "local_total": [2.9, 4.0]})
    fva = pd.DataFrame({"week_no": [1, 2], "Forecast net cash": [1.0, 2.0], "Actual net cash": [1.5, 1.0]})
    for chart in (C.waterfall(steps, "Cash (USD)"), C.weekly_cash_chart(weeks, "Cash (USD)"), C.shortfall_chart(days, "position_date", "cash", "buffer", "Cash (USD)"),
                  C.exposure_chart(expo, "Value (USD)"), C.grouped_bar(fva, "week_no", ["Forecast net cash", "Actual net cash"], "Net cash (USD)", "Week")):
        titles = visible_titles(chart.to_dict())
        assert titles and not (set(titles) & {"value", "color", "variable", "position_date", "week_no", "usd_value", "_series", "_amount", "cash", "buffer"}), titles
    labels = C.waterfall(steps, "Cash (USD)").to_dict()["layer"][1]["encoding"]["text"]
    assert labels["field"] == "label"
    assert C._short(22_607_237.5, True) == "+22.6M" and C._short(-870_217.4, True) == "-870k" and C._short(36_034_844.1, False) == "36.0M"
