"""Actual daily cash positions.

Per account and calendar day, the book position is rebuilt from the ledger:
``opening(d) = closing(d-1)``, ``closing = opening + inflows - outflows``, starting from the
account's opening balance. The bank's closing balance is attached for comparison and each
balance is valued in USD with the staleness rule from :mod:`cashpilot.engine.fx`.
Entity positions are the sum of their accounts' USD values, split into available and
restricted cash.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashpilot.core.money import to_usd
from cashpilot.dataset import Dataset
from cashpilot.engine.fx import FALLBACK, MISSING, FxBook


def fx_book(ds: Dataset, policy: dict, reporting: str = "USD") -> FxBook:
    return FxBook(ds["currency_rate"], reporting, policy["fx_staleness_business_days"])


def daily_cash_positions(ds: Dataset, actuals_end, fx: FxBook) -> pd.DataFrame:
    accounts = ds["bank_account"]
    end = np.datetime64(pd.Timestamp(actuals_end).date(), "D")
    grids = []
    for a in accounts.itertuples():
        first = np.datetime64(a.opening_balance_date, "D")
        last = min(np.datetime64(a.closed_on, "D"), end) if pd.notna(a.closed_on) else end
        days = np.arange(first, last + 1, dtype="datetime64[D]")
        grids.append(pd.DataFrame({"account_id": a.account_id, "position_date": pd.to_datetime(days),
                                   "entity_id": a.entity_id, "currency": a.currency, "x_opening": a.opening_balance}))
    grid = pd.concat(grids, ignore_index=True)

    led = ds["ledger_entry"]
    flows = led.assign(inflows=led["amount"].clip(lower=0), outflows=(-led["amount"]).clip(lower=0))
    flows = flows.groupby(["account_id", "posting_date"])[["inflows", "outflows"]].sum().reset_index()
    flows = flows.rename(columns={"posting_date": "position_date"})
    pos = grid.merge(flows, on=["account_id", "position_date"], how="left").fillna({"inflows": 0, "outflows": 0})
    pos = pos.sort_values(["account_id", "position_date"]).reset_index(drop=True)
    net = (pos["inflows"] - pos["outflows"]).astype(np.int64)
    pos["closing_balance"] = pos["x_opening"].astype(np.int64) + net.groupby(pos["account_id"]).cumsum()
    pos["opening_balance"] = pos["closing_balance"] - net
    pos["inflows"] = pos["inflows"].astype(np.int64)
    pos["outflows"] = pos["outflows"].astype(np.int64)

    st = ds["bank_statement"][["account_id", "statement_date", "closing_balance"]].rename(
        columns={"statement_date": "position_date", "closing_balance": "statement_closing"})
    pos = pos.merge(st, on=["account_id", "position_date"], how="left")
    pos["bank_minus_book"] = pos["statement_closing"] - pos["closing_balance"]

    pos["fx_rate_id"] = None
    pos["fx_status"] = None
    pos["closing_balance_usd"] = pd.array([pd.NA] * len(pos), dtype="Int64")
    for ccy, idx in pos.groupby("currency").groups.items():
        rid, rate, status = fx.as_of(ccy, pos.loc[idx, "position_date"].to_numpy(dtype="datetime64[D]"))
        pos.loc[idx, "fx_rate_id"] = rid
        pos.loc[idx, "fx_status"] = status
        usd = to_usd(pos.loc[idx, "closing_balance"].to_numpy(), ccy, np.nan_to_num(rate, nan=0.0))
        pos.loc[idx, "closing_balance_usd"] = pd.array(np.where(status == MISSING, None, usd), dtype="Int64")
    return pos.drop(columns=["x_opening"])


def entity_cash_positions(ds: Dataset, daily: pd.DataFrame, fx: FxBook) -> pd.DataFrame:
    ent = ds["legal_entity"].set_index("entity_id")
    restricted = ds["bank_account"].set_index("account_id")["is_restricted"]
    d = daily.assign(
        is_restricted=daily["account_id"].map(restricted).astype(bool),
        usd=daily["closing_balance_usd"].astype("Float64").fillna(0).astype(np.int64),
        missing=daily["fx_status"] == MISSING,
        fallback=daily["fx_status"] == FALLBACK,
    )
    d["restricted_usd"] = np.where(d["is_restricted"], d["usd"], 0)
    g = d.groupby(["entity_id", "position_date"]).agg(
        total_usd=("usd", "sum"), restricted_usd=("restricted_usd", "sum"), accounts_active=("account_id", "size"),
        any_missing=("missing", "any"), any_fallback=("fallback", "any")).reset_index()
    g = g[g["position_date"] >= g["entity_id"].map(ent["effective_from"])].reset_index(drop=True)
    g["available_usd"] = g["total_usd"] - g["restricted_usd"]
    g["fx_status"] = np.where(g["any_missing"], "INCOMPLETE", np.where(g["any_fallback"], FALLBACK, "OK"))
    g["min_buffer_usd"] = 0
    for entity, idx in g.groupby("entity_id").groups.items():
        func = ent.at[entity, "functional_currency"]
        _, rate = fx.latest(func, g.loc[idx, "position_date"].to_numpy(dtype="datetime64[D]"))
        g.loc[idx, "min_buffer_usd"] = to_usd(np.full(len(idx), ent.at[entity, "min_liquidity_buffer"]), func, rate)
    g["headroom_usd"] = g["available_usd"] - g["min_buffer_usd"]
    return g.drop(columns=["any_missing", "any_fallback"])
