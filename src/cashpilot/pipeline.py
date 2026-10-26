"""End-to-end orchestration used by the CLI and the reproducibility check."""

from __future__ import annotations

import json
import time
from pathlib import Path

from cashpilot.core.config import Config
from cashpilot.dataset import Dataset, read_csv
from cashpilot.engine.positions import fx_book
from cashpilot.engine.process import process
from cashpilot.evaluate.metrics import evaluate
from cashpilot.export.bundle import write_bundle
from cashpilot.generate.pipeline import generate_dataset
from cashpilot.quality.validate import validate


def run_all(cfg: Config, out: Path, formats=("csv", "json", "sql"), log=print) -> dict:
    """Generate -> validate baseline -> inject/history -> CashPilot processing -> validate -> evaluate -> export."""
    t0 = time.time()
    log(f"[1/5] generating `{cfg.profile}` dataset (seed {cfg.seed})")
    generated, baseline, _ = generate_dataset(cfg)
    baseline_report = validate(baseline, cfg, fx_book(baseline, cfg.policy))
    log(f"      clean baseline: {len(baseline_report.checks)} checks, "
        f"{int(baseline_report.frame()['violations'].sum())} violations ({time.time() - t0:.0f}s)")
    log("[2/5] CashPilot: positions, audit, exceptions, remediation, live forecast, actual vs forecast")
    final = process(generated, cfg)
    log(f"      done ({time.time() - t0:.0f}s)")
    log("[3/5] validating")
    report = validate(final, cfg, fx_book(final, cfg.policy), generated.ground_truth)
    log("[4/5] evaluating against the ground truth")
    evaluation = evaluate(final, cfg, generated.ground_truth)
    log(f"[5/5] exporting {', '.join(formats)} to {out}")
    manifest = write_bundle(final, cfg, Path(out), formats, report, baseline_report, evaluation)
    status = "PASS" if report.ok else "FAIL"
    log(f"done in {time.time() - t0:.0f}s - validation {status}; {len(manifest['files'])} files written")
    return {"validation": status, "manifest": manifest, "evaluation": evaluation}


def load_dataset(path: Path) -> tuple[Dataset, Config]:
    """A bundle written by ``run_all`` (or ``generate``): tables, ground truth and its config."""
    path = Path(path)
    cfg = Config(json.loads((path / "generation_config.json").read_text(encoding="utf-8")))
    raw = cfg.raw
    for key in ("start_date", "actuals_end", "schedule_end"):
        raw["calendar"][key] = _date(raw["calendar"][key])
    raw["lifecycle"]["acquisition_date"] = _date(raw["lifecycle"]["acquisition_date"])
    raw["forecast"]["first_cutoff"] = _date(raw["forecast"]["first_cutoff"])
    raw["forecast"]["live_cutoff"] = _date(raw["forecast"]["live_cutoff"])
    return read_csv(path / "csv", path / "ground_truth"), cfg


def _date(value):
    import datetime as dt
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))
