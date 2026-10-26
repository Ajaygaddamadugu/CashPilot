"""Role-based workflow for forecast runs and exceptions.

* Permission matrix per role; every attempted action is written to ``audit_event``
  (ALLOWED or DENIED), so access decisions are traceable too.
* State changes follow the lifecycles in the data dictionary and are *appended* as events;
  nothing is updated in place except the derived ``status_at_end`` snapshot.
* Four-eyes: a run's approver must differ from its preparer and submitter.
* A run cannot be approved while it has an open CRITICAL exception, or a HIGH exception
  that is neither resolved nor waived. Waivers need a risk reviewer and a justification.
* Account holders may only view their own entity.
"""

from __future__ import annotations

import warnings

import pandas as pd

from cashpilot.core.config import Config
from cashpilot.dataset import Dataset
from cashpilot.schema import load_schema

PERMISSIONS = {
    "VIEW_ENTITY": {"ACCOUNT_HOLDER", "OPS_ANALYST", "RISK_REVIEWER", "SYS_ADMIN"},
    "CREATE_RUN": {"OPS_ANALYST", "SYSTEM"},
    "SUBMIT_RUN": {"OPS_ANALYST"},
    "APPROVE_RUN": {"RISK_REVIEWER"},
    "REJECT_RUN": {"RISK_REVIEWER"},
    "SUPERSEDE_RUN": {"SYSTEM", "RISK_REVIEWER"},
    "ASSIGN_EXCEPTION": {"SYSTEM", "OPS_ANALYST"},
    "ESCALATE_EXCEPTION": {"OPS_ANALYST"},
    "RESOLVE_EXCEPTION": {"OPS_ANALYST", "RISK_REVIEWER"},
    "WAIVE_EXCEPTION": {"RISK_REVIEWER"},
}
RUN_ACTIONS = {"CREATED": "CREATE_RUN", "COMPLETED": "CREATE_RUN", "SUBMITTED": "SUBMIT_RUN", "APPROVED": "APPROVE_RUN",
               "REJECTED": "REJECT_RUN", "SUPERSEDED": "SUPERSEDE_RUN"}
EXC_ACTIONS = {"RAISED": "ASSIGN_EXCEPTION", "ASSIGNED": "ASSIGN_EXCEPTION", "ESCALATED": "ESCALATE_EXCEPTION",
               "RESOLVED": "RESOLVE_EXCEPTION", "WAIVED": "WAIVE_EXCEPTION"}


class WorkflowError(Exception):
    pass


