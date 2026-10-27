"""The explorer, 'Start here' and plain-language layers of the dashboard (no Streamlit needed)."""

from pathlib import Path

import pytest

from cashpilot.dashboard import data as D
from cashpilot.dashboard import explorer as X
from cashpilot.dashboard import guide as G
from cashpilot.dashboard import text as T
from cashpilot.engine.explain import DRIVER_ORDER
from cashpilot.engine.workflow import PERMISSIONS

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def bundle(pipeline, starter_cfg):
    _, _, final = pipeline
    return D.Bundle(final, starter_cfg)


# --------------------------------------------- explorer: entities, ledger, documents

def test_ledger_check_proves_opening_plus_flows_equals_the_stored_closing_balance(bundle):
    ds = bundle.ds
    on = D.default_date(ds)
    checked = 0
    for account in ds["bank_account"]["account_id"]:
        chk = X.ledger_account_check(bundle, account, on)
        if chk["closing_recorded"] is None:          # a closed account has no position on this date
            continue
        checked += 1
        assert chk["matches"], account
        assert chk["closing_calculated"] == pytest.approx(chk["opening"] + chk["inflows"] - chk["outflows"])
    assert checked >= 20


def test_ledger_view_filters_and_converts_to_major_units(bundle):
    led = bundle.ds["ledger_entry"]
    account = led["account_id"].iloc[0]
    view = X.ledger_view(bundle, [account], start="2026-03-01", end="2026-03-31", entry_types=["BANK_FEE"])
    raw = led[(led["account_id"] == account) & (led["posting_date"] >= "2026-03-01") & (led["posting_date"] <= "2026-03-31") & (led["entry_type"] == "BANK_FEE")]
    assert len(view) == len(raw) > 0 and (view["entry_type"] == "BANK_FEE").all()
    scale = 1 if raw["currency"].iloc[0] == "JPY" else 100
    assert view["money_out"].sum() == pytest.approx(-raw["amount"].sum() / scale) and view["money_in"].sum() == 0     # fees are money out
    whole = X.ledger_view(bundle)
    assert len(whole) == len(led) and whole["money_in"].sum() > 0
    assert X.ledger_totals(X.ledger_view(bundle, [account]))["entries"].sum() == (led["account_id"] == account).sum()


def test_entity_and_account_master_data_match_the_tables(bundle):
    ds = bundle.ds
    ent = X.entity_master(bundle)
    assert len(ent) == len(ds["legal_entity"]) and ent["accounts"].sum() == len(ds["bank_account"])
    holding = ent[ent["entity_type"] == "HOLDING"]
    assert len(holding) == 1 and holding["parent_entity_id"].iloc[0] is None
    acc = X.account_master(bundle)
    assert len(acc) == len(ds["bank_account"]) and set(acc["status_at_end"]) <= {"ACTIVE", "FROZEN", "CLOSED"}
    closed = acc[acc["status_at_end"] == "CLOSED"]["account_id"].iloc[0]
    assert X.account_events(bundle, closed)["event_type"].tolist()[-1] == "CLOSED"       # the lifecycle history is kept
    one = ent["entity_id"].iloc[1]
    assert set(X.account_master(bundle, one)["entity_id"]) == {one}


def test_receivables_and_payables_lists_agree_with_their_lifecycle_events(bundle):
    ds = bundle.ds
    r = X.receivable_list(bundle)
    assert len(r) == len(ds["receivable"])
    assert r["status"].value_counts().to_dict() == ds["receivable"]["status_at_end"].value_counts().to_dict()
    paid = r[r["status"] == "PAID"]
    assert paid["paid_on"].notna().all() and (paid["days_late"] == (paid["paid_on"] - paid["due_date"]).dt.days).all()
    assert r.loc[r["status"] != "PAID", "paid_on"].isna().all()                  # unpaid invoices have no payment date
    p = X.payable_list(bundle)
    assert len(p) == len(ds["payable"]) and p["is_one_off"].sum() == ds["payable"]["is_one_off"].sum()
    one_offs = X.one_off_payments(bundle)
    assert one_offs["is_one_off"].all() and set(one_offs["category"]) <= {"CAPEX", "TAX_SETTLEMENT", "DEBT_REPAYMENT", "ACQUISITION", "LEGAL_SETTLEMENT"}
    summary = X.document_status_summary(bundle)
    assert summary.loc[summary["kind"] == "Customer invoices", "count"].sum() == len(r)


def test_customers_pay_later_the_riskier_they_are(bundle):
    late = X.lateness_by_tier(bundle).set_index("risk_tier")
    assert late["median_days_late"].is_monotonic_increasing                # the documented rule behind delayed receivables
    assert late["invoices"].sum() == len(bundle.ds["receivable"])
    assert late.loc["A", "median_days_late"] <= 2 and late.loc["D", "median_days_late"] >= 20


