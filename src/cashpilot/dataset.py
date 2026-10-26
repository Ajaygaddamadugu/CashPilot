"""A dataset is a dict of DataFrames shaped by the data dictionary.

Internal dtypes per dictionary type:
    string, decimal  -> object (str or None)
    int              -> Int64 (nullable)
    bool             -> boolean (nullable)
    date, timestamp  -> datetime64[ns] (naive, UTC)
    money            -> Int64 minor units
    rate             -> float64

Text form (CSV/JSON/SQL) is produced column by column with fixed formatters so the
output is byte-for-byte deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from cashpilot.core.money import format_minor, parse_major
from cashpilot.schema import Table, load_schema

GROUND_TRUTH_TABLE = "anomaly_label"


class Dataset:
    """Tables keyed by name. Ground truth is held separately and never mixed in."""

    def __init__(self, tables: dict[str, pd.DataFrame] | None = None, ground_truth: pd.DataFrame | None = None):
        self.tables: dict[str, pd.DataFrame] = dict(tables or {})
        self.ground_truth = ground_truth

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.tables[name]

    def __setitem__(self, name: str, df: pd.DataFrame) -> None:
        self.tables[name] = df

    def __contains__(self, name: str) -> bool:
        return name in self.tables

    def get(self, name: str, default=None):
        return self.tables.get(name, default)

    def copy(self) -> "Dataset":
        gt = None if self.ground_truth is None else self.ground_truth.copy()
        return Dataset({k: v.copy() for k, v in self.tables.items()}, gt)


# ----------------------------------------------------------------- conforming

def empty_frame(table: Table) -> pd.DataFrame:
    return conform(pd.DataFrame(columns=table.column_names), table)


def conform(df: pd.DataFrame, table: Table) -> pd.DataFrame:
    """Order columns as in the dictionary, add missing optional columns, coerce dtypes."""
    missing_required = [c.name for c in table.columns if c.required and c.name not in df.columns]
    if missing_required:
        raise ValueError(f"{table.name}: missing required columns {missing_required}")
    out = pd.DataFrame(index=df.index)
    for col in table.columns:
        s = df[col.name] if col.name in df.columns else pd.Series([None] * len(df), index=df.index, dtype="object")
        out[col.name] = _coerce(s, col.type)
    return out.reset_index(drop=True)


def _coerce(s: pd.Series, kind: str) -> pd.Series:
    if kind in ("string", "decimal"):
        return s.astype("object").where(s.notna(), None)
    if kind in ("int", "money"):
        return pd.array(s, dtype="Int64") if len(s) else pd.Series([], dtype="Int64")
    if kind == "bool":
        return s.astype("boolean")
    if kind in ("date", "timestamp"):
        out = pd.to_datetime(s)
        if getattr(out.dt, "tz", None) is not None:
            out = out.dt.tz_convert("UTC").dt.tz_localize(None)
        out = out.astype("datetime64[ns]")
        return out.dt.normalize() if kind == "date" else out
    if kind == "rate":
        return s.astype("float64")
    raise ValueError(f"Unknown column type {kind}")


# ------------------------------------------------------------------ text form

def _currency_series(df: pd.DataFrame, table: Table, col) -> pd.Series | str:
    if col.currency:
        return col.currency
    return df[col.currency_field]


def to_text(df: pd.DataFrame, table: Table) -> pd.DataFrame:
    """Typed frame -> frame of strings (None for nulls)."""
    out = {}
    for col in table.columns:
        s = df[col.name]
        if col.type in ("string", "decimal"):
            out[col.name] = s.astype("object").where(s.notna(), None)
        elif col.type == "int":
            out[col.name] = [None if pd.isna(v) else str(int(v)) for v in s]
        elif col.type == "bool":
            out[col.name] = [None if pd.isna(v) else ("true" if v else "false") for v in s]
        elif col.type == "date":
            out[col.name] = s.dt.strftime("%Y-%m-%d").where(s.notna(), None)
        elif col.type == "timestamp":
            out[col.name] = s.dt.strftime("%Y-%m-%dT%H:%M:%SZ").where(s.notna(), None)
        elif col.type == "money":
            out[col.name] = format_minor(s, _currency_series(df, table, col))
        elif col.type == "rate":
            out[col.name] = [None if pd.isna(v) else f"{v:.8f}" for v in s]
        else:
            raise ValueError(col.type)
    return pd.DataFrame(out, columns=table.column_names)


def from_text(text: pd.DataFrame, table: Table) -> pd.DataFrame:
    """Frame of strings -> typed frame."""
    text = text.astype("object").where(text.notna(), None)
    data = {}
    # Currency columns must be parsed before the money columns that depend on them.
    for col in table.columns:
        s = text[col.name] if col.name in text.columns else pd.Series([None] * len(text), dtype="object")
        if col.type in ("string", "decimal"):
            data[col.name] = s
        elif col.type == "int":
            data[col.name] = [None if v is None else int(v) for v in s]
        elif col.type == "bool":
            data[col.name] = [None if v is None else str(v).lower() == "true" for v in s]
        elif col.type in ("date", "timestamp"):
            data[col.name] = pd.to_datetime(s.where(s.notna(), None), utc=(col.type == "timestamp"))
        elif col.type == "money":
            ccy = col.currency or (text[col.currency_field] if col.currency_field in text.columns else None)
            data[col.name] = parse_major(s, ccy)
        elif col.type == "rate":
            data[col.name] = [np.nan if v is None else float(v) for v in s]
    return conform(pd.DataFrame(data), table)


# ------------------------------------------------------------------------ CSV

def write_csv(ds: Dataset, directory: Path) -> None:
    schema = load_schema()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name in schema.dataset_tables:
        if name in ds:
            _write_csv_table(ds[name], schema.table(name), directory / f"{name}.csv")


def write_ground_truth_csv(ds: Dataset, directory: Path) -> Path:
    table = load_schema().table(GROUND_TRUTH_TABLE)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "anomalies.csv"
    _write_csv_table(ds.ground_truth, table, path)
    return path


def _write_csv_table(df: pd.DataFrame, table: Table, path: Path) -> None:
    text = to_text(conform(df, table), table)
    text.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")


def read_csv_table(path: Path, table: Table) -> pd.DataFrame:
    text = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8")
    return from_text(text, table)


def read_csv(directory: Path, ground_truth_dir: Path | None = None) -> Dataset:
    schema = load_schema()
    directory = Path(directory)
    tables = {}
    for name in schema.dataset_tables:
        path = directory / f"{name}.csv"
        if path.exists():
            tables[name] = read_csv_table(path, schema.table(name))
    gt = None
    if ground_truth_dir is not None and (Path(ground_truth_dir) / "anomalies.csv").exists():
        gt = read_csv_table(Path(ground_truth_dir) / "anomalies.csv", schema.table(GROUND_TRUTH_TABLE))
    return Dataset(tables, gt)


# ----------------------------------------------------------------------- JSON

def _json_records(df: pd.DataFrame, table: Table) -> list[dict]:
    text = to_text(conform(df, table), table)
    records = []
    types = {c.name: c.type for c in table.columns}
    for row in text.itertuples(index=False, name=None):
        rec = {}
        for name, value in zip(table.column_names, row):
            if value is None:
                rec[name] = None
            elif types[name] == "int":
                rec[name] = int(value)
            elif types[name] == "bool":
                rec[name] = value == "true"
            else:
                rec[name] = value  # strings, dates, timestamps, money and rates stay exact as text
        records.append(rec)
    return records


def write_json_table(df: pd.DataFrame, table: Table, path: Path) -> None:
    records = _json_records(df, table)
    lines = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records]
    body = "[\n" + ",\n".join(lines) + "\n]\n" if lines else "[]\n"
    path.write_text(body, encoding="utf-8", newline="\n")


def write_json(ds: Dataset, directory: Path) -> None:
    schema = load_schema()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name in schema.dataset_tables:
        if name in ds:
            write_json_table(ds[name], schema.table(name), directory / f"{name}.json")
