"""Step 10: regenerate twice with the same seed and compare row counts and checksums."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from cashpilot.core.config import load_config
from cashpilot.pipeline import run_all


def compare_manifests(m1: dict, m2: dict) -> dict:
    f1 = {f["path"]: f for f in m1["files"]}
    f2 = {f["path"]: f for f in m2["files"]}
    files = []
    for path in sorted(set(f1) | set(f2)):
        a, b = f1.get(path), f2.get(path)
        match = bool(a and b and a["sha256"] == b["sha256"] and a["rows"] == b["rows"])
        files.append({"path": path, "rows": (a or b)["rows"], "sha256_run1": (a or {}).get("sha256", ""),
                      "sha256_run2": (b or {}).get("sha256", ""), "match": match})
    return {"files_compared": len(files), "files_identical": sum(f["match"] for f in files),
            "rows_compared": sum(f["rows"] or 0 for f in files), "identical": all(f["match"] for f in files), "files": files}


def repro_check(profile: str, seed: int | None, workdir: Path, formats=("csv", "json", "sql"), log=print) -> dict:
    cfg = load_config(profile, seed)
    manifests = []
    for i in (1, 2):
        out = Path(workdir) / f"run-{i}"
        if out.exists():
            shutil.rmtree(out)
        log(f"== run {i} -> {out}")
        manifests.append(run_all(cfg, out, formats, log=log)["manifest"])
    result = {"profile": cfg.profile, "seed": cfg.seed, **compare_manifests(*manifests)}
    (Path(workdir) / "comparison.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