# ---------------------------------------------------------- guide: brief, actors

def test_dataset_scale_compares_with_the_briefs_baseline(bundle):
    scale = G.dataset_scale(bundle).set_index("item")
    assert scale.loc["Legal entities", "brief_baseline"] == 30 and scale.loc["Ledger entries", "brief_baseline"] == 100_000
    assert scale.loc["Ledger entries", "this_dataset"] == len(bundle.ds["ledger_entry"])
    assert scale.loc["Currencies", "result"] == "Matches the brief" and scale.loc["Legal entities", "result"].startswith("Smaller")


def test_acceptance_criteria_are_read_from_the_saved_validation_evidence(bundle):
    saved = D.Bundle(bundle.ds, bundle.cfg, REPO / "data" / "starter")
    acc = G.acceptance_summary(saved)
    assert len(acc) == 4 and set(acc["status_text"]) == {"PASS"}
    assert "byte-identical" in acc.set_index("criterion").at["Forecasts are reproducible", "proof"]
    assert set(G.acceptance_summary(bundle)["status_text"]) == {"Not recorded"}     # a bundle without files claims nothing


def test_edge_case_summary_matches_the_exceptions(bundle):
    edges = G.edge_case_summary(bundle)
    exc = bundle.ds["exception"]
    assert len(edges) == 5 and edges["found"].sum() == (exc["category"] == "DATA_QUALITY").sum()
    assert (edges["found"] > 0).all() and edges["how_handled"].str.contains("resolved or waived").all()


def test_actors_table_counts_every_role_and_refusal(bundle):
    actors = G.actors_table(bundle)
    assert actors["people"].sum() == len(bundle.ds["app_user"]) and len(actors) == 5
    assert actors["denied_attempts"].sum() == (bundle.ds["audit_event"]["outcome"] == "DENIED").sum() > 0
    assert actors["records_authored"].min() > 0
    assert "approve" in actors.set_index("role").at["Risk / compliance reviewer", "can_do"]


# ---------------------------------------------- plain language is complete

def test_every_code_the_engine_can_produce_has_a_plain_explanation(bundle):
    ds = bundle.ds
    assert set(DRIVER_ORDER) == set(T.DRIVER_TEXT) == set(T.DRIVER_LABEL)
    assert set(ds["forecast_run_item"]["treatment"]) <= set(T.TREATMENT_TEXT)
    assert set(ds["exception"]["exception_type"]) <= set(T.EXCEPTION_NAME)
    assert set(ds["forecast_run"]["run_purpose"]) <= set(T.PURPOSE_TEXT)
    assert set(ds["cash_flow_forecast"]["flow_category"]) <= set(T.FLOW_LABEL)
    assert set(ds["app_user"]["role"]) <= set(T.ROLE_TEXT)
    assert set(ds["exception"]["decision"]) <= set(D.DECISION_TEXT) and set(ds["exception"]["rule_id"]) <= set(D.RULE_TEXT)
    assert set(ds["cf_revision"]["reason"]) <= set(T.REASON_TEXT)
    assert set(PERMISSIONS) <= set(T.ACTION_TEXT)


def test_every_reason_in_a_run_comparison_is_explained(bundle):
    runs = D.run_catalog(bundle.ds)["run_id"].tolist()
    diff = D.run_diff(bundle, runs[-3], runs[-1])["items"]
    assert len(diff) and not diff["what_happened"].str.startswith("Other").any()
    assert diff["change"].str.match(r"^(New in this run|No longer in this run|Changed: .+)$").all()
    assert T.plain_change("CHANGED_DATE+AMOUNT_OR_FX+TREATMENT") == "Changed: date, amount or FX rate and how it is handled"
    assert T.plain_reason("SETTLED: REALIZED") == "It happened: the cash was booked"
    assert T.plain_reason("SOMETHING_NEW") == "Other: SOMETHING_NEW"           # unknown codes are shown, never hidden


def test_runs_with_actuals_excludes_the_live_run(bundle):
    ids = D.runs_with_actuals(bundle.ds)
    live = D.default_run(bundle.ds)
    assert ids and live not in ids and set(ids) == set(bundle.ds["forecast_vs_actual"]["run_id"])
    assert D.run_catalog(bundle.ds).set_index("run_id")["label"][live].endswith("live  ·  approved")


def test_accuracy_view_opens_on_a_run_with_several_weeks(bundle):
    ds = bundle.ds
    chosen = D.default_accuracy_run(ds)
    f = ds["forecast_vs_actual"]
    weeks = f[(f["run_id"] == chosen) & f["scenario_id"].str.startswith("SCN-BASE")]["week_no"].nunique()
    assert chosen in D.runs_with_actuals(ds) and weeks >= 4 and chosen != D.runs_with_actuals(ds)[-1]
