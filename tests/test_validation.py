"""Step 8: the validation suite passes on clean data and flags only labelled anomalies."""

from cashpilot.engine.positions import fx_book
from cashpilot.quality.validate import render_markdown, summary_dict, validate

ANOMALY_CHECKS = {"R-RECON-001", "R-FX-001", "R-DUP", "R-CUR", "R-LEAK-001"}


def test_clean_baseline_has_no_violations(pipeline, starter_cfg):
    _, clean, _ = pipeline
    frame = validate(clean, starter_cfg, fx_book(clean, starter_cfg.policy)).frame()
    assert frame["violations"].sum() == 0


def test_final_dataset_has_no_unexpected_violations(pipeline, starter_cfg):
    generated, _, final = pipeline
    report = validate(final, starter_cfg, fx_book(final, starter_cfg.policy), generated.ground_truth)
    frame = report.frame()
    assert report.ok, frame[frame["status"] == "FAIL"]
    assert set(frame.loc[frame["status"] == "EXPECTED", "check_id"]) == ANOMALY_CHECKS
    covered = set(frame["category"])
    assert {"STRUCTURE", "INTEGRITY", "DATES", "ARITHMETIC", "LIFECYCLE", "DUPLICATES", "ANOMALY", "VOLUME"} <= covered


def test_a_corrupted_row_is_reported_as_unexpected(pipeline, starter_cfg):
    generated, _, final = pipeline
    broken = final.copy()
    led = broken["ledger_entry"]
    led.loc[0, "entity_id"] = "ENT-999999"  # breaks a foreign key and the ledger/account join
    report = validate(broken, starter_cfg, fx_book(broken, starter_cfg.policy), generated.ground_truth)
    failed = set(report.frame().query("status == 'FAIL'")["check_id"])
    assert {"I-FK-ledger_entry", "I-JOIN-ledger-account"} <= failed and not report.ok


def test_summary_renders(pipeline, starter_cfg):
    generated, clean, final = pipeline
    report = validate(final, starter_cfg, fx_book(final, starter_cfg.policy), generated.ground_truth)
    base = validate(clean, starter_cfg, fx_book(clean, starter_cfg.policy))
    md = render_markdown(report, "starter", base)
    assert "Overall: PASS" in md and "Clean baseline" in md
    assert summary_dict(report, base)["baseline"]["violations"] == 0
