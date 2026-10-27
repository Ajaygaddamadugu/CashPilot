"""The command-line interface: results, permissions, four-eyes approval and failure behavior."""

import re
import shutil

import pandas as pd
import pytest

from cashpilot.cli import main
from cashpilot.export.bundle import write_bundle
from cashpilot.export.docs import render_data_dictionary
from cashpilot.schema import load_schema


@pytest.fixture(scope="module")
def template(pipeline, starter_cfg, tmp_path_factory):
    _, _, final = pipeline
    out = tmp_path_factory.mktemp("cli-template")
    write_bundle(final, starter_cfg, out, ("csv",))
    return out, final


@pytest.fixture()
def data(template, tmp_path):
    """A private copy: commands that act as a user rewrite the CSV tables."""
    dest = tmp_path / "bundle"
    shutil.copytree(template[0], dest)
    return dest


def users(final, role):
    return final["app_user"].query("role == @role")["user_id"].tolist()


def run(args, capsys):
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def csv(data, name):
    return pd.read_csv(data / "csv" / f"{name}.csv", dtype=str, keep_default_na=False)


# ------------------------------------------------------------------- read-only

def test_exceptions_lists_and_filters(data, capsys):
    code, out, _ = run(["exceptions", "--data", str(data), "--type", "LOOKAHEAD_LEAKAGE"], capsys)
    assert code == 0 and "R-LEAK-001" in out and "(1 exception)" in out
    code, out, _ = run(["exceptions", "--data", str(data), "--status", "OPEN"], capsys)
    assert code == 0 and "(0 exceptions)" in out        # the playbook leaves nothing open


def test_explain_drivers_add_up_to_the_printed_variance(template, data, capsys):
    _, final = template
    fva = final["forecast_vs_actual"]
    pick = fva[fva["scenario_id"].str.startswith("SCN-BASE") & (fva["variance_usd"].abs() > 100_000)].iloc[0]
    code, out, _ = run(["explain", "--data", str(data), "--run", pick["run_id"], "--entity", pick["entity_id"],
                        "--week", str(int(pick["week_no"]))], capsys)
    assert code == 0
    money = lambda s: round(float(s.replace(",", "")) * 100)
    variance = money(re.search(r"variance\s+(-?[\d,]+\.\d\d)", out).group(1))
    drivers = [money(m) for m in re.findall(r"^  [A-Z_]+\s+(-?[\d,]+\.\d\d)\s+\(\d+ records\)", out, flags=re.M)]
    assert variance == int(pick["variance_usd"]) and len(drivers) >= 2
    assert sum(drivers) == variance                       # explained to the cent
    assert "unexplained residual 0.00" in out


def test_explain_reports_when_there_is_nothing_to_compare(data, capsys):
    code, out, _ = run(["explain", "--data", str(data), "--run", "FCAST-2026-10-01-001", "--entity", "ENT-000001", "--week", "1"], capsys)
    assert code == 1 and "no comparison" in out            # the live run's weeks have not elapsed


def test_validate_command_passes_on_the_dataset(data, capsys):
    code, out, _ = run(["validate", "--data", str(data)], capsys)
    assert code == 0 and "PASS" in out
    assert "Overall: PASS" in (data / "validation_summary.md").read_text(encoding="utf-8")


def test_evaluate_command_writes_the_reports(data, capsys):
    assert run(["evaluate", "--data", str(data)], capsys)[0] == 0
    text = (data / "reports" / "evaluation.md").read_text(encoding="utf-8")
    assert "Detection quality against the ground truth" in text and "Cash balance accuracy" in text
    assert (data / "reports" / "liquidity_outlook.md").exists() and (data / "reports" / "data_profile.md").exists()


def test_docs_command_regenerates_the_data_dictionary(tmp_path, capsys):
    assert run(["docs", "--out", str(tmp_path)], capsys)[0] == 0
    assert (tmp_path / "DATA_DICTIONARY.md").read_text(encoding="utf-8") == render_data_dictionary(load_schema())


# ------------------------------------------------------------- acting as a user

