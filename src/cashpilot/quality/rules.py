"""Detection primitives shared by the dataset-level detectors and the forecast data-quality gate.

These functions only read source tables. They never read ground truth.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashpilot.core.money import MINOR_UNITS

SYSTEM_SOURCES = ("AR_SUBLEDGER", "AP_SUBLEDGER")


def duplicate_pairs(items: pd.DataFrame, tolerance_days: int) -> pd.DataFrame:
    """Manual forecast items that repeat a subledger item.

    R-DUP-001: the manual item carries the same invoice/bill reference as a subledger item.
    R-DUP-002: otherwise, same entity, account, direction, currency, counterparty and amount,
               with expected dates no more than ``tolerance_days`` apart.
    Returns columns: cf_id (the manual duplicate), original_cf_id, rule_id.
    """
    cols = ["cf_id", "entity_id", "account_id", "direction", "currency", "counterparty_id", "amount",
            "expected_date", "source_reference"]
    manual = items.loc[items["source_system"] == "MANUAL", cols]
    system = items.loc[items["source_system"].isin(SYSTEM_SOURCES), cols]
    if manual.empty or system.empty:
        return pd.DataFrame(columns=["cf_id", "original_cf_id", "rule_id"])
    exact = manual.dropna(subset=["source_reference"]).merge(
        system[["entity_id", "source_reference", "cf_id"]], on=["entity_id", "source_reference"], suffixes=("", "_orig"))
    exact = exact.assign(rule_id="R-DUP-001").rename(columns={"cf_id_orig": "original_cf_id"})
    rest = manual[~manual["cf_id"].isin(exact["cf_id"]) & manual["counterparty_id"].notna()]
    keys = ["entity_id", "account_id", "direction", "currency", "counterparty_id", "amount"]
    fuzzy = rest.merge(system[keys + ["cf_id", "expected_date"]], on=keys, suffixes=("", "_orig"))
    fuzzy["gap"] = (fuzzy["expected_date"] - fuzzy["expected_date_orig"]).abs().dt.days
    fuzzy = fuzzy[fuzzy["gap"] <= tolerance_days].sort_values(["cf_id", "gap", "cf_id_orig"])
    fuzzy = fuzzy.drop_duplicates("cf_id").assign(rule_id="R-DUP-002").rename(columns={"cf_id_orig": "original_cf_id"})
    out = pd.concat([exact[["cf_id", "original_cf_id", "rule_id"]], fuzzy[["cf_id", "original_cf_id", "rule_id"]]])
    return out.drop_duplicates("cf_id").sort_values("cf_id").reset_index(drop=True)


def mixed_currency(items: pd.DataFrame, accounts: pd.DataFrame, receivables: pd.DataFrame,
                   payables: pd.DataFrame) -> pd.DataFrame:
    """Forecast items whose currency was mixed without conversion.

    R-CUR-001: item currency differs from its account's currency and no conversion is recorded.
    R-CUR-002: item is linked to a source document in another currency, records no conversion,
               and its amount equals the document amount (the foreign number was copied as is).
    Returns columns: cf_id, rule_id, source_currency, source_amount (minor units of source_currency).
    """
    acct_ccy = accounts.set_index("account_id")["currency"]
    it = items.assign(account_currency=items["account_id"].map(acct_ccy))
    unconverted = it["original_currency"].isna()
    r1 = it[unconverted & (it["currency"] != it["account_currency"])]
    r1 = r1.assign(rule_id="R-CUR-001", source_currency=r1["currency"], source_amount=r1["amount"])

    docs = pd.concat([
        receivables[["receivable_id", "currency", "amount"]].rename(columns={"receivable_id": "doc_id"}),
        payables[["payable_id", "currency", "amount"]].rename(columns={"payable_id": "doc_id"}),
    ])
    it["doc_id"] = it["receivable_id"].fillna(it["payable_id"])
    linked = it[unconverted & it["doc_id"].notna() & ~it["cf_id"].isin(r1["cf_id"])].merge(
        docs.rename(columns={"currency": "doc_currency", "amount": "doc_amount"}), on="doc_id")
    linked = linked[linked["doc_currency"] != linked["currency"]]
    item_major = linked["amount"].astype(float) / linked["currency"].map(lambda c: 10 ** MINOR_UNITS[c])
    doc_major = linked["doc_amount"].astype(float) / linked["doc_currency"].map(lambda c: 10 ** MINOR_UNITS[c])
    r2 = linked[np.abs(item_major - doc_major) < 1.0]
    r2 = r2.assign(rule_id="R-CUR-002", source_currency=r2["doc_currency"], source_amount=r2["doc_amount"])
    cols = ["cf_id", "rule_id", "source_currency", "source_amount"]
    return pd.concat([r1[cols], r2[cols]]).sort_values("cf_id").reset_index(drop=True)
