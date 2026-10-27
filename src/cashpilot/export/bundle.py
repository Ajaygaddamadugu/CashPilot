"""Write a complete dataset bundle (Step 9 of the brief).

<out>/
  csv/<table>.csv              every dataset table
  json/<table>.json            same tables as JSON arrays (amounts as exact decimal strings)
  sql/schema.sql               DDL with primary keys, foreign keys and CHECK constraints
  sql/append_only_sqlite.sql   triggers that make history tables append-only (SQLite)
  sql/seed.sql                 INSERTs in dependency order
  ground_truth/anomalies.*     labels for injected anomalies - kept apart from the data
  data_dictionary.md           field-level documentation
  generation_config.json       the exact profile used (seed, volumes, policies)
  validation_summary.md|json   Step 8 results
  reports/                     evaluation, liquidity outlook, data profile
  README.md                    what is in the bundle and how to regenerate it
  manifest.json                row counts and SHA-256 of every file above (no timestamps)
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from cashpilot import __version__
from cashpilot.core.config import Config
from cashpilot.dataset import GROUND_TRUTH_ALIAS, GROUND_TRUTH_NAME, GROUND_TRUTH_TABLE, Dataset, write_csv, write_ground_truth_csv, write_json, write_json_table
from cashpilot.export.docs import render_data_dictionary
from cashpilot.export.sql import write_sql
from cashpilot.quality.validate import Report, write_summary
from cashpilot.report.markdown import data_profile_report, evaluation_report, liquidity_report
from cashpilot.schema import load_schema

PROVENANCE = ("Fully synthetic. No external dataset, API or personal data was used. Company, bank and person "
              "names are fictional; FX starting levels are round illustrative numbers. ISO 4217 is used only as a "
              "public reference for currency codes and decimal places.")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rows(path: Path) -> int | None:
    if path.suffix == ".csv":
        with open(path, "rb") as fh:
            return sum(1 for _ in fh) - 1
    if path.suffix == ".json" and path.parent.name in ("json", "ground_truth"):
        return len(json.loads(path.read_text(encoding="utf-8")))
    return None


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    return str(o)


def dataset_readme(ds: Dataset, cfg: Config, validation_ok: bool | None) -> str:
    schema = load_schema()
    lines = [
        f"# CashPilot dataset — `{cfg.profile}` profile", "",
        f"Synthetic treasury data for a {cfg.volumes['legal_entities']}-entity group, generated with seed **{cfg.seed}**.",
        "", "Regenerate byte-for-byte with:", "", "```", f"cashpilot all --profile {cfg.profile} --seed {cfg.seed}", "```", "",
        "## Layout", "",
        "| Path | Content |", "|---|---|",
        "| `csv/` | One CSV per table (UTF-8, `\\n` line endings, header row) |",
        "| `json/` | The same tables as JSON arrays; money and rates are exact decimal strings |",
        "| `sql/` | `schema.sql` (DDL with PK/FK/CHECK), `append_only_sqlite.sql`, `seed.sql` |",
        "| `ground_truth/` | `ground_truth.csv|json`: labels of the injected anomalies and negative controls (`anomalies.*` are identical aliases kept for older consumers). **Not an input**: never use as a feature |",
        "| `data_dictionary.md` | Every field: type, required, allowed values, units, uniqueness, validation rule |",
        "| `validation_summary.md` | Step 8 checks and their results |",
        "| `reports/` | Evaluation, 13-week liquidity outlook, data profile |",
        "| `manifest.json` | Row counts and SHA-256 checksums of every file |", "",
        f"Validation: **{'PASS' if validation_ok else 'see validation_summary.md'}**.", "",
        "## Tables", "", "| Table | Layer | Rows | Description |", "|---|---|---|---|",
    ]
    for name in schema.topological_order():
        if name in ds:
            t = schema.table(name)
            lines.append(f"| `{name}` | {t.layer} | {len(ds[name]):,} | {t.description} |")
    lines += ["", "## Provenance", "", PROVENANCE, ""]
    return "\n".join(lines)


def write_bundle(ds: Dataset, cfg: Config, out: Path, formats=("csv", "json", "sql"), validation: Report | None = None,
                 baseline_validation: Report | None = None, evaluation: dict | None = None) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if "csv" in formats:
        write_csv(ds, out / "csv")
    if "json" in formats:
        write_json(ds, out / "json")
    if "sql" in formats:
        write_sql(ds, out / "sql")
    if ds.ground_truth is not None:
        write_ground_truth_csv(ds, out / "ground_truth")
        gt_json = out / "ground_truth" / f"{GROUND_TRUTH_NAME}.json"
        write_json_table(ds.ground_truth, load_schema().table(GROUND_TRUTH_TABLE), gt_json)
        shutil.copyfile(gt_json, out / "ground_truth" / f"{GROUND_TRUTH_ALIAS}.json")
    _write_text(out / "data_dictionary.md", render_data_dictionary(load_schema()))
    _write_text(out / "generation_config.json", json.dumps(cfg.raw, indent=2, sort_keys=True, default=str) + "\n")
    if validation is not None:
        write_summary(validation, out / "validation_summary.md", out / "validation_summary.json", cfg.profile, baseline_validation)
    if evaluation is not None:
        _write_text(out / "reports" / "evaluation.md", evaluation_report(evaluation))
        _write_text(out / "reports" / "liquidity_outlook.md", liquidity_report(evaluation, ds))
        _write_text(out / "reports" / "data_profile.md", data_profile_report(evaluation))
        _write_text(out / "reports" / "evaluation.json", json.dumps(evaluation, indent=2, default=_json_default) + "\n")
    _write_text(out / "README.md", dataset_readme(ds, cfg, None if validation is None else validation.ok))
    return write_manifest(ds, cfg, out)


def write_manifest(ds: Dataset, cfg: Config, out: Path) -> dict:
    files = []
    for path in sorted(p for p in out.rglob("*") if p.is_file() and p.name not in ("manifest.json",)
                       and not p.name.startswith("reproducibility")):
        files.append({"path": path.relative_to(out).as_posix(), "rows": _rows(path), "bytes": path.stat().st_size, "sha256": _sha256(path)})
    manifest = {
        "dataset": "CashPilot synthetic treasury dataset",
        "profile": cfg.profile,
        "seed": cfg.seed,
        "command": f"cashpilot all --profile {cfg.profile} --seed {cfg.seed}",
        "config_sha256": cfg.config_hash(),
        "generator": {"package": "cashpilot", "version": __version__, "python": platform.python_version(),
                      "numpy": np.__version__, "pandas": pd.__version__, "pyyaml": yaml.__version__},
        "provenance": PROVENANCE,
        "external_sources": [],
        "tables": {name: {"rows": int(len(df)), "layer": load_schema().table(name).layer} for name, df in ds.tables.items()},
        "files": files,
    }
    _write_text(out / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    return manifest
