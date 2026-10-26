"""Historical forecast versions produced by the LEGACY process (before CashPilot).

One run per weekly cutoff, each evaluated under the scenario versions effective that day.
Lifecycle events follow the documented workflow (analyst prepares, a different risk reviewer
approves). Two documented deviations:
  * benign re-runs: version 001 left out the stress scenario, the reviewer rejected it and the
    analyst re-ran it as version 002 the same afternoon;
  * look-ahead runs (labelled anomalies): the weekly job failed and was re-run a week late,
    reading the latest data while still claiming the original cutoff.
"""

from __future__ import annotations

import pandas as pd

from cashpilot.core import ids
from cashpilot.core.config import Config
from cashpilot.dataset import Dataset
from cashpilot.engine.forecast import ForecastContext, RunResult, RunSpec, create_run
from cashpilot.generate.anomalies import weekly_cutoffs
from cashpilot.generate.master import SYSTEM_USER

LEAK_DAYS = 7
RUN_TABLES = ["forecast_run", "forecast_run_scenario", "forecast_run_item", "forecast_run_balance_input",
              "forecast_run_fx_input", "forecast_position", "scenario_assumption_effect"]


class RunLog:
    """Collects run results and lifecycle events, then turns them into tables."""

    def __init__(self):
        self.results: list[RunResult] = []
        self.events: list[dict] = []

    def add(self, result: RunResult, steps: list[tuple]) -> None:
        self.results.append(result)
        state = None
        for ts, event, actor, comment in steps:
            self.events.append({"run_id": result.run["run_id"], "event_ts": ts, "event_type": event, "from_status": state,
                                "to_status": event, "actor_id": actor, "comment": comment})
            state = event

    def tables(self) -> dict[str, pd.DataFrame]:
        out = {
            "forecast_run": pd.DataFrame([r.run for r in self.results]),
            "forecast_run_scenario": pd.concat([r.scenarios for r in self.results], ignore_index=True),
            "forecast_run_item": pd.concat([r.items for r in self.results], ignore_index=True),
            "forecast_run_balance_input": pd.concat([r.balances for r in self.results], ignore_index=True),
            "forecast_run_fx_input": pd.concat([r.fx for r in self.results], ignore_index=True),
            "forecast_position": pd.concat([r.positions for r in self.results], ignore_index=True),
            "scenario_assumption_effect": pd.concat([r.effects for r in self.results], ignore_index=True),
        }
        out["forecast_run_event"] = pd.DataFrame(self.events)
        return out


def standard_steps(created: pd.Timestamp, preparer: str, approver: str, approve_after=pd.Timedelta(hours=6, minutes=45)):
    return [
        (created, "CREATED", preparer, None),
        (created + pd.Timedelta(minutes=5), "COMPLETED", SYSTEM_USER, None),
        (created + pd.Timedelta(hours=1, minutes=15), "SUBMITTED", preparer, None),
        (created + approve_after, "APPROVED", approver, "Reviewed scenario outputs and breach list"),
    ]


def build_history(cfg: Config, ds: Dataset, ctx: ForecastContext, leaky: list, benign: list, log: RunLog) -> None:
    users = ds["app_user"]
    analysts = users.loc[users["role"] == "OPS_ANALYST", "user_id"].tolist()
    reviewers = users.loc[users["role"] == "RISK_REVIEWER", "user_id"].tolist()
    leaky, benign = set(map(pd.Timestamp, leaky)), set(map(pd.Timestamp, benign))
    for k, cutoff in enumerate(weekly_cutoffs(cfg)):
        analyst, reviewer = analysts[k % len(analysts)], reviewers[k % len(reviewers)]
        scen = ctx.effective_scenarios(cutoff)
        created = cutoff + pd.Timedelta(hours=8, minutes=15)
        if cutoff in benign:
            first = create_run(ctx, RunSpec(cutoff, 1, "LEGACY", "SCHEDULED", analyst, created, scen[:2]))
            log.add(first, standard_steps(created, analyst, reviewer)[:3] + [
                (cutoff + pd.Timedelta(hours=14), "REJECTED", reviewer, "Stress scenario missing; re-run with the full scenario set")])
            again = cutoff + pd.Timedelta(hours=15)
            second = create_run(ctx, RunSpec(cutoff, 2, "LEGACY", "RERUN", analyst, again, scen, supersedes=first.run["run_id"]))
            log.add(second, standard_steps(again, analyst, reviewer, approve_after=pd.Timedelta(hours=19)))
        elif cutoff in leaky:
            late = cutoff + pd.Timedelta(days=LEAK_DAYS, hours=9)
            result = create_run(ctx, RunSpec(cutoff, 1, "LEGACY", "SCHEDULED", analyst, late, scen, leak_days=LEAK_DAYS))
            log.add(result, standard_steps(late, analyst, reviewer, approve_after=pd.Timedelta(hours=5)))
        else:
            result = create_run(ctx, RunSpec(cutoff, 1, "LEGACY", "SCHEDULED", analyst, created, scen))
            log.add(result, standard_steps(created, analyst, reviewer))


def finalise_run_tables(cfg: Config, tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    ev = tables["forecast_run_event"].copy()
    ev["x_order"] = range(len(ev))
    ev = ev.sort_values(["event_ts", "run_id", "x_order"], kind="mergesort").reset_index(drop=True)
    ev["event_id"] = ids.sequence("FRE", cfg.cycle_year, 6, len(ev))
    runs = tables["forecast_run"].copy()
    runs["status_at_end"] = runs["run_id"].map(ev.groupby("run_id")["to_status"].last())
    tables = dict(tables)
    tables["forecast_run_event"] = ev
    tables["forecast_run"] = runs.sort_values("run_id").reset_index(drop=True)
    return tables
