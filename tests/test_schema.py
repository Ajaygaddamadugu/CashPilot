import re
import sqlite3
from pathlib import Path

import pytest

from cashpilot.export.docs import render_data_dictionary
from cashpilot.export.sql import append_only_tables, render_ddl, render_triggers
from cashpilot.schema import load_schema

REPO = Path(__file__).resolve().parents[1]
CORE_ENTITIES = [
    "legal_entity", "bank_account", "ledger_entry", "cash_flow_forecast", "receivable",
    "payable", "currency_rate", "liquidity_scenario", "forecast_run",
]


def test_every_core_entity_from_the_brief_is_defined():
    schema = load_schema()
    for name in CORE_ENTITIES:
        assert name in schema.tables


def test_every_foreign_key_points_at_a_primary_key():
    schema = load_schema()
    for table, col in schema.foreign_keys():
        parent = schema.table(col.fk_table)
        assert parent.primary_key == (col.fk_column,), f"{table.name}.{col.name} -> {col.fk}"


def test_patterns_compile_and_money_columns_know_their_currency():
    schema = load_schema()
    for t in schema.tables.values():
        for c in t.columns:
            if c.pattern:
                re.compile(c.pattern)
            if c.type == "money":
                assert c.currency or c.currency_field in t.column_names, f"{t.name}.{c.name}"


def test_topological_order_puts_parents_first():
    schema = load_schema()
    order = schema.topological_order()
    assert set(order) == set(schema.dataset_tables)
    pos = {n: i for i, n in enumerate(order)}
    for table, col in schema.foreign_keys():
        if table.layer != "ground_truth" and col.fk_table != table.name:
            assert pos[col.fk_table] < pos[table.name]


def test_ddl_applies_in_sqlite_and_history_is_append_only():
    schema = load_schema()
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(render_ddl(schema))
    con.executescript(render_triggers(schema))
    assert "ledger_entry" in append_only_tables(schema)

    con.execute("INSERT INTO currency VALUES ('USD', 'US Dollar', 2, TRUE)")
    con.execute("INSERT INTO app_user VALUES ('USR-0001', 'Scheduler', 'SYSTEM', NULL, '2025-12-01')")
    con.execute(
        "INSERT INTO legal_entity VALUES ('ENT-000001', 'Holding', 'US', 'USD', 'HOLDING', NULL, 'L', "
        "1000000.00, '2026-01-01', NULL, 'ACTIVE')"
    )
    con.execute(
        "INSERT INTO bank_account VALUES ('BANKACC-ENT-000001-001', 'ENT-000001', 'Bank', '****1234', 'USD', "
        "'OPERATING', FALSE, FALSE, 0, '2020-01-01', '2026-01-01', 10.00, NULL, 'ACTIVE')"
    )
    con.execute(
        "INSERT INTO bank_account_event VALUES ('BAE-2026-000001', 'BANKACC-ENT-000001-001', "
        "'2020-01-01T09:00:00Z', 'OPENED', NULL, 'ACTIVE', 'USR-0001', NULL)"
    )
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("UPDATE bank_account_event SET to_status = 'CLOSED'")
    with pytest.raises(sqlite3.IntegrityError):  # foreign key enforced
        con.execute(
            "INSERT INTO bank_account_event VALUES ('BAE-2026-000002', 'BANKACC-ENT-000099-001', "
            "'2020-01-01T09:00:00Z', 'OPENED', NULL, 'ACTIVE', 'USR-0001', NULL)"
        )


def test_committed_data_dictionary_is_up_to_date():
    committed = (REPO / "docs" / "DATA_DICTIONARY.md").read_text(encoding="utf-8")
    assert committed == render_data_dictionary(load_schema()), "run: cashpilot docs"
