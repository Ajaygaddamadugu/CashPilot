"""Generation pipeline: parents first, then children, then events and derived records."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from cashpilot.core.config import Config
from cashpilot.dataset import Dataset, conform_dataset
from cashpilot.generate.documents import Documents, build_documents
from cashpilot.generate.ledger import LedgerResult, build_ledger, build_statements
from cashpilot.generate.master import (
    build_account_events, build_accounts, build_counterparties, build_currencies, build_entities,
    build_fx_rates, build_scenarios, build_users,
)


@dataclass
class World:
    """Everything the later stages (anomaly injection, history) need besides the tables."""
    cfg: Config
    docs: Documents
    ledger: LedgerResult


def generate_baseline(cfg: Config) -> tuple[Dataset, World]:
    """Valid baseline data: no anomalies, no forecast runs yet."""
    currencies = build_currencies(cfg)
    entities = build_entities(cfg)
    users = build_users(cfg, entities)
    counterparties = build_counterparties(cfg)
    accounts = build_accounts(cfg, entities)
    account_events = build_account_events(cfg, accounts, users)
    fx = build_fx_rates(cfg)
    scenarios, assumptions, links = build_scenarios(cfg)
    docs = build_documents(cfg, entities, accounts, counterparties, users, fx,
                           n_duplicates=cfg.anomalies["duplicate_cash_flows"])
    led = build_ledger(cfg, entities, accounts, fx, docs)
    statements = build_statements(cfg, accounts, led.ledger)
    tables = {
        "currency": currencies,
        "app_user": users,
        "counterparty": counterparties,
        "currency_rate": fx,
        "liquidity_scenario": scenarios,
        "scenario_assumption": assumptions,
        "scenario_assumption_link": links,
        "legal_entity": entities,
        "bank_account": accounts,
        "receivable": docs.receivables,
        "payable": docs.payables,
        "cash_flow_forecast": docs.cf_items,
        "ledger_entry": led.ledger,
        "settlement_allocation": led.allocations,
        "bank_statement": statements,
        "bank_account_event": account_events,
        "receivable_event": led.receivable_events,
        "payable_event": led.payable_events,
        "cf_revision": led.revisions,
    }
    raw = Dataset({k: v.reset_index(drop=True) for k, v in tables.items()})
    return conform_dataset(raw), World(cfg, docs, led)


def generate_dataset(cfg: Config) -> tuple[Dataset, Dataset, World]:
    """Baseline -> labelled anomalies -> legacy forecast history. Returns (dataset, baseline, world)."""
    from cashpilot.engine.forecast import ForecastContext
    from cashpilot.engine.positions import fx_book
    from cashpilot.generate.anomalies import inject
    from cashpilot.generate.history import RunLog, build_history, finalise_run_tables

    baseline, world = generate_baseline(cfg)
    injected, ground_truth, leaky, benign = inject(cfg, baseline)
    ctx = ForecastContext(injected, cfg, fx_book(injected, cfg.policy))
    log = RunLog()
    build_history(cfg, injected, ctx, leaky, benign, log)
    for name, df in finalise_run_tables(cfg, log.tables()).items():
        injected[name] = df
    injected.ground_truth = ground_truth
    return conform_dataset(injected), baseline, world


def table_counts(ds: Dataset) -> pd.Series:
    return pd.Series({k: len(v) for k, v in ds.tables.items()})
