"""Headless smoke tests of the Streamlit app (skipped when the optional dashboard extra is not installed)."""

import shutil
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
APP = str(REPO / "src" / "cashpilot" / "dashboard" / "app.py")
TIMEOUT = 240


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.chdir(REPO)
    monkeypatch.setenv("CASHPILOT_DATA", "data/starter")
    return AppTest.from_file(APP, default_timeout=TIMEOUT)


def sidebar(at, label):
    return next(s for s in at.sidebar.selectbox if s.label == label)


def test_every_tab_renders_with_the_committed_dataset(app):
    at = app.run()
    assert not at.exception, [e.value for e in at.exception]
    assert [t.label for t in at.tabs] == ["Cash overview", "Accounts & currencies", "Forecast", "Cash-flow drivers", "Exceptions",
                                          "Actual vs forecast", "Audit & exports"]
    assert at.title[0].value == "CashPilot"
    labels = {m.label for m in at.metric}
    assert {"Available", "Restricted", "Entities below buffer", "Validation"} <= labels
    assert any(len(d.value) for d in at.dataframe)
    assert not at.error


def test_every_scenario_and_entity_filter_works(app):
    at = app.run()
    scenarios = sidebar(at, "Scenario").options
    assert len(scenarios) == 3
    for i in range(len(scenarios)):
        sidebar(at, "Scenario").select_index(i)
        at = at.run()
        assert not at.exception, (scenarios[i], [e.value for e in at.exception])
    sidebar(at, "Entity").select_index(2)          # a single entity instead of the group
    at = at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_every_forecast_run_can_be_selected(app):
    at = app.run()
    runs = sidebar(at, "Forecast run").options
    assert len(runs) > 10
    for i in (0, len(runs) // 2, len(runs) - 1):    # newest, a historical version, the oldest
        sidebar(at, "Forecast run").select_index(i)
        at = at.run()
        assert not at.exception, (runs[i], [e.value for e in at.exception])


def test_an_exception_can_be_traced_to_its_evidence(app):
    at = app.run()
    trace = next(s for s in at.selectbox if s.label == "Trace an exception")
    leak = next(i for i, o in enumerate(trace.options) if "LOOKAHEAD_LEAKAGE" in o)
    trace.select_index(leak)
    at = at.run()
    assert not at.exception, [e.value for e in at.exception]
    text = " ".join(m.value for m in at.markdown)
    assert "LOOKAHEAD_LEAKAGE" in text and "R-LEAK-001" in text and "SUPERSEDE_WITH_RERUN" in text


def test_reproducibility_can_be_verified_from_the_ui(app):
    at = app.run()
    next(b for b in at.button if b.label == "Verify reproducibility").click()
    at = at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Reproduced" in s.value for s in at.success)           # the live run re-runs to identical hashes
    sidebar(at, "Forecast run").select_index(len(sidebar(at, "Forecast run").options) - 1)
    # the look-ahead run is the one that must NOT reproduce
    labels = sidebar(at, "Forecast run").options
    at = at.run()
    sel = sidebar(at, "Forecast run")
    sel.select_index(next(i for i, o in enumerate(sel.options) if "FCAST-2026-05-21-001" in o))
    at = at.run()
    next(b for b in at.button if b.label == "Verify reproducibility").click()
    at = at.run()
    assert not at.exception and any("Not reproducible" in e.value for e in at.error)


def test_missing_dataset_is_a_message_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CASHPILOT_DATA", str(tmp_path / "nothing"))
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    assert not at.exception and any("No dataset found" in e.value for e in at.error)


def test_an_unprocessed_dataset_explains_what_to_run(monkeypatch, tmp_path):
    root = tmp_path / "data" / "half"
    shutil.copytree(REPO / "data" / "starter", root, ignore=shutil.ignore_patterns("json", "sql", "reports"))
    (root / "csv" / "entity_cash_position.csv").unlink()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CASHPILOT_DATA", "data/half")
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    assert not at.exception
    assert any("has not been processed yet" in e.value and "entity_cash_position" in e.value for e in at.error)


def test_the_dashboard_never_writes_to_the_dataset(app):
    before = {p: p.stat().st_mtime_ns for p in (REPO / "data" / "starter").rglob("*") if p.is_file()}
    at = app.run()
    next(b for b in at.button if b.label == "Verify reproducibility").click()
    at.run()
    after = {p: p.stat().st_mtime_ns for p in (REPO / "data" / "starter").rglob("*") if p.is_file()}
    assert before == after
