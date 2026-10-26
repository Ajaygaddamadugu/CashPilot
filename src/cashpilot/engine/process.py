"""What CashPilot does with a dataset, end to end.

1. Consolidate actual positions (per account, per entity in USD; available vs restricted).
2. Audit the data and every stored forecast run; raise exceptions, each with a rule and decision.
3. Work the exceptions through the role-based workflow, following the documented playbook.
4. Remediate forecast versions that used post-cutoff data: an as-of re-run is approved and
   supersedes the leaky version (history is appended, never edited).
5. Produce the live 13-week forecast, raise liquidity alerts, approve it under four-eyes.
6. Compare every forecast version with actuals and attribute the variance to drivers.
All timestamps are synthetic (derived from the live cutoff), so the output is reproducible.
"""

from __future__ import annotations

import pandas as pd

from cashpilot.core.config import Config
from cashpilot.dataset import Dataset, conform_dataset
from cashpilot.engine.compare import compare_all
from cashpilot.engine.forecast import ForecastContext, RunSpec, create_run
from cashpilot.engine.positions import daily_cash_positions, entity_cash_positions, fx_book
from cashpilot.engine.workflow import Workflow, WorkflowError
from cashpilot.quality.detectors import detect_all, liquidity_alerts

SYSTEM = "USR-0001"

# Playbook: how each kind of exception is worked (docs/ACTORS_WORKFLOW.md).
PLAYBOOK = {
    ("BALANCE_BREAK", "LOW"): [("RESOLVED", "analyst", "Bank charge or returned payment booked; statement reconciled")],
    ("BALANCE_BREAK", "HIGH"): [("ESCALATED", "analyst", "Material difference with the bank statement"),
                                ("RESOLVED", "reviewer", "Adjustment approved; bank asked to confirm the item")],
    ("FX_RATE_MISSING", "MEDIUM"): [("RESOLVED", "analyst", "Previous fixing used within the staleness tolerance")],
    ("FX_RATE_MISSING", "HIGH"): [("ESCALATED", "analyst", "Fixing gap exceeds tolerance; conversion blocked"),
                                  ("WAIVED", "reviewer", "Accept last available fixing for historical valuation; vendor gap logged")],
    ("DUPLICATE_CASH_FLOW", "MEDIUM"): [("RESOLVED", "analyst", "Manual duplicate excluded by the data-quality gate; account holder notified")],
    ("MIXED_CURRENCY", "HIGH"): [("ESCALATED", "analyst", "Forecast item mixes currencies"),
                                 ("RESOLVED", "reviewer", "Converted at the cutoff rate by the data-quality gate; source system fix requested")],
    ("LIQUIDITY_BREACH", "HIGH"): [("ESCALATED", "analyst", "Base-case breach of the liquidity buffer"),
                                   ("RESOLVED", "reviewer", "Funding plan agreed: intra-group top-up from the pool header")],
    ("LIQUIDITY_BREACH", "MEDIUM"): [("RESOLVED", "analyst", "Delayed-receipt breach monitored; collections team alerted")],
    ("LIQUIDITY_BREACH", "LOW"): [("RESOLVED", "analyst", "Stress-only breach within the contingency plan")],
}


