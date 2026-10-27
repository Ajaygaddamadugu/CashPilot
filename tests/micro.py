"""A tiny, fully hand-checkable dataset for financial-calculation tests.

One USD entity, four accounts, a handful of postings and a deliberately gappy EUR rate table:

    A-USD  operating   opening 1,000.00 USD     2026-01-05  -50.00
    A-RES  restricted  opening   200.00 USD     (no postings)
    A-EUR  operating   opening 1,000.00 EUR     2026-01-05  +500.00, -200.00
    A-JPY  operating   opening 100,000 JPY      2026-01-05  +1,000

    EUR/USD   1.10 on 2026-01-02, 1.20 on 2026-01-05, then no fixings at all
    JPY/USD   0.007 every business day

Expected values are written out by hand in the tests, never recomputed with the code under test.
"""

from types import SimpleNamespace

import pandas as pd

from cashpilot.core import calendar as cal
from cashpilot.dataset import Dataset, conform
from cashpilot.engine.fx import FxBook
from cashpilot.generate.ledger import build_statements
from cashpilot.schema import load_schema

ENTITY = "ENT-000001"
ACTUALS_END = "2026-01-13"
TOLERANCE = 3  # business days, as in the profiles


def _acct(n, ccy, kind, opening, restricted=False):
    return {
        "account_id": f"BANKACC-{ENTITY}-{n:03d}", "entity_id": ENTITY, "bank_name": "Test Bank",
        "account_number_masked": f"****{n:04d}", "currency": ccy, "account_type": kind, "is_restricted": restricted,
        "is_pool_header": False, "overdraft_limit": 0, "opened_on": pd.Timestamp("2020-01-01"),
        "opening_balance_date": pd.Timestamp("2026-01-02"), "opening_balance": opening, "closed_on": None,
        "status_at_end": "ACTIVE",
    }


ACCOUNTS = [
    _acct(1, "USD", "OPERATING", 100_000),
    _acct(2, "USD", "RESTRICTED", 20_000, restricted=True),
    _acct(3, "EUR", "OPERATING", 100_000),
    _acct(4, "JPY", "OPERATING", 100_000),  # JPY has no minor units: 100,000 yen
]
USD, RES, EUR, JPY = (a["account_id"] for a in ACCOUNTS)


def micro_dataset() -> Dataset:
    schema = load_schema()
    entity = pd.DataFrame([{
        "entity_id": ENTITY, "entity_name": "Test Holding Inc.", "country_code": "US", "functional_currency": "USD",
        "entity_type": "HOLDING", "parent_entity_id": None, "size_tier": "S", "min_liquidity_buffer": 50_000,
        "effective_from": pd.Timestamp("2026-01-01"), "effective_to": None, "status": "ACTIVE"}])
    accounts = pd.DataFrame(ACCOUNTS)
    postings = [(USD, "2026-01-05", -5_000), (EUR, "2026-01-05", 50_000), (EUR, "2026-01-05", -20_000), (JPY, "2026-01-05", 1_000)]
    ledger = pd.DataFrame([{
        "ledger_entry_id": f"LED-2026-{i:08d}", "account_id": a, "entity_id": ENTITY, "posting_date": pd.Timestamp(d),
        "recorded_at": pd.Timestamp(d) + pd.Timedelta(hours=12),
        "currency": next(x["currency"] for x in ACCOUNTS if x["account_id"] == a), "amount": amt,
        "entry_type": "OTHER_RECEIPT" if amt > 0 else "OTHER_PAYMENT", "description": "fixture"}
        for i, (a, d, amt) in enumerate(postings, start=1)])
    stmt_cfg = SimpleNamespace(actuals_end=ACTUALS_END, cycle_year=2026)
    statements = build_statements(stmt_cfg, accounts, ledger)

    days = cal.business_days("2026-01-02", ACTUALS_END)
    rates = [("EUR", "2026-01-02", 1.10), ("EUR", "2026-01-05", 1.20)] + [("JPY", str(d), 0.007) for d in days]
    rate_table = pd.DataFrame([{
        "rate_id": f"FXR-{d}-{c}-USD", "rate_date": pd.Timestamp(d), "base_currency": c, "quote_currency": "USD", "rate": r,
        "rate_type": "CLOSING", "source": "SYNTHETIC_GBM", "recorded_at": pd.Timestamp(d) + pd.Timedelta(hours=16)}
        for c, d, r in rates])
    tables = {"legal_entity": entity, "bank_account": accounts, "ledger_entry": ledger, "bank_statement": statements,
              "currency_rate": rate_table}
    return Dataset({n: conform(df, schema.table(n)) for n, df in tables.items()})


def micro_fx(ds: Dataset) -> FxBook:
    return FxBook(ds["currency_rate"], "USD", TOLERANCE)
