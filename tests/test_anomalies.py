"""Edge cases: injected only where labelled, kept apart from the data, and detected without it."""

import pandas as pd

from cashpilot.dataset import Dataset
from cashpilot.engine.positions import fx_book
from cashpilot.quality.detectors import detect_all
from cashpilot.quality.validate import LABEL_COLUMNS

DETERMINISTIC = ["BALANCE_BREAK", "FX_RATE_MISSING", "MIXED_CURRENCY", "LOOKAHEAD_LEAKAGE"]


def anomalies(gt, issue=None):
    a = gt[gt["label"] == "ANOMALY"]
    return a if issue is None else a[a["issue_type"] == issue]


def test_ground_truth_lives_outside_the_dataset(pipeline):
    generated, _, final = pipeline
    assert generated.ground_truth is not None and len(generated.ground_truth)
    assert "anomaly_label" not in final.tables
    for name, df in final.tables.items():
        assert not set(df.columns) & set(LABEL_COLUMNS), name


def test_injected_counts_follow_the_profile(pipeline, starter_cfg):
    gt = pipeline[0].ground_truth
    a = starter_cfg.anomalies
    assert len(anomalies(gt, "BALANCE_BREAK")) == a["balance_breaks"]
    assert len(anomalies(gt, "DUPLICATE_CASH_FLOW")) == a["duplicate_cash_flows"]
    assert len(anomalies(gt, "MIXED_CURRENCY")) == a["mixed_currency"]
    assert len(anomalies(gt, "LOOKAHEAD_LEAKAGE")) == a["lookahead_runs"]
    assert len(anomalies(gt, "FX_RATE_MISSING")) >= a["fx_missing_short_gaps"] + 5 * a["fx_missing_long_gaps"]
    assert (gt["label"] == "NEGATIVE_CONTROL").sum() > 0


def test_injection_touches_only_the_labelled_records(pipeline):
    generated, clean, _ = pipeline
    gt = generated.ground_truth
    pd.testing.assert_frame_equal(generated["ledger_entry"], clean["ledger_entry"])
    # forecast items: unchanged except the labelled mixed-currency rows; duplicates are new rows
    mixed = set(anomalies(gt, "MIXED_CURRENCY")["record_id"])
    dups = set(anomalies(gt, "DUPLICATE_CASH_FLOW")["record_id"])
    cf = generated["cash_flow_forecast"]
    assert set(cf["cf_id"]) - set(clean["cash_flow_forecast"]["cf_id"]) == dups
    same = cf[~cf["cf_id"].isin(mixed | dups)].reset_index(drop=True)
    pd.testing.assert_frame_equal(same, clean["cash_flow_forecast"][~clean["cash_flow_forecast"]["cf_id"].isin(mixed)].reset_index(drop=True))
    # FX: exactly the labelled fixings were removed
    removed = set(clean["currency_rate"]["rate_id"]) - set(generated["currency_rate"]["rate_id"])
    assert removed == set(anomalies(gt, "FX_RATE_MISSING")["record_id"])
    # statements: the bank's daily movement differs only on the labelled days
    def movement(st):
        return st.set_index("statement_id").eval("closing_balance - opening_balance")
    diff = movement(generated["bank_statement"]) != movement(clean["bank_statement"])
    assert set(diff[diff].index) == set(anomalies(gt, "BALANCE_BREAK")["record_id"])


def test_deterministic_rules_find_exactly_the_injected_anomalies(pipeline):
    generated, _, final = pipeline
    gt, exc = generated.ground_truth, final["exception"]
    for issue in DETERMINISTIC:
        found = set(exc.loc[exc["exception_type"] == issue, "record_id"])
        assert found == set(anomalies(gt, issue)["record_id"]), issue


def test_duplicates_within_tolerance_are_found_and_decisions_match(pipeline):
    generated, _, final = pipeline
    gt, exc = generated.ground_truth, final["exception"]
    dup = anomalies(gt, "DUPLICATE_CASH_FLOW")
    findable = set(dup.loc[dup["sub_type"] != "FUZZY_BEYOND_TOLERANCE", "record_id"])
    found = set(exc.loc[exc["exception_type"] == "DUPLICATE_CASH_FLOW", "record_id"])
    assert findable <= found
    merged = anomalies(gt).merge(exc, on="record_id", suffixes=("_gt", ""))
    assert (merged["expected_decision"] == merged["decision"]).all()


def test_negative_controls_are_not_flagged(pipeline):
    generated, _, final = pipeline
    controls = generated.ground_truth.query("label == 'NEGATIVE_CONTROL'")["record_id"]
    assert not set(controls) & set(final["exception"]["record_id"])


def test_detection_never_reads_the_ground_truth(pipeline, starter_cfg):
    generated, _, final = pipeline
    blind = Dataset({k: v for k, v in generated.tables.items()}, ground_truth=None)
    found = detect_all(blind, starter_cfg, fx_book(blind, starter_cfg.policy))
    exc = final["exception"]
    assert set(found["record_id"]) == set(exc.loc[exc["category"] == "DATA_QUALITY", "record_id"])
