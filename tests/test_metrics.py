"""Evaluation metrics on tiny fixtures whose answers are worked out by hand.

The ground truth is passed in only here, after detection, exactly as in the real evaluation.
"""

import pandas as pd

from cashpilot.dataset import Dataset
from cashpilot.evaluate.metrics import balance_accuracy, detection_quality, forecast_accuracy

T = pd.Timestamp


def test_detection_quality_by_hand():
    gt = pd.DataFrame([
        ("ANOMALY", "BALANCE_BREAK", "A", "r1", "RAISE_RECON_BREAK"),
        ("ANOMALY", "BALANCE_BREAK", "A", "r2", "RAISE_RECON_BREAK"),
        ("ANOMALY", "BALANCE_BREAK", "B", "r3", "RAISE_RECON_BREAK"),
        ("ANOMALY", "DUPLICATE_CASH_FLOW", "X", "d1", "EXCLUDE_DUPLICATE"),
        ("ANOMALY", "DUPLICATE_CASH_FLOW", "Y", "d2", "EXCLUDE_DUPLICATE"),
        ("NEGATIVE_CONTROL", "NO_ISSUE", "N", "c1", None),
    ], columns=["label", "issue_type", "sub_type", "record_id", "expected_decision"])
    exceptions = pd.DataFrame([
        ("DATA_QUALITY", "BALANCE_BREAK", "r1", "RAISE_RECON_BREAK"),       # correct
        ("DATA_QUALITY", "BALANCE_BREAK", "r2", "USE_PREVIOUS_RATE"),       # found, wrong decision
        ("DATA_QUALITY", "BALANCE_BREAK", "r9", "RAISE_RECON_BREAK"),       # false positive
        ("DATA_QUALITY", "DUPLICATE_CASH_FLOW", "c1", "EXCLUDE_DUPLICATE"),  # flags a legitimate look-alike
        ("BUSINESS_ALERT", "LIQUIDITY_BREACH", "run|scn|ent", "FUNDING_REVIEW"),  # not a data-quality finding: ignored
    ], columns=["category", "exception_type", "record_id", "decision"])
    result = detection_quality(Dataset({"exception": exceptions}), gt)
    by = {r["issue_type"]: r for r in result["by_issue"]}

    bb = by["BALANCE_BREAK"]   # tp 2 (r1, r2), fp 1 (r9), fn 1 (r3)
    assert (bb["labelled"], bb["detected"], bb["tp"], bb["fp"], bb["fn"]) == (3, 3, 2, 1, 1)
    assert (bb["precision"], bb["recall"], bb["f1"]) == (0.6667, 0.6667, 0.6667)
    assert bb["decision_accuracy"] == 0.5     # r1 right, r2 wrong

    dup = by["DUPLICATE_CASH_FLOW"]   # nothing real found; one false alarm on a control
    assert (dup["labelled"], dup["detected"], dup["tp"], dup["fp"], dup["fn"]) == (2, 1, 0, 1, 2)
    assert (dup["precision"], dup["recall"], dup["f1"]) == (0.0, 0.0, 0.0)
    assert "LIQUIDITY_BREACH" not in by

    sub = {(r["issue_type"], r["sub_type"]): r for r in result["by_sub_type"]}
    assert (sub["BALANCE_BREAK", "A"]["detected"], sub["BALANCE_BREAK", "A"]["recall"]) == (2, 1.0)
    assert (sub["BALANCE_BREAK", "B"]["detected"], sub["BALANCE_BREAK", "B"]["recall"]) == (0, 0.0)
    assert (result["negative_controls"], result["negative_controls_flagged"], result["flagged_control_ids"]) == (1, 1, ["c1"])


def test_forecast_accuracy_wape_and_bias_by_hand():
    runs = pd.DataFrame([("R1", "CASHPILOT", "SCHEDULED", "APPROVED", None), ("R2", "LEGACY", "SCHEDULED", "REJECTED", None)],
                        columns=["run_id", "process", "run_purpose", "status_at_end", "supersedes_run_id"])
    # variance = actual - forecast
    rows = [("R1", "SCN-BASE-V01", "E1", 1, 100, 20), ("R1", "SCN-BASE-V01", "E2", 1, -50, 20),
            ("R1", "SCN-BASE-V01", "E1", 2, 200, -50), ("R1", "SCN-BASE-V01", "E1", 6, 300, 30),
            ("R2", "SCN-BASE-V01", "E1", 1, 100, 100),      # rejected run: must not count
            ("R1", "SCN-DELAY-V01", "E1", 1, 100, 10)]
    fva = pd.DataFrame(rows, columns=["run_id", "scenario_id", "entity_id", "week_no", "actual_net_usd", "variance_usd"])
    result = forecast_accuracy(Dataset({"forecast_vs_actual": fva, "forecast_run": runs}), None)

    h = result["approved_versions"]["by_horizon"]
    assert h["week 1"] == {"wape": 0.2667, "bias": 0.2667, "entity_weeks": 2}      # (20+20)/(100+50)
    assert h["weeks 2-4"] == {"wape": 0.25, "bias": -0.25, "entity_weeks": 1}      # 50/200
    assert h["weeks 5-13"] == {"wape": 0.1, "bias": 0.1, "entity_weeks": 1}        # 30/300
    assert result["approved_versions"]["runs"] == 1
    assert result["approved_versions_by_scenario"]["DELAY"]["week 1"]["wape"] == 0.1   # 10/100
    assert "lookahead_signature" not in result                                         # needs ground truth


def _balance_fixture(actual_status):
    runs = pd.DataFrame([("R1", T("2026-01-05"), 14, "APPROVED")], columns=["run_id", "cutoff_date", "horizon_days", "status_at_end"])
    positions = pd.DataFrame([("R1", "SCN-BASE-V01", "E1", T("2026-01-11"), 1000), ("R1", "SCN-BASE-V01", "E1", T("2026-01-18"), 1100)],
                             columns=["run_id", "scenario_id", "entity_id", "position_date", "closing_available_usd"])
    actual = pd.DataFrame([("E1", T("2026-01-11"), 900, "OK"), ("E1", T("2026-01-18"), 1000, actual_status)],
                          columns=["entity_id", "position_date", "available_usd", "fx_status"])
    return Dataset({"forecast_run": runs, "forecast_position": positions, "entity_cash_position": actual})


def test_balance_accuracy_by_hand_and_skips_actuals_with_missing_fx():
    out = balance_accuracy(_balance_fixture("INCOMPLETE"))
    # week 1: forecast 1,000 vs actual 900 -> +11.11%. Week 2's actual is flagged INCOMPLETE (a rate was missing,
    # so the actual is understated): it is excluded rather than compared.
    assert out["week 1"] == {"mape": 0.1111, "bias": 0.1111, "observations": 1, "excluded_incomplete_fx": 0}
    assert out["weeks 2-4"] == {"mape": None, "bias": None, "observations": 0, "excluded_incomplete_fx": 1}
    assert out["weeks 5-13"]["observations"] == 0

    out = balance_accuracy(_balance_fixture("OK"))      # the same week counts once its actual is complete
    assert out["weeks 2-4"] == {"mape": 0.1, "bias": 0.1, "observations": 1, "excluded_incomplete_fx": 0}   # 100/1000
