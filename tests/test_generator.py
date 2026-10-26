import re

import numpy as np
import pandas as pd

from cashpilot.schema import load_schema


def test_volumes_hit_the_profile_targets_exactly(baseline, starter_cfg):
    ds, _ = baseline
    v, a = starter_cfg.volumes, starter_cfg.anomalies
    assert len(ds["legal_entity"]) == v["legal_entities"]
    assert len(ds["bank_account"]) == v["bank_accounts"]
    assert len(ds["ledger_entry"]) == v["ledger_entries"]
    # injected duplicates are added later and complete the forecast-item total
    assert len(ds["cash_flow_forecast"]) + a["duplicate_cash_flows"] == v["forecast_items"]
    assert set(ds["bank_account"]["currency"]) == set(starter_cfg.currencies)


def test_every_foreign_key_resolves(baseline):
    ds, _ = baseline
    schema = load_schema()
    for table, col in schema.foreign_keys():
        if table.name not in ds or col.fk_table not in ds:
            continue
        values = ds[table.name][col.name].dropna()
        parents = set(ds[col.fk_table][col.fk_column])
        orphans = set(values) - parents
        assert not orphans, f"{table.name}.{col.name}: {sorted(orphans)[:3]}"


def test_ids_follow_the_documented_patterns(baseline):
    ds, _ = baseline
    schema = load_schema()
    for name, df in ds.tables.items():
        for col in schema.table(name).columns:
            if col.pattern and col.name in df:
                bad = df[col.name].dropna().astype(str)
                bad = bad[~bad.str.match(col.pattern)]
                assert bad.empty, f"{name}.{col.name}: {bad.head(3).tolist()}"


def test_account_ids_embed_their_entity(baseline):
    ds, _ = baseline
    acc = ds["bank_account"]
    assert (acc["account_id"].str.slice(8, 18) == acc["entity_id"]).all()


def test_baseline_statements_reconcile_with_the_ledger(baseline):
    ds, _ = baseline
    st = ds["bank_statement"]
    led = ds["ledger_entry"].groupby(["account_id", "posting_date"])["amount"].sum()
    moves = st.set_index(["account_id", "statement_date"]).index.map(lambda k: led.get(k, 0))
    assert ((st["closing_balance"] - st["opening_balance"]).to_numpy() == np.asarray(moves)).all()
    assert (st["closing_balance"] == st["opening_balance"] + st["total_credits"] - st["total_debits"]).all()
    prev = st.sort_values(["account_id", "statement_date"]).groupby("account_id")["closing_balance"].shift()
    cont = st.sort_values(["account_id", "statement_date"])
    assert (cont["opening_balance"][prev.notna()] == prev[prev.notna()]).all()


def test_internal_transfers_net_to_zero(baseline):
    ds, _ = baseline
    led = ds["ledger_entry"]
    same_ccy = led[led["transfer_group_id"].notna() & (led["entry_type"] != "FX_CONVERSION")]
    assert (same_ccy.groupby("transfer_group_id")["amount"].sum() == 0).all()
    assert (same_ccy.groupby("transfer_group_id").size() == 2).all()


def test_ledger_ids_follow_posting_order(baseline):
    ds, _ = baseline
    led = ds["ledger_entry"]
    assert led["posting_date"].is_monotonic_increasing
    assert led["ledger_entry_id"].is_unique
