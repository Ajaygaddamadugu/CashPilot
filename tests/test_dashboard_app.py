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
    assert [t.label for t in at.tabs] == ["Start here", "Cash overview", "Accounts & currencies", "Entities & transactions", "Forecast",
                                          "Cash-flow drivers", "Exceptions", "Actual vs forecast", "Audit & exports"]
    assert at.title[0].value == "CashPilot"
    labels = {m.label for m in at.metric}
    assert {"Available", "Restricted", "Entities below buffer", "Validation", "Companies", "Bank accounts", "Ledger entries"} <= labels
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
    sidebar(at, "Company").select_index(2)          # a single entity instead of the group
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
    leak = next(i for i, o in enumerate(trace.options) if "after its cutoff" in o)      # shown in plain words, not as a code
    trace.select_index(leak)
    at = at.run()
    assert not at.exception, [e.value for e in at.exception]
    text = " ".join(m.value for m in at.markdown)
    assert "Forecast used data from after its cutoff" in text and "R-LEAK-001" in text and "Supersede with rerun" in text and "SUPERSEDE_WITH_RERUN" not in text


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


def test_start_here_explains_the_brief_in_plain_words(app):
    at = app.run()
    text = " ".join(m.value for m in at.markdown)
    for needle in ("Daily balances reconcile", "Scenarios differ only by documented assumptions", "Forecasts are reproducible",
                   "Actual-versus-forecast variance is explainable"):
        assert needle in text, needle
    assert all("PASS" in m.value for m in at.markdown if m.value.startswith("**✅"))
    headers = " ".join(h.value for h in at.subheader)
    for needle in ("What is CashPilot?", "The five edge cases the brief requires", "Who does what", "The four acceptance criteria"):
        assert needle in headers, needle


def test_every_explorer_section_renders(app):
    at = app.run()
    radio = next(r for r in at.radio if r.label == "Show")
    for option in radio.options:
        radio.set_value(option)
        at = at.run()
        assert not at.exception, (option, [e.value for e in at.exception])
        radio = next(r for r in at.radio if r.label == "Show")
    # the ledger section shows the opening + money in - money out = closing check, and it agrees
    radio.set_value("Bank transactions (ledger)")
    at = at.run()
    assert any("They agree" in s.value for s in at.success), [e.value for e in at.error]


def test_actual_vs_forecast_opens_on_a_past_version_with_data(app):
    at = app.run()
    pick = next(s for s in at.selectbox if s.label.startswith("Forecast version to evaluate"))
    assert "live" not in pick.value and not any(i.value.startswith("No fully elapsed") for i in at.info)


def test_tables_contain_no_python_none_or_mixed_type_cells(app):
    """Blank cells instead of the word None, and one type per column (Arrow cannot serialise mixed columns)."""
    at = app.run()
    assert not at.exception
    assert len(at.dataframe) > 10
    for df in at.dataframe:
        for col in df.value.columns:
            values = df.value[col]
            assert not (values.astype(str) == "None").any(), col
            if values.dtype == object:
                assert values.map(type).nunique() <= 1, (col, values.map(type).unique())


def test_the_sidebar_shows_names_not_paths_or_codes(app):
    at = app.run()
    shown = sidebar(at, "Dataset").options
    assert shown[0].startswith("Starter") and all("/" not in o and "\\" not in o for o in shown), shown     # names, not folder paths
    for option in sidebar(at, "Scenario").options:
        assert "SCN-" not in option, option                   # "Base · v1", "Delayed receipt · v1", "Stress · v2"
    assert any(o.startswith("Stress") for o in sidebar(at, "Scenario").options)
    assert any(c.value for c in at.sidebar.caption), "the chosen scenario is described in words"


def test_table_cells_use_words_and_names_not_codes(app):
    """Cells read 'Not needed (USD)' and 'Operations analyst 04 (USR-0004)', not NOT_REQUIRED and USR-0004 alone."""
    at = app.run()
    cells = " ".join(str(v) for df in at.dataframe for col in df.value.columns for v in df.value[col].astype(str).unique()[:200])
    for raw in ("NEW_AFTER_PREVIOUS_CUTOFF", "EXCLUDED_DUPLICATE", "NOT_REQUIRED", "PARTIALLY_PAID", "OPERATING_RECEIPT", "AR_SUBLEDGER", "BELOW BUFFER", "INCOMPLETE FX"):
        assert raw not in cells, raw
    assert "Not needed (USD)" in cells