def test_forecast_then_four_eyes_approval(template, data, capsys):
    _, final = template
    analyst, reviewer = users(final, "OPS_ANALYST")[0], users(final, "RISK_REVIEWER")[0]
    code, out, _ = run(["forecast", "--data", str(data), "--cutoff", "2026-10-01", "--as-user", analyst, "--purpose", "LIVE",
                        "--at", "2026-10-02 08:00"], capsys)
    assert code == 0 and "created FCAST-2026-10-01-002" in out             # next version of the live cutoff
    run_id = "FCAST-2026-10-01-002"
    assert run(["run-event", "--data", str(data), "--run", run_id, "--event", "SUBMITTED", "--as-user", analyst, "--at", "2026-10-02 09:00"], capsys)[0] == 0
    code, out, _ = run(["run-event", "--data", str(data), "--run", run_id, "--event", "APPROVED", "--as-user", analyst, "--at", "2026-10-02 10:00"], capsys)
    assert code == 2 and "REFUSED" in out                                  # an analyst cannot approve
    code, out, _ = run(["run-event", "--data", str(data), "--run", run_id, "--event", "APPROVED", "--as-user", reviewer, "--at", "2026-10-02 11:00"], capsys)
    assert code == 0 and f"{run_id}: APPROVED by {reviewer}" in out
    status = csv(data, "forecast_run").set_index("run_id").at[run_id, "status_at_end"]
    assert status == "APPROVED"
    audit = csv(data, "audit_event").query("target_id == @run_id")
    assert audit["outcome"].tolist().count("DENIED") == 1 and set(audit["action"]) == {"CREATE_RUN", "SUBMIT_RUN", "APPROVE_RUN"}


def test_illegal_transition_is_refused_and_leaves_history_unchanged(template, data, capsys):
    _, final = template
    reviewer = users(final, "RISK_REVIEWER")[0]
    before = len(csv(data, "forecast_run_event"))
    live = final["forecast_run"].query("run_purpose == 'LIVE'")["run_id"].iloc[0]       # already APPROVED
    code, out, _ = run(["run-event", "--data", str(data), "--run", live, "--event", "REJECTED", "--as-user", reviewer], capsys)
    assert code == 2 and "REFUSED" in out
    assert len(csv(data, "forecast_run_event")) == before


def test_account_holders_cannot_forecast_or_view_other_entities(template, data, capsys):
    _, final = template
    holders = final["app_user"].query("role == 'ACCOUNT_HOLDER'").sort_values("user_id")
    me, other = holders.iloc[0], holders.iloc[1]
    code, out, _ = run(["forecast", "--data", str(data), "--cutoff", "2026-10-01", "--as-user", me["user_id"]], capsys)
    assert code == 2 and "DENIED" in out
    code, out, _ = run(["view-entity", "--data", str(data), "--entity", other["entity_id"], "--as-user", me["user_id"]], capsys)
    assert code == 2 and "DENIED" in out
    code, out, _ = run(["view-entity", "--data", str(data), "--entity", me["entity_id"], "--as-user", me["user_id"], "--days", "2"], capsys)
    assert code == 0 and "available_usd" in out
    denied = csv(data, "audit_event").query("actor_id == @me['user_id'] and outcome == 'DENIED'")
    assert set(denied["action"]) == {"CREATE_RUN", "VIEW_ENTITY"}          # both refusals are on the record


def test_a_resolved_exception_cannot_be_reopened_or_waived(template, data, capsys):
    _, final = template
    exc = final["exception"]
    done = exc.query("status_at_end == 'RESOLVED'")["exception_id"].iloc[0]
    reviewer = users(final, "RISK_REVIEWER")[0]
    code, out, _ = run(["exception", "--data", str(data), "--id", done, "--event", "WAIVED", "--as-user", reviewer, "--comment", "x"], capsys)
    assert code == 2 and "REFUSED" in out


# ----------------------------------------------------------------- failures

def test_missing_dataset_is_a_clean_error_not_a_traceback(tmp_path, capsys):
    code, out, err = run(["exceptions", "--data", str(tmp_path / "nope")], capsys)
    assert code == 2 and out == "" and "no CashPilot dataset" in err and "cashpilot all" in err


def test_malformed_date_is_a_clean_error(template, data, capsys):
    _, final = template
    analyst = users(final, "OPS_ANALYST")[0]
    code, _, err = run(["forecast", "--data", str(data), "--cutoff", "not-a-date", "--as-user", analyst], capsys)
    assert code == 2 and err.startswith("error:")


def test_unknown_profile_is_a_clean_error(tmp_path, capsys):
    code, _, err = run(["generate", "--profile", "no-such-profile", "--out", str(tmp_path)], capsys)
    assert code == 2 and "Profile not found" in err


def test_unknown_command_prints_usage_and_exits_2(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["no-such-command"])
    assert stop.value.code == 2 and "usage:" in capsys.readouterr().err


def test_dashboard_command_refuses_a_missing_dataset_cleanly(tmp_path, capsys):
    code, out, err = run(["dashboard", "--data", str(tmp_path / "nope"), "--headless"], capsys)
    assert code == 2 and out == "" and err.startswith("error:")      # either "needs Streamlit" or "no CashPilot dataset"
