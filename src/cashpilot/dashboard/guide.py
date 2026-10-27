"""The 'Start here' views: how this dataset meets the brief, in plain terms.

Reads results the pipeline already produced (validation summary, reproducibility proof, exceptions, audit
events); it computes no financial figures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from cashpilot.dashboard import text as T
from cashpilot.dashboard.data import DECISION_TEXT, Bundle
from cashpilot.engine.workflow import PERMISSIONS

BRIEF_SCALE = (("Legal entities", 30, "legal_entity"), ("Bank accounts", 150, "bank_account"), ("Ledger entries", 100_000, "ledger_entry"),
               ("Forecast items", 20_000, "cash_flow_forecast"), ("Currencies", 5, "currency"))

CRITERIA = (
    ("Daily balances reconcile",
     "Each account's balance rolls forward day by day from its opening balance and the ledger; bank statements agree with the ledger "
     "(except the deliberately injected breaks, which are flagged); entity totals add up from their accounts.",
     ("A-STM-rollforward", "A-STM-continuity", "A-POS-rollforward", "A-POS-consolidation", "A-TRF-net"), "Cash overview, Accounts & currencies, Exceptions"),
    ("Scenarios differ only by documented assumptions",
     "Delayed-receipt and stress are the base case plus a written list of assumptions; each assumption's effect is measured and they add up "
     "exactly to the difference from base.",
     ("A-SCN-attribution",), "Forecast"),
    ("Forecasts are reproducible",
     "Re-running the dataset generator with the same seed gives byte-identical files, and re-running a stored forecast from the data known at "
     "its cutoff gives the same result.",
     (), "Audit & exports (Verify reproducibility)"),
    ("Actual-versus-forecast variance is explainable",
     "The difference between forecast and actual cash is split into named drivers with nothing left unexplained, and each driver drills down "
     "to the forecast items and ledger postings behind it.",
     ("A-VAR-explained", "A-VAR-drilldown"), "Actual vs forecast"),
)

AUTHORED_SOURCES = (("bank_account_event", "actor_id"), ("receivable_event", "actor_id"), ("payable_event", "actor_id"), ("cf_revision", "actor_id"),
                    ("forecast_run_event", "actor_id"), ("exception_event", "actor_id"), ("cash_flow_forecast", "created_by"),
                    ("forecast_run", "created_by"), ("liquidity_scenario", "created_by"))


def dataset_scale(b: Bundle) -> pd.DataFrame:
    rows = []
    for item, required, table in BRIEF_SCALE:
        n = len(b.ds[table])
        rows.append({"item": item, "brief_baseline": required, "this_dataset": n,
                     "result": "Matches the brief" if n == required else "Smaller profile of the same generator"})
    return pd.DataFrame(rows)


def acceptance_summary(b: Bundle) -> pd.DataFrame:
    """The four acceptance criteria with the saved validation / reproducibility evidence behind each."""
    results = {}
    repro = {}
    if b.path is not None:
        v = Path(b.path) / "validation_summary.json"
        if v.is_file():
            results = {r["check_id"]: r for r in json.loads(v.read_text(encoding="utf-8"))["results"]}
        r = Path(b.path) / "reproducibility.json"
        if r.is_file():
            repro = json.loads(r.read_text(encoding="utf-8"))
    rows = []
    for name, plain, checks, where in CRITERIA:
        if not checks:
            if repro:
                status = "PASS" if repro.get("identical") else "FAIL"
                proof = f"{repro['files_identical']} of {repro['files_compared']} files byte-identical across two fresh regenerations with the same seed"
            else:
                status, proof = "Not recorded", "Run `cashpilot repro-check` to record it"
        else:
            found = [results[c]["status"] for c in checks if c in results]
            if len(found) != len(checks):
                status, proof = "Not recorded", "No validation summary in this dataset folder (run `cashpilot validate`)"
            else:
                status = "FAIL" if "FAIL" in found else "PASS"
                proof = f"{len(checks)} validation checks: " + ", ".join(checks)
        rows.append({"criterion": name, "what_it_means": plain, "status_text": status, "proof": proof, "where": where})
    return pd.DataFrame(rows)


def edge_case_summary(b: Bundle) -> pd.DataFrame:
    exc = b.ds["exception"]
    exc = exc[exc["category"] == "DATA_QUALITY"]
    rows = []
    for etype, (name, meaning, where) in T.EDGE_CASES.items():
        mine = exc[exc["exception_type"] == etype]
        decision = mine["decision"].iloc[0] if len(mine) else None
        resolved = int(mine["status_at_end"].isin(["RESOLVED", "WAIVED"]).sum())
        rows.append({"edge_case": name, "what_it_means": meaning, "found": int(len(mine)),
                     "how_handled": f"{DECISION_TEXT.get(decision, '')} ({resolved} of {len(mine)} resolved or waived)" if len(mine) else "None found in this dataset",
                     "where": where})
    return pd.DataFrame(rows)


def actors_table(b: Bundle) -> pd.DataFrame:
    ds = b.ds
    authored = pd.Series(dtype="float64")
    for table, col in AUTHORED_SOURCES:
        if table in ds:
            authored = authored.add(ds[table][col].value_counts(), fill_value=0)
    audit = ds["audit_event"]
    denied = audit.loc[audit["outcome"] == "DENIED", "actor_id"].value_counts()
    rows = []
    for role in ("ACCOUNT_HOLDER", "OPS_ANALYST", "RISK_REVIEWER", "SYS_ADMIN", "SYSTEM"):
        ids = set(ds["app_user"].loc[ds["app_user"]["role"] == role, "user_id"])
        can = "; ".join(T.ACTION_TEXT[a] for a, roles in PERMISSIONS.items() if role in roles)
        rows.append({"role": T.ROLE_TEXT[role], "people": len(ids), "can_do": T.ROLE_EXTRA[role] + (f" May: {can}." if can else ""),
                     "records_authored": int(authored.reindex(list(ids)).fillna(0).sum()), "denied_attempts": int(denied.reindex(list(ids)).fillna(0).sum())})
    return pd.DataFrame(rows)
