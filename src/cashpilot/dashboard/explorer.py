"""Data explorer views: entities, bank accounts, ledger entries, customer invoices and supplier bills.

Plain selections and joins over the stored tables, in major units. The ledger check re-adds an account's
postings to its opening balance and compares the result with the stored daily position, so a user can see
for themselves that opening balance + inflows - outflows = closing balance.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashpilot.dashboard.data import Bundle, major

OPEN_STATUSES = ("OPEN", "PARTIALLY_PAID", "OVERDUE")


def entity_master(b: Bundle) -> pd.DataFrame:
    ds = b.ds
    e = ds["legal_entity"].copy()
    acc = ds["bank_account"]
    e["accounts"] = e["entity_id"].map(acc.groupby("entity_id").size()).fillna(0).astype(int)
    e["currencies"] = e["entity_id"].map(acc.groupby("entity_id")["currency"].agg(lambda s: ", ".join(sorted(set(s)))))
    e["min_liquidity_buffer"] = major(e["min_liquidity_buffer"], e["functional_currency"])
    cols = ["entity_id", "entity_name", "entity_type", "country_code", "functional_currency", "size_tier", "parent_entity_id", "min_liquidity_buffer",
            "effective_from", "effective_to", "status", "accounts", "currencies"]
    return e[cols].sort_values("entity_id").reset_index(drop=True)


def account_master(b: Bundle, entity: str | None = None) -> pd.DataFrame:
    a = b.ds["bank_account"].copy()
    if entity:
        a = a[a["entity_id"] == entity]
    a["overdraft_limit"] = major(a["overdraft_limit"], a["currency"])
    a["opening_balance"] = major(a["opening_balance"], a["currency"])
    a["entity_name"] = a["entity_id"].map(b.entity_names)
    a["restricted"] = a["is_restricted"].astype(bool)
    cols = ["account_id", "entity_id", "entity_name", "bank_name", "account_type", "currency", "restricted", "is_pool_header", "overdraft_limit",
            "opened_on", "opening_balance_date", "opening_balance", "closed_on", "status_at_end"]
    return a[cols].sort_values("account_id").reset_index(drop=True)


def account_events(b: Bundle, account_id: str) -> pd.DataFrame:
    ev = b.ds["bank_account_event"]
    ev = ev[ev["account_id"] == account_id].sort_values(["event_ts", "event_id"])
    return ev[["event_ts", "event_type", "from_status", "to_status", "actor_id", "reason"]].reset_index(drop=True)


def ledger_view(b: Bundle, accounts=None, start=None, end=None, entry_types=None) -> pd.DataFrame:
    led = b.ds["ledger_entry"]
    mask = np.ones(len(led), dtype=bool)
    if accounts:
        mask &= led["account_id"].isin(accounts).to_numpy()
    if start is not None:
        mask &= (led["posting_date"] >= pd.Timestamp(start)).to_numpy()
    if end is not None:
        mask &= (led["posting_date"] <= pd.Timestamp(end)).to_numpy()
    if entry_types:
        mask &= led["entry_type"].isin(entry_types).to_numpy()
    led = led[mask]
    amount = major(led["amount"], led["currency"])
    names = b.ds["counterparty"].set_index("counterparty_id")["counterparty_name"]
    out = pd.DataFrame({
        "posting_date": led["posting_date"].to_numpy(), "ledger_entry_id": led["ledger_entry_id"].to_numpy(), "account_id": led["account_id"].to_numpy(),
        "entry_type": led["entry_type"].to_numpy(), "description": led["description"].to_numpy(), "currency": led["currency"].to_numpy(),
        "money_in": amount.clip(lower=0).to_numpy(), "money_out": (-amount).clip(lower=0).to_numpy(),
        "counterparty": led["counterparty_id"].map(names).to_numpy(), "cf_id": led["cf_id"].to_numpy()})
    return out.reset_index(drop=True)


def ledger_totals(view: pd.DataFrame) -> pd.DataFrame:
    """Entries and money in/out by entry type (valid for one account / one currency at a time)."""
    return (view.groupby("entry_type").agg(entries=("ledger_entry_id", "size"), money_in=("money_in", "sum"), money_out=("money_out", "sum"))
            .reset_index().sort_values("entries", ascending=False))


def ledger_account_check(b: Bundle, account_id: str, on) -> dict:
    """opening balance + inflows - outflows up to a date, against the stored daily position (account currency, major units)."""
    ds = b.ds
    acc = ds["bank_account"].set_index("account_id").loc[account_id]
    led = ds["ledger_entry"]
    led = led[(led["account_id"] == account_id) & (led["posting_date"] <= pd.Timestamp(on))]
    ccy = acc["currency"]
    scale = 10 ** (0 if ccy == "JPY" else 2)
    inflows, outflows = int(led["amount"].clip(lower=0).sum()), int((-led["amount"]).clip(lower=0).sum())
    opening = int(acc["opening_balance"])
    calc = opening + inflows - outflows
    d = ds["daily_cash_position"]
    rec = d[(d["account_id"] == account_id) & (d["position_date"] == pd.Timestamp(on))]
    recorded = int(rec["closing_balance"].iloc[0]) if len(rec) else None
    return {"currency": ccy, "opening": opening / scale, "inflows": inflows / scale, "outflows": outflows / scale, "closing_calculated": calc / scale,
            "closing_recorded": None if recorded is None else recorded / scale, "matches": recorded is not None and recorded == calc, "entries": int(len(led)),
            "opening_balance_date": acc["opening_balance_date"]}


def _paid_on(b: Bundle, event_table: str, key: str) -> pd.Series:
    ev = b.ds[event_table]
    return ev[ev["event_type"] == "PAID"].groupby(key)["event_ts"].max().dt.normalize()


def receivable_list(b: Bundle) -> pd.DataFrame:
    ds = b.ds
    r = ds["receivable"].copy()
    cp = ds["counterparty"].set_index("counterparty_id")
    r["customer"] = r["counterparty_id"].map(cp["counterparty_name"])
    r["risk_tier"] = r["counterparty_id"].map(cp["risk_tier"])
    r["entity_name"] = r["entity_id"].map(b.entity_names)
    r["amount"] = major(r["amount"], r["currency"])
    r["paid_on"] = r["receivable_id"].map(_paid_on(b, "receivable_event", "receivable_id"))
    r["days_late"] = (r["paid_on"] - r["due_date"]).dt.days
    r = r.rename(columns={"status_at_end": "status"})
    cols = ["receivable_id", "entity_id", "entity_name", "customer", "risk_tier", "invoice_number", "invoice_date", "due_date", "currency", "amount",
            "status", "paid_on", "days_late"]
    return r[cols].sort_values("receivable_id").reset_index(drop=True)


def payable_list(b: Bundle) -> pd.DataFrame:
    ds = b.ds
    p = ds["payable"].copy()
    cp = ds["counterparty"].set_index("counterparty_id")
    p["supplier"] = p["counterparty_id"].map(cp["counterparty_name"])
    p["entity_name"] = p["entity_id"].map(b.entity_names)
    p["amount"] = major(p["amount"], p["currency"])
    p["paid_on"] = p["payable_id"].map(_paid_on(b, "payable_event", "payable_id"))
    p = p.rename(columns={"status_at_end": "status"})
    cols = ["payable_id", "entity_id", "entity_name", "supplier", "bill_number", "bill_date", "due_date", "currency", "amount", "category", "is_one_off",
            "status", "paid_on"]
    return p[cols].sort_values("payable_id").reset_index(drop=True)


def one_off_payments(b: Bundle) -> pd.DataFrame:
    p = payable_list(b)
    return p[p["is_one_off"].astype(bool)].sort_values(["due_date", "payable_id"]).reset_index(drop=True)


def document_status_summary(b: Bundle) -> pd.DataFrame:
    r, p = receivable_list(b), payable_list(b)
    out = pd.concat([r["status"].value_counts().rename_axis("status").reset_index(name="count").assign(kind="Customer invoices"),
                     p["status"].value_counts().rename_axis("status").reset_index(name="count").assign(kind="Supplier bills")])
    return out[["kind", "status", "count"]].reset_index(drop=True)


def lateness_by_tier(b: Bundle) -> pd.DataFrame:
    """How late customers pay, by their risk tier (the documented rule that drives delayed receivables)."""
    r = receivable_list(b)
    rows = []
    for tier, g in r.groupby("risk_tier"):
        paid = g[g["status"] == "PAID"]
        late = paid["days_late"].dropna()
        rows.append({"risk_tier": tier, "invoices": int(len(g)), "paid": int(len(paid)),
                     "median_days_late": float(late.median()) if len(late) else np.nan,
                     "share_paid_over_7_days_late": float((late > 7).mean()) if len(late) else np.nan,
                     "written_off": int((g["status"] == "WRITTEN_OFF").sum()), "still_unpaid": int(g["status"].isin(OPEN_STATUSES).sum())})
    return pd.DataFrame(rows)
