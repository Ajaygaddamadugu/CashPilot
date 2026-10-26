"""Command-line interface: ``cashpilot <command>`` (or ``python -m cashpilot``).

Pipeline
  all            generate, process, validate, evaluate and export a dataset in one go
  generate       source data + labelled anomalies + legacy forecast history (CSV + ground truth)
  run            CashPilot processing of a generated dataset
  validate       Step 8 checks -> validation_summary.md/json
  evaluate       metrics against the ground truth -> reports/
  export         (re)write JSON/SQL, docs and manifest from the CSV tables
  repro-check    regenerate twice with the same seed and compare checksums
  docs           regenerate docs/DATA_DICTIONARY.md

Workflow (acts as a user; every action is permission-checked and audited)
  forecast       create a CashPilot forecast run as of a cutoff date
  run-event      submit / approve / reject a run
  exceptions     list exceptions
  exception      assign / escalate / resolve / waive an exception
  view-entity    show an entity's cash position (account holders: own entity only)
  explain        drill into the variance of one run, entity and week
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

DEFAULT_OUT = "data/{profile}"


def _out(args) -> Path:
    return Path(args.out or DEFAULT_OUT.format(profile=args.profile))


def _now(args) -> pd.Timestamp:
    return pd.Timestamp(args.at) if getattr(args, "at", None) else pd.Timestamp.now(tz="UTC").tz_localize(None).floor("s")


def _save(ds, path: Path) -> None:
    from cashpilot.dataset import conform_dataset, write_csv
    write_csv(conform_dataset(ds), Path(path) / "csv")
    print(f"tables updated in {path}/csv - run `cashpilot export --data {path}` to refresh JSON/SQL and the manifest")


# ------------------------------------------------------------------- pipeline

def cmd_all(args) -> int:
    from cashpilot.core.config import load_config
    from cashpilot.pipeline import run_all
    cfg = load_config(args.profile, args.seed)
    result = run_all(cfg, _out(args), tuple(args.formats.split(",")))
    det = result["evaluation"].get("detection", {}).get("by_issue", [])
    for r in det:
        print(f"  {r['issue_type']:<22} recall {r['recall']:.0%}  precision {r['precision']:.0%}")
    return 0 if result["validation"] == "PASS" else 1


def cmd_generate(args) -> int:
    from cashpilot.core.config import load_config
    from cashpilot.dataset import write_csv, write_ground_truth_csv
    from cashpilot.generate.pipeline import generate_dataset
    cfg = load_config(args.profile, args.seed)
    ds, _, _ = generate_dataset(cfg)
    out = _out(args)
    write_csv(ds, out / "csv")
    write_ground_truth_csv(ds, out / "ground_truth")
    (out / "generation_config.json").write_text(json.dumps(cfg.raw, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"generated {sum(len(v) for v in ds.tables.values()):,} rows in {len(ds.tables)} tables -> {out}")
    return 0


def cmd_run(args) -> int:
    from cashpilot.engine.process import process
    from cashpilot.pipeline import load_dataset
    ds, cfg = load_dataset(args.data)
    out = process(ds, cfg)
    _save(out, Path(args.data))
    return 0


def cmd_validate(args) -> int:
    from cashpilot.engine.positions import fx_book
    from cashpilot.pipeline import load_dataset
    from cashpilot.quality.validate import write_summary, validate
    ds, cfg = load_dataset(args.data)
    report = validate(ds, cfg, fx_book(ds, cfg.policy), ds.ground_truth)
    write_summary(report, Path(args.data) / "validation_summary.md", Path(args.data) / "validation_summary.json", cfg.profile)
    frame = report.frame()
    print(f"{len(frame)} checks: {frame['status'].value_counts().to_dict()} -> {'PASS' if report.ok else 'FAIL'}")
    return 0 if report.ok else 1


def cmd_evaluate(args) -> int:
    from cashpilot.evaluate.metrics import evaluate
    from cashpilot.pipeline import load_dataset
    from cashpilot.report.markdown import data_profile_report, evaluation_report, liquidity_report
    ds, cfg = load_dataset(args.data)
    ev = evaluate(ds, cfg, ds.ground_truth)
    rep = Path(args.data) / "reports"
    rep.mkdir(exist_ok=True)
    (rep / "evaluation.md").write_text(evaluation_report(ev), encoding="utf-8", newline="\n")
    (rep / "liquidity_outlook.md").write_text(liquidity_report(ev, ds), encoding="utf-8", newline="\n")
    (rep / "data_profile.md").write_text(data_profile_report(ev), encoding="utf-8", newline="\n")
    print(f"reports written to {rep}")
    return 0


def cmd_export(args) -> int:
    from cashpilot.engine.positions import fx_book
    from cashpilot.evaluate.metrics import evaluate
    from cashpilot.export.bundle import write_bundle
    from cashpilot.pipeline import load_dataset
    from cashpilot.quality.validate import validate
    ds, cfg = load_dataset(args.data)
    report = validate(ds, cfg, fx_book(ds, cfg.policy), ds.ground_truth)
    manifest = write_bundle(ds, cfg, Path(args.data), tuple(args.formats.split(",")), report, None, evaluate(ds, cfg, ds.ground_truth))
    print(f"exported {len(manifest['files'])} files; manifest refreshed")
    return 0


def cmd_repro(args) -> int:
    from cashpilot.evaluate.repro import repro_check
    from cashpilot.report.markdown import reproducibility_report
    work = Path(args.workdir or f"out/repro-{args.profile}")
    result = repro_check(args.profile, args.seed, work, tuple(args.formats.split(",")))
    target = Path(args.out or DEFAULT_OUT.format(profile=args.profile))
    target.mkdir(parents=True, exist_ok=True)
    (target / "reproducibility.md").write_text(reproducibility_report(result), encoding="utf-8", newline="\n")
    (target / "reproducibility.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"{result['files_identical']}/{result['files_compared']} files identical -> {'IDENTICAL' if result['identical'] else 'DIFFERENT'}")
    return 0 if result["identical"] else 1


def cmd_docs(args) -> int:
    from cashpilot.export.docs import render_data_dictionary
    from cashpilot.schema import load_schema
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "DATA_DICTIONARY.md"
    path.write_text(render_data_dictionary(load_schema()), encoding="utf-8", newline="\n")
    print(f"wrote {path}")
    return 0


# ------------------------------------------------------------------- workflow

def _workflow(args):
    from cashpilot.engine.workflow import Workflow
    from cashpilot.pipeline import load_dataset
    ds, cfg = load_dataset(args.data)
    return ds, cfg, Workflow(ds, cfg)


def cmd_forecast(args) -> int:
    from cashpilot.engine.forecast import ForecastContext, RunSpec, create_run
    from cashpilot.engine.positions import fx_book
    from cashpilot.engine.workflow import WorkflowError
    ds, cfg, wf = _workflow(args)
    cutoff = pd.Timestamp(args.cutoff)
    ts = _now(args)
    try:
        wf.authorise(args.as_user, "CREATE_RUN", f"cutoff {cutoff.date()}", ts)
    except WorkflowError as e:
        print(f"DENIED: {e}")
        _save(ds, Path(args.data))
        return 2
    runs = ds["forecast_run"]
    same = runs[runs["cutoff_date"] == cutoff]
    version = int(same["version"].max()) + 1 if len(same) else 1
    ctx = ForecastContext(ds, cfg, fx_book(ds, cfg.policy))
    result = create_run(ctx, RunSpec(cutoff, version, "CASHPILOT", args.purpose, args.as_user, ts, ctx.effective_scenarios(cutoff)))
    wf.add_run(result, [(ts, "CREATED", args.as_user, args.comment), (ts + pd.Timedelta(seconds=1), "COMPLETED", "USR-0001", None)])
    group = result.positions.groupby(["scenario_id", "position_date"])["closing_available_usd"].sum().groupby("scenario_id").min() / 100
    print(f"created {result.run['run_id']} ({len(result.items)} items, input hash {result.run['input_hash'][:12]}…)")
    for sid, v in group.items():
        breaches = result.positions[(result.positions["scenario_id"] == sid) & result.positions["breach_flag"]]["entity_id"].nunique()
        print(f"  {sid:<16} lowest group available USD {v:,.0f}; entities below buffer: {breaches}")
    _save(ds, Path(args.data))
    return 0


def cmd_run_event(args) -> int:
    from cashpilot.engine.workflow import WorkflowError
    ds, _, wf = _workflow(args)
    try:
        wf.run_event(args.run, args.event, args.as_user, _now(args), args.comment)
        print(f"{args.run}: {args.event} by {args.as_user}")
        code = 0
    except WorkflowError as e:
        print(f"REFUSED: {e}")
        code = 2
    _save(ds, Path(args.data))
    return code


def cmd_exceptions(args) -> int:
    from cashpilot.pipeline import load_dataset
    ds, _ = load_dataset(args.data)
    exc = ds["exception"]
    if args.status:
        exc = exc[exc["status_at_end"] == args.status]
    if args.type:
        exc = exc[exc["exception_type"] == args.type]
    cols = ["exception_id", "rule_id", "exception_type", "severity", "record_id", "decision", "status_at_end"]
    print(exc[cols].head(args.limit).to_string(index=False))
    print(f"({len(exc)} exception{'s' if len(exc) != 1 else ''})")
    return 0


def cmd_exception(args) -> int:
    from cashpilot.engine.workflow import WorkflowError
    ds, _, wf = _workflow(args)
    try:
        wf.exception_event(args.id, args.event, args.as_user, _now(args), args.comment)
        print(f"{args.id}: {args.event} by {args.as_user}")
        code = 0
    except WorkflowError as e:
        print(f"REFUSED: {e}")
        code = 2
    _save(ds, Path(args.data))
    return code


def cmd_view_entity(args) -> int:
    from cashpilot.engine.workflow import WorkflowError
    ds, _, wf = _workflow(args)
    try:
        pos = wf.view_entity(args.as_user, args.entity, _now(args))
        tail = pos.tail(args.days)[["position_date", "available_usd", "restricted_usd", "min_buffer_usd", "headroom_usd", "fx_status"]].copy()
        for c in ("available_usd", "restricted_usd", "min_buffer_usd", "headroom_usd"):
            tail[c] = (tail[c] / 100).map("{:,.0f}".format)
        print(tail.to_string(index=False))
        code = 0
    except WorkflowError as e:
        print(f"DENIED: {e}")
        code = 2
    _save(ds, Path(args.data))
    return code


def cmd_explain(args) -> int:
    from cashpilot.pipeline import load_dataset
    ds, _ = load_dataset(args.data)
    fva = ds["forecast_vs_actual"]
    row = fva[(fva["run_id"] == args.run) & (fva["entity_id"] == args.entity) & (fva["week_no"] == args.week) & fva["scenario_id"].str.startswith("SCN-BASE")]
    if row.empty:
        print("no comparison for that run/entity/week (the week may not have elapsed yet)")
        return 1
    r = row.iloc[0]
    print(f"{args.run} {args.entity} week {args.week} ({r['week_start']:%Y-%m-%d}..{r['week_end']:%Y-%m-%d})")
    print(f"  forecast {r['forecast_net_usd'] / 100:>16,.2f}\n  actual   {r['actual_net_usd'] / 100:>16,.2f}\n  variance {r['variance_usd'] / 100:>16,.2f}")
    va = ds["variance_attribution"]
    va = va[(va["run_id"] == args.run) & (va["entity_id"] == args.entity) & (va["week_no"] == args.week)]
    for driver, g in va.groupby("driver"):
        print(f"  {driver:<17} {g['amount_usd'].sum() / 100:>16,.2f}  ({len(g)} records)")
        top = g.reindex(g["amount_usd"].abs().sort_values(ascending=False).index).head(args.top)
        for t in top.itertuples():
            print(f"      {t.amount_usd / 100:>14,.2f}  item {t.cf_id or '-'}  posting {t.ledger_entry_id or '-'}")
    return 0


# --------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cashpilot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def profile_args(p):
        p.add_argument("--profile", default="starter", help="starter | full | path to a profile YAML (default: starter)")
        p.add_argument("--seed", type=int, default=None, help="override the profile seed (default 20261022)")
        p.add_argument("--out", default=None, help="output folder (default: data/<profile>)")

    p = sub.add_parser("all", help="generate, process, validate, evaluate and export")
    profile_args(p)
    p.add_argument("--formats", default="csv,json,sql")
    p.set_defaults(func=cmd_all)
    p = sub.add_parser("generate", help="source data, labelled anomalies and legacy history")
    profile_args(p)
    p.set_defaults(func=cmd_generate)
    for name, func, text in (("run", cmd_run, "CashPilot processing of a generated dataset"),
                             ("validate", cmd_validate, "run the Step 8 validation suite"),
                             ("evaluate", cmd_evaluate, "metrics against the ground truth")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--data", required=True, help="dataset folder")
        p.set_defaults(func=func)
    p = sub.add_parser("export", help="write JSON/SQL, docs, reports and manifest from the CSV tables")
    p.add_argument("--data", required=True)
    p.add_argument("--formats", default="csv,json,sql")
    p.set_defaults(func=cmd_export)
    p = sub.add_parser("repro-check", help="regenerate twice with the same seed and compare checksums")
    profile_args(p)
    p.add_argument("--workdir", default=None, help="scratch folder (default: out/repro-<profile>)")
    p.add_argument("--formats", default="csv,json,sql")
    p.set_defaults(func=cmd_repro)
    p = sub.add_parser("docs", help="regenerate docs/DATA_DICTIONARY.md from the data dictionary")
    p.add_argument("--out", default="docs")
    p.set_defaults(func=cmd_docs)

    def act(p):
        p.add_argument("--data", required=True, help="dataset folder")
        p.add_argument("--as-user", dest="as_user", required=True, help="user ID, e.g. USR-0003")
        p.add_argument("--at", default=None, help="action timestamp (default: now, UTC)")
        p.add_argument("--comment", default=None)

    p = sub.add_parser("forecast", help="create a CashPilot forecast run")
    act(p)
    p.add_argument("--cutoff", required=True)
    p.add_argument("--purpose", default="SCHEDULED", choices=["SCHEDULED", "RERUN", "REMEDIATION", "LIVE"])
    p.set_defaults(func=cmd_forecast)
    p = sub.add_parser("run-event", help="submit / approve / reject / supersede a run")
    act(p)
    p.add_argument("--run", required=True)
    p.add_argument("--event", required=True, choices=["SUBMITTED", "APPROVED", "REJECTED", "SUPERSEDED"])
    p.set_defaults(func=cmd_run_event)
    p = sub.add_parser("exceptions", help="list exceptions")
    p.add_argument("--data", required=True)
    p.add_argument("--status", default=None)
    p.add_argument("--type", default=None)
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_exceptions)
    p = sub.add_parser("exception", help="assign / escalate / resolve / waive an exception")
    act(p)
    p.add_argument("--id", required=True)
    p.add_argument("--event", required=True, choices=["ASSIGNED", "ESCALATED", "RESOLVED", "WAIVED"])
    p.set_defaults(func=cmd_exception)
    p = sub.add_parser("view-entity", help="an entity's recent cash position")
    act(p)
    p.add_argument("--entity", required=True)
    p.add_argument("--days", type=int, default=10)
    p.set_defaults(func=cmd_view_entity)
    p = sub.add_parser("explain", help="variance drill-down for one run, entity and week")
    p.add_argument("--data", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--entity", required=True)
    p.add_argument("--week", type=int, required=True)
    p.add_argument("--top", type=int, default=3)
    p.set_defaults(func=cmd_explain)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