class Workflow:
    def __init__(self, ds: Dataset, cfg: Config):
        self.ds = ds
        self.cfg = cfg
        users = ds["app_user"].set_index("user_id")
        self.role = users["role"].to_dict()
        self.home = users["entity_id"].to_dict()
        lc = load_schema().lifecycles
        self.run_transitions = {(e, s): t for e, s, t in lc["forecast_run"].transitions}
        self.exc_transitions = {(e, s): t for e, s, t in lc["exception"].transitions}
        for name in ("exception", "exception_event", "audit_event"):
            if name not in ds:
                ds[name] = pd.DataFrame(columns=load_schema().table(name).column_names)

    # ------------------------------------------------------------------ helpers
    def _next_id(self, table: str, column: str, prefix: str, width: int) -> str:
        existing = self.ds[table][column]
        n = int(existing.str[-width:].astype(int).max()) + 1 if len(existing) else 1
        return f"{prefix}-{self.cfg.cycle_year}-{n:0{width}d}"

    def _append(self, table: str, row: dict) -> None:
        with warnings.catch_warnings():  # optional columns are often all-null
            warnings.simplefilter("ignore", FutureWarning)
            self.ds[table] = pd.concat([self.ds[table], pd.DataFrame([row])], ignore_index=True)

    def audit(self, actor: str, action: str, target: str, ts, allowed: bool, detail: str | None = None) -> None:
        self._append("audit_event", {"event_id": self._next_id("audit_event", "event_id", "AUD", 6), "event_ts": pd.Timestamp(ts),
                                     "actor_id": actor, "action": action, "target_id": target,
                                     "outcome": "ALLOWED" if allowed else "DENIED", "detail": detail})

    def authorise(self, actor: str, action: str, target: str, ts, entity: str | None = None) -> None:
        role = self.role.get(actor)
        reason = None
        if role not in PERMISSIONS[action]:
            reason = f"role {role} may not {action.lower().replace('_', ' ')}"
        elif role == "ACCOUNT_HOLDER" and entity is not None and self.home.get(actor) != entity:
            reason = f"account holder of {self.home.get(actor)} may not view {entity}"
        self.audit(actor, action, target, ts, reason is None, reason)
        if reason:
            raise WorkflowError(reason)

    # --------------------------------------------------------------------- runs
    def run_status(self, run_id: str) -> str | None:
        ev = self.ds["forecast_run_event"]
        ev = ev[ev["run_id"] == run_id]
        return ev.sort_values(["event_ts", "event_id"])["to_status"].iloc[-1] if len(ev) else None

    def run_event(self, run_id: str, event: str, actor: str, ts, comment: str | None = None) -> None:
        self.authorise(actor, RUN_ACTIONS[event], run_id, ts)
        state = self.run_status(run_id)
        if (event, state) not in self.run_transitions:
            raise WorkflowError(f"{run_id}: cannot {event} from {state}")
        if event == "APPROVED":
            self._check_approval(run_id, actor)
        self._append("forecast_run_event", {"event_id": self._next_id("forecast_run_event", "event_id", "FRE", 6), "run_id": run_id,
                                            "event_ts": pd.Timestamp(ts), "event_type": event, "from_status": state,
                                            "to_status": self.run_transitions[(event, state)], "actor_id": actor, "comment": comment})
        runs = self.ds["forecast_run"]
        runs.loc[runs["run_id"] == run_id, "status_at_end"] = self.run_transitions[(event, state)]

    def _check_approval(self, run_id: str, approver: str) -> None:
        ev = self.ds["forecast_run_event"]
        makers = set(ev.loc[(ev["run_id"] == run_id) & ev["event_type"].isin(["CREATED", "SUBMITTED"]), "actor_id"])
        if approver in makers:
            raise WorkflowError(f"{run_id}: four-eyes rule - {approver} prepared or submitted this run")
        exc = self.ds["exception"]
        linked = exc[(exc["run_id"] == run_id)]
        blocking = linked[((linked["severity"] == "CRITICAL") & ~linked["status_at_end"].isin(["RESOLVED"])) |
                          ((linked["severity"] == "HIGH") & ~linked["status_at_end"].isin(["RESOLVED", "WAIVED"]))]
        if len(blocking):
            raise WorkflowError(f"{run_id}: blocked by open exceptions {', '.join(blocking['exception_id'])}")

    def add_run(self, result, steps: list[tuple]) -> None:
        """Store a new run's tables (append-only) and play its lifecycle steps."""
        r = result.run | {"status_at_end": None}
        self._append("forecast_run", r)
        for table, frame in (("forecast_run_scenario", result.scenarios), ("forecast_run_item", result.items),
                             ("forecast_run_balance_input", result.balances), ("forecast_run_fx_input", result.fx),
                             ("forecast_position", result.positions), ("scenario_assumption_effect", result.effects)):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                self.ds[table] = pd.concat([self.ds[table], frame], ignore_index=True)
        for ts, event, actor, comment in steps:
            self.run_event(r["run_id"], event, actor, ts, comment)

    # --------------------------------------------------------------- exceptions
    def raise_exceptions(self, findings: pd.DataFrame, ts) -> list[str]:
        new_ids = []
        for _, f in findings.iterrows():
            exc_id = self._next_id("exception", "exception_id", "EXC", 6)
            self._append("exception", {**{k: (None if pd.isna(v) else v) for k, v in f.items()}, "exception_id": exc_id,
                                       "detected_at": pd.Timestamp(ts), "status_at_end": None})
            self.exception_event(exc_id, "RAISED", "USR-0001", ts, f["details"])
            new_ids.append(exc_id)
        return new_ids

    def exception_status(self, exc_id: str) -> str | None:
        ev = self.ds["exception_event"]
        ev = ev[ev["exception_id"] == exc_id]
        return ev.sort_values(["event_ts", "event_id"])["to_status"].iloc[-1] if len(ev) else None

    def exception_event(self, exc_id: str, event: str, actor: str, ts, comment: str | None = None) -> None:
        self.authorise(actor, EXC_ACTIONS[event], exc_id, ts)
        state = self.exception_status(exc_id)
        if (event, state) not in self.exc_transitions:
            raise WorkflowError(f"{exc_id}: cannot {event} from {state}")
        if event == "WAIVED" and not comment:
            raise WorkflowError("a waiver needs a written justification")
        self._append("exception_event", {"event_id": self._next_id("exception_event", "event_id", "EXE", 6),
                                         "exception_id": exc_id, "event_ts": pd.Timestamp(ts), "event_type": event,
                                         "from_status": state, "to_status": self.exc_transitions[(event, state)],
                                         "actor_id": actor, "comment": comment})
        exc = self.ds["exception"]
        exc.loc[exc["exception_id"] == exc_id, "status_at_end"] = self.exc_transitions[(event, state)]

    # ------------------------------------------------------------------- views
    def view_entity(self, actor: str, entity: str, ts) -> pd.DataFrame:
        self.authorise(actor, "VIEW_ENTITY", entity, ts, entity=entity)
        pos = self.ds.get("entity_cash_position")
        return pos[pos["entity_id"] == entity] if pos is not None else pd.DataFrame()
