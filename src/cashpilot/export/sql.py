"""SQL DDL, append-only triggers and seed INSERTs, all derived from the data dictionary.

The DDL is portable ANSI-style SQL (tested on SQLite). The triggers file uses SQLite
syntax and makes history tables append-only.
"""

from __future__ import annotations

from pathlib import Path

from cashpilot.dataset import Dataset, conform, to_text
from cashpilot.schema import Schema, Table, load_schema

SQL_TYPES = {
    "string": "TEXT",
    "decimal": "NUMERIC(18,6)",
    "int": "INTEGER",
    "bool": "BOOLEAN",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
    "money": "NUMERIC(20,2)",
    "rate": "NUMERIC(18,8)",
}

APPEND_ONLY_LAYERS = ("transaction", "event", "bridge", "history")
APPEND_ONLY_EXTRA = ("exception_event", "audit_event")
BATCH = 500


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_table_ddl(table: Table) -> str:
    lines = []
    for c in table.columns:
        line = f"    {c.name} {SQL_TYPES[c.type]}"
        if c.required:
            line += " NOT NULL"
        if c.allowed:
            vals = ", ".join(str(a) if isinstance(a, int) else _quote(str(a)) for a in c.allowed)
            line += f" CHECK ({c.name} IN ({vals}))"
        lines.append(line)
    lines.append(f"    PRIMARY KEY ({', '.join(table.primary_key)})")
    for c in table.columns:
        if c.unique and table.primary_key != (c.name,):
            lines.append(f"    UNIQUE ({c.name})")
    for group in table.unique_together:
        lines.append(f"    UNIQUE ({', '.join(group)})")
    for c in table.columns:
        if c.fk:
            lines.append(f"    FOREIGN KEY ({c.name}) REFERENCES {c.fk_table} ({c.fk_column})")
    body = ",\n".join(lines)
    return f"-- {table.description}\nCREATE TABLE {table.name} (\n{body}\n);\n"


def render_ddl(schema: Schema) -> str:
    parts = [
        "-- CashPilot schema, generated from src/cashpilot/schema/dictionary.yaml.",
        "-- Tables are ordered parents-first so the file can be applied top to bottom.",
        "",
    ]
    for name in schema.topological_order():
        parts.append(render_table_ddl(schema.table(name)))
    return "\n".join(parts)


def append_only_tables(schema: Schema) -> list[str]:
    return [
        n for n in schema.topological_order()
        if schema.table(n).layer in APPEND_ONLY_LAYERS or n in APPEND_ONLY_EXTRA
    ]


def render_triggers(schema: Schema) -> str:
    parts = [
        "-- SQLite triggers that make history append-only: rows can be inserted, never changed or deleted.",
        "-- Status changes are new rows in the *_event / cf_revision tables.",
        "",
    ]
    for name in append_only_tables(schema):
        for action in ("UPDATE", "DELETE"):
            parts.append(
                f"CREATE TRIGGER {name}_no_{action.lower()} BEFORE {action} ON {name}\n"
                f"BEGIN SELECT RAISE(ABORT, '{name} is append-only'); END;"
            )
    return "\n".join(parts) + "\n"


def _literal(value, kind: str) -> str:
    if value is None:
        return "NULL"
    if kind in ("int", "money", "rate", "decimal"):
        return value
    if kind == "bool":
        return "TRUE" if value == "true" else "FALSE"
    return _quote(value)


def render_inserts(df, table: Table) -> list[str]:
    text = to_text(conform(df, table), table)
    kinds = [c.type for c in table.columns]
    cols = ", ".join(table.column_names)
    statements = []
    rows = list(text.itertuples(index=False, name=None))
    for start in range(0, len(rows), BATCH):
        values = ",\n".join(
            "(" + ", ".join(_literal(v, k) for v, k in zip(row, kinds)) + ")" for row in rows[start:start + BATCH]
        )
        statements.append(f"INSERT INTO {table.name} ({cols}) VALUES\n{values};")
    return statements


def write_sql(ds: Dataset, directory: Path) -> None:
    schema = load_schema()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "schema.sql").write_text(render_ddl(schema), encoding="utf-8", newline="\n")
    (directory / "append_only_sqlite.sql").write_text(render_triggers(schema), encoding="utf-8", newline="\n")
    with open(directory / "seed.sql", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("-- CashPilot seed data. Apply schema.sql first, then this file.\nBEGIN TRANSACTION;\n")
        for name in schema.topological_order():
            if name in ds and len(ds[name]):
                fh.write(f"\n-- {name}\n")
                for stmt in render_inserts(ds[name], schema.table(name)):
                    fh.write(stmt + "\n")
        fh.write("COMMIT;\n")