def process(ds: Dataset, cfg: Config) -> Dataset:
    ds = Dataset({k: v.copy() for k, v in ds.tables.items()}, ds.ground_truth)
    fx = fx_book(ds, cfg.policy)
    daily = daily_cash_positions(ds, cfg.actuals_end, fx)
    ds["daily_cash_position"] = daily
    ds["entity_cash_position"] = entity_cash_positions(ds, daily, fx)

    ctx = ForecastContext(ds, cfg, fx)
    wf = Workflow(ds, cfg)
    users = ds["app_user"]
    analysts = users.loc[users["role"] == "OPS_ANALYST", "user_id"].tolist()
    reviewers = users.loc[users["role"] == "RISK_REVIEWER", "user_id"].tolist()
    live_cutoff = pd.Timestamp(cfg.forecast["live_cutoff"])
    audit_ts = live_cutoff + pd.Timedelta(hours=6)

    # 2-3. audit and work the exceptions
    findings = detect_all(ds, cfg, fx)
    exc_ids = wf.raise_exceptions(findings, audit_ts)
    leaks = []
    for i, exc_id in enumerate(exc_ids):
        e = ds["exception"].set_index("exception_id").loc[exc_id]
        people = {"analyst": analysts[i % len(analysts)], "reviewer": reviewers[i % len(reviewers)]}
        t = audit_ts + pd.Timedelta(minutes=5, seconds=i)
        wf.exception_event(exc_id, "ASSIGNED", SYSTEM, t, f"Assigned to {people['analyst']}")
        if e["exception_type"] == "LOOKAHEAD_LEAKAGE":
            wf.exception_event(exc_id, "ESCALATED", people["analyst"], t + pd.Timedelta(minutes=30),
                               "Run used data recorded after its cutoff; as-of re-run required")
            leaks.append((exc_id, e["run_id"], people))
            continue
        for k, (event, who, comment) in enumerate(PLAYBOOK[(e["exception_type"], e["severity"])]):
            wf.exception_event(exc_id, event, people[who], t + pd.Timedelta(hours=1 + k), comment)

    # 4. remediation: as-of re-runs supersede leaky versions
    runs = ds["forecast_run"]
    for k, (exc_id, old_id, people) in enumerate(leaks):
        old = runs.set_index("run_id").loc[old_id]
        cutoff = pd.Timestamp(old["cutoff_date"])
        version = int(runs.loc[runs["cutoff_date"] == cutoff, "version"].max()) + 1
        created = audit_ts + pd.Timedelta(hours=3, minutes=10 * k)
        result = create_run(ctx, RunSpec(cutoff, version, "CASHPILOT", "REMEDIATION", people["analyst"], created,
                                         ctx.effective_scenarios(cutoff), supersedes=old_id))
        new_id = result.run["run_id"]
        wf.add_run(result, [(created, "CREATED", people["analyst"], f"As-of re-run for {exc_id}"),
                            (created + pd.Timedelta(minutes=2), "COMPLETED", SYSTEM, None),
                            (created + pd.Timedelta(minutes=20), "SUBMITTED", people["analyst"], None),
                            (created + pd.Timedelta(hours=2), "APPROVED", people["reviewer"], "Lineage verified: all inputs before the cutoff")])
        wf.run_event(old_id, "SUPERSEDED", people["reviewer"], created + pd.Timedelta(hours=2, minutes=1),
                     f"Superseded by {new_id} ({exc_id})")
        wf.exception_event(exc_id, "RESOLVED", people["reviewer"], created + pd.Timedelta(hours=2, minutes=2),
                           f"Superseded by {new_id}; as-of re-run approved")

    # 5. live forecast, alerts, approval
    analyst, reviewer = analysts[0], reviewers[0]
    created = live_cutoff + pd.Timedelta(hours=8, minutes=15)
    version = int(runs.loc[runs["cutoff_date"] == live_cutoff, "version"].max()) + 1 if (runs["cutoff_date"] == live_cutoff).any() else 1
    live = create_run(ctx, RunSpec(live_cutoff, version, "CASHPILOT", "LIVE", analyst, created, ctx.effective_scenarios(live_cutoff)))
    wf.add_run(live, [(created, "CREATED", analyst, "Weekly 13-week liquidity forecast"),
                      (created + pd.Timedelta(minutes=3), "COMPLETED", SYSTEM, None)])
    alert_ts = created + pd.Timedelta(minutes=5)
    alerts = liquidity_alerts(live.positions, live.run["run_id"])
    for i, exc_id in enumerate(wf.raise_exceptions(alerts, alert_ts)):
        e = ds["exception"].set_index("exception_id").loc[exc_id]
        t = alert_ts + pd.Timedelta(minutes=1, seconds=i)
        wf.exception_event(exc_id, "ASSIGNED", SYSTEM, t, f"Assigned to {analyst}")
        for k, (event, who, comment) in enumerate(PLAYBOOK[(e["exception_type"], e["severity"])]):
            wf.exception_event(exc_id, event, analyst if who == "analyst" else reviewer, t + pd.Timedelta(hours=1 + k), comment)
    wf.run_event(live.run["run_id"], "SUBMITTED", analyst, created + pd.Timedelta(hours=4), "Breaches reviewed; funding plan attached")
    wf.run_event(live.run["run_id"], "APPROVED", reviewer, created + pd.Timedelta(hours=7), "Approved for treasury committee")

    # access control is enforced and audited: an account holder may only see its own entity
    holders = users[users["role"] == "ACCOUNT_HOLDER"].sort_values("user_id")
    h = holders.iloc[0]
    other = holders.iloc[1]["entity_id"]
    wf.view_entity(h["user_id"], h["entity_id"], created + pd.Timedelta(hours=8))
    try:
        wf.view_entity(h["user_id"], other, created + pd.Timedelta(hours=8, minutes=1))
    except WorkflowError:
        pass

    # 6. actual versus forecast for every version
    exc = ds["exception"]
    dq_items = set(exc.loc[exc["exception_type"].isin(["DUPLICATE_CASH_FLOW", "MIXED_CURRENCY"]), "record_id"])
    ctx = ForecastContext(ds, cfg, fx)
    fva, attr = compare_all(ctx, fx, ds, dq_items, cfg.actuals_end)
    ds["forecast_vs_actual"] = fva
    ds["variance_attribution"] = attr
    return conform_dataset(ds)
