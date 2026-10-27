"""Roles, four-eyes, append-only history, remediation of leaky runs and the live forecast."""

import pandas as pd
import pytest

from cashpilot.dataset import Dataset
from cashpilot.engine.workflow import Workflow, WorkflowError


def copy(ds):
    return Dataset({k: v.copy() for k, v in ds.tables.items()})


def test_leaky_runs_are_superseded_by_approved_as_of_reruns(pipeline):
    generated, _, final = pipeline
    gt = generated.ground_truth
    runs = final["forecast_run"].set_index("run_id")
    for leaky in gt.query("issue_type == 'LOOKAHEAD_LEAKAGE'")["record_id"]:
        assert runs.at[leaky, "status_at_end"] == "SUPERSEDED"
        fix = runs[runs["supersedes_run_id"] == leaky]
        assert len(fix) == 1 and fix["process"].iloc[0] == "CASHPILOT" and fix["status_at_end"].iloc[0] == "APPROVED"
        items = final["forecast_run_item"]
        lineage = items[items["run_id"] == fix.index[0]]
        assert (lineage["input_recorded_at"] < fix["knowledge_cutoff_ts"].iloc[0]).all()


def test_live_forecast_is_approved_by_a_different_person(pipeline, starter_cfg):
    _, _, final = pipeline
    runs = final["forecast_run"]
    live = runs[runs["run_purpose"] == "LIVE"].iloc[0]
    assert live["cutoff_date"] == pd.Timestamp(starter_cfg.forecast["live_cutoff"]) and live["status_at_end"] == "APPROVED"
    ev = final["forecast_run_event"]
    ev = ev[ev["run_id"] == live["run_id"]]
    approver = ev.loc[ev["event_type"] == "APPROVED", "actor_id"].iloc[0]
    assert approver not in set(ev.loc[ev["event_type"].isin(["CREATED", "SUBMITTED"]), "actor_id"])


def test_processing_only_appends_to_history(pipeline):
    generated, _, final = pipeline
    for table, key in (("forecast_run_event", "event_id"), ("forecast_run_item", None), ("forecast_position", None)):
        before, after = generated[table], final[table]
        assert len(after) >= len(before)
        pd.testing.assert_frame_equal(after.iloc[: len(before)].reset_index(drop=True), before.reset_index(drop=True))


def test_permissions_four_eyes_and_waivers_are_enforced(pipeline, starter_cfg):
    _, _, final = pipeline
    ds = copy(final)
    wf = Workflow(ds, starter_cfg)
    users = ds["app_user"]
    analyst = users.query("role == 'OPS_ANALYST'")["user_id"].iloc[0]
    holder = users.query("role == 'ACCOUNT_HOLDER'").iloc[0]
    other_entity = users.query("role == 'ACCOUNT_HOLDER'")["entity_id"].iloc[1]
    ts = pd.Timestamp("2026-10-02 09:00")
    live = ds["forecast_run"].query("run_purpose == 'LIVE'")["run_id"].iloc[0]
    with pytest.raises(WorkflowError, match="may not"):
        wf.run_event(live, "SUPERSEDED", analyst, ts)            # analysts cannot supersede
    with pytest.raises(WorkflowError, match="cannot SUBMITTED"):
        wf.run_event(live, "SUBMITTED", analyst, ts)             # APPROVED -> SUBMITTED is not a transition
    with pytest.raises(WorkflowError, match="may not view"):
        wf.view_entity(holder["user_id"], other_entity, ts)      # account holders see only their entity
    assert len(wf.view_entity(holder["user_id"], holder["entity_id"], ts)) > 0
    audit = ds["audit_event"]
    assert (audit["outcome"] == "DENIED").sum() >= 3
    exc = ds["exception"].query("status_at_end == 'RESOLVED'")["exception_id"].iloc[0]
    with pytest.raises(WorkflowError):
        wf.exception_event(exc, "WAIVED", users.query("role == 'RISK_REVIEWER'")["user_id"].iloc[0], ts)  # terminal state


def test_every_variance_is_fully_explained(pipeline):
    _, _, final = pipeline
    fva = final["forecast_vs_actual"]
    assert len(fva) and (fva["residual_usd"] == 0).all()
    drivers = [c for c in fva.columns if c.endswith("_usd") and c not in ("forecast_net_usd", "actual_net_usd", "variance_usd", "residual_usd")]
    assert (fva[drivers].sum(axis=1) == fva["actual_net_usd"] - fva["forecast_net_usd"]).all()


def test_waiver_needs_a_reviewer_and_a_written_justification(pipeline, starter_cfg):
    _, _, final = pipeline
    ds = copy(final)
    wf = Workflow(ds, starter_cfg)
    users = ds["app_user"]
    analyst = users.query("role == 'OPS_ANALYST'")["user_id"].iloc[0]
    reviewer = users.query("role == 'RISK_REVIEWER'")["user_id"].iloc[0]
    finding = pd.DataFrame([{
        "rule_id": "R-FX-001", "category": "DATA_QUALITY", "exception_type": "FX_RATE_MISSING", "severity": "HIGH",
        "record_table": "currency_rate", "record_id": "FXR-2026-03-03-JPY-USD", "decision": "BLOCK_CONVERSION", "details": "test"}])
    ts = pd.Timestamp("2026-10-03 09:00")
    exc_id = wf.raise_exceptions(finding, ts)[0]
    wf.exception_event(exc_id, "ASSIGNED", "USR-0001", ts + pd.Timedelta(minutes=1))
    wf.exception_event(exc_id, "ESCALATED", analyst, ts + pd.Timedelta(minutes=2), "gap exceeds tolerance")
    with pytest.raises(WorkflowError, match="may not waive"):
        wf.exception_event(exc_id, "WAIVED", analyst, ts + pd.Timedelta(minutes=3), "I accept it")      # wrong role
    with pytest.raises(WorkflowError, match="written justification"):
        wf.exception_event(exc_id, "WAIVED", reviewer, ts + pd.Timedelta(minutes=4))                      # no justification
    assert wf.exception_status(exc_id) == "ESCALATED"                                                    # refusals changed nothing
    wf.exception_event(exc_id, "WAIVED", reviewer, ts + pd.Timedelta(minutes=5), "last fixing accepted for historical valuation")
    assert wf.exception_status(exc_id) == "WAIVED"
    events = ds["exception_event"].query("exception_id == @exc_id")
    assert events["event_type"].tolist() == ["RAISED", "ASSIGNED", "ESCALATED", "WAIVED"]
