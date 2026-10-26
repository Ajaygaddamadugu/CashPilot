"""Step 9/10: exports round-trip, SQL loads with constraints, output is byte-reproducible."""

import hashlib
import json
import sqlite3

import pandas as pd
import pytest

from cashpilot.core.config import load_config
from cashpilot.dataset import to_text
from cashpilot.engine.forecast import ForecastContext, recreate_run
from cashpilot.engine.positions import fx_book
from cashpilot.export.bundle import write_bundle
from cashpilot.generate.pipeline import generate_baseline
from cashpilot.pipeline import load_dataset
from cashpilot.schema import load_schema


@pytest.fixture(scope="module")
def bundle(pipeline, starter_cfg, tmp_path_factory):
    _, _, final = pipeline
    out = tmp_path_factory.mktemp("bundle")
    manifest = write_bundle(final, starter_cfg, out, ("csv", "json", "sql"))
    return out, manifest, final


def test_csv_round_trip_is_lossless(bundle):
    out, _, final = bundle
    loaded, _ = load_dataset(out)
    assert set(loaded.tables) == set(final.tables)
    for name in final.tables:
        pd.testing.assert_frame_equal(loaded[name], final[name], check_dtype=False, obj=name)
    assert loaded.ground_truth is not None and len(loaded.ground_truth) == len(final.ground_truth)


def test_json_mirrors_csv(bundle):
    out, _, final = bundle
    records = json.loads((out / "json" / "ledger_entry.json").read_text(encoding="utf-8"))
    assert len(records) == len(final["ledger_entry"])
    assert isinstance(records[0]["amount"], str)  # exact decimal strings, never floats


def test_sql_seed_loads_with_foreign_keys_and_append_only_history(bundle):
    out, _, final = bundle
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys = ON")
    for f in ("schema.sql", "append_only_sqlite.sql", "seed.sql"):
        con.executescript((out / "sql" / f).read_text(encoding="utf-8"))
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert con.execute("SELECT COUNT(*) FROM ledger_entry").fetchone()[0] == len(final["ledger_entry"])
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("DELETE FROM forecast_run_event")


def test_manifest_lists_every_file_with_counts_and_no_timestamps(bundle):
    out, manifest, final = bundle
    listed = {f["path"]: f for f in manifest["files"]}
    on_disk = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file() and p.name != "manifest.json"}
    assert set(listed) == on_disk
    assert listed["csv/ledger_entry.csv"]["rows"] == len(final["ledger_entry"])
    for path, f in listed.items():
        assert hashlib.sha256((out / path).read_bytes()).hexdigest() == f["sha256"]
    text = (out / "manifest.json").read_text(encoding="utf-8")
    assert "generated_at" not in text and manifest["external_sources"] == []


def test_stored_runs_are_recreated_exactly_from_the_exported_files(bundle):
    out, _, _ = bundle
    ds, cfg = load_dataset(out)
    ctx = ForecastContext(ds, cfg, fx_book(ds, cfg.policy))
    runs, scen = ds["forecast_run"], ds["forecast_run_scenario"]
    for run_id in (runs["run_id"].iloc[5], runs.query("run_purpose == 'LIVE'")["run_id"].iloc[0]):
        row = runs.set_index("run_id").loc[run_id].copy()
        row["run_id"] = run_id
        again = recreate_run(ctx, row, scen.loc[scen["run_id"] == run_id, "scenario_id"].tolist())
        assert (again.run["input_hash"], again.run["result_hash"]) == (row["input_hash"], row["result_hash"])


def _digests(ds):
    schema = load_schema()
    out = {}
    for name, df in ds.tables.items():
        t = schema.table(name)
        out[name] = hashlib.sha256(to_text(df, t).to_csv(index=False, lineterminator="\n").encode()).hexdigest()
    return out


def test_same_seed_gives_identical_bytes_and_another_seed_does_not():
    cfg = load_config("starter")
    a, _ = generate_baseline(cfg)
    b, _ = generate_baseline(load_config("starter"))
    c, _ = generate_baseline(load_config("starter", seed=cfg.seed + 1))
    assert _digests(a) == _digests(b)
    assert _digests(a)["ledger_entry"] != _digests(c)["ledger_entry"]
