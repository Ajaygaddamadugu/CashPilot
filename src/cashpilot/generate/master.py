"""Reference and master data, generated first: currencies, entities, users, counterparties,
bank accounts (with lifecycle events), FX rates and the scenario definitions.

Columns starting with ``_`` are simulation-only parameters (e.g. an entity's size scale).
They are dropped on export because the data dictionary does not define them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashpilot.core import calendar as cal
from cashpilot.core import ids
from cashpilot.core.config import Config
from cashpilot.core.money import MINOR_UNITS, major_to_minor
from cashpilot.core.rng import stream
from cashpilot.generate.common import (
    BANKS, COUNTRIES, CPTY_ADJ, CPTY_NOUN, CPTY_REGION, FX_DRIFT, FX_SHOCKS, FX_START, FX_VOL,
    HOLDING_BUFFER_USD, HOLDING_SCALE_USD, SECTORS, STEMS, SUFFIX, TIER_BUFFER_USD, TIER_SCALE_USD,
    day, sig3, stamp,
)

CURRENCY_NAMES = {"USD": "US Dollar", "EUR": "Euro", "GBP": "Pound Sterling", "INR": "Indian Rupee", "JPY": "Japanese Yen"}

# Account type sequence per entity; the second element picks the currency:
# 0 = functional currency, 1 = first foreign currency, 2 = second foreign currency.
TYPES_HOLDING = [("CONCENTRATION", 0), ("OPERATING", 0), ("DEPOSIT", 0), ("RESTRICTED", 0), ("PAYROLL", 0),
                 ("OPERATING", 1), ("COLLECTION", 2), ("DEPOSIT", 1), ("OPERATING", 2), ("COLLECTION", 0)]
TYPES_OPERATING = [("OPERATING", 0), ("COLLECTION", 0), ("PAYROLL", 0), ("DEPOSIT", 0), ("RESTRICTED", 0),
                   ("OPERATING", 1), ("COLLECTION", 1), ("OPERATING", 2), ("COLLECTION", 2), ("DEPOSIT", 1)]
BASE_ACCOUNTS = {"S": 3, "M": 5, "L": 8}
NEW_ACCOUNT_DATES = ["2026-03-02", "2026-06-15", "2026-08-03"]
CLOSE_DATES = ["2026-05-29", "2026-08-31", "2026-07-31"]
FREEZE = ("2026-07-06", "2026-07-17")  # frozen from the first date, unfrozen on the second

SYSTEM_USER = "USR-0001"
ADMIN_USER = "USR-0002"


def build_currencies(cfg: Config) -> pd.DataFrame:
    return pd.DataFrame({
        "currency_code": cfg.currencies,
        "currency_name": [CURRENCY_NAMES[c] for c in cfg.currencies],
        "minor_units": [MINOR_UNITS[c] for c in cfg.currencies],
        "is_reporting_currency": [c == cfg.reporting_currency for c in cfg.currencies],
    })


def build_entities(cfg: Config) -> pd.DataFrame:
    rng = stream(cfg.seed, "entities")
    n = cfg.volumes["legal_entities"]
    remaining = dict(cfg.entity_mix)
    remaining[cfg.reporting_currency] -= 1  # the holding company
    order: list[str] = []
    while any(v > 0 for v in remaining.values()):
        for c in cfg.currencies:
            if remaining.get(c, 0) > 0:
                order.append(c)
                remaining[c] -= 1
    currencies = [cfg.reporting_currency] + order
    stems = [str(s) for s in rng.permutation(STEMS)]
    used_country = {c: 0 for c in cfg.currencies}
    rows = []
    for i, ccy in enumerate(currencies, start=1):
        holding = i == 1
        tier = "L" if holding else str(rng.choice(["S", "M", "L"], p=[0.45, 0.40, 0.15]))
        country = COUNTRIES[ccy][used_country[ccy] % len(COUNTRIES[ccy])]
        used_country[ccy] += 1
        sector = SECTORS[int(rng.integers(len(SECTORS)))]
        if holding:
            name, scale, buffer_usd = f"{stems[0]} Group Holdings {SUFFIX[country]}", HOLDING_SCALE_USD, HOLDING_BUFFER_USD
        else:
            name = f"{stems[i - 1]} {sector} {SUFFIX[country]}"
            scale = TIER_SCALE_USD[tier] * float(rng.lognormal(0.0, 0.35))
            buffer_usd = TIER_BUFFER_USD[tier]
        acquired = i == n and n > 1
        rows.append({
            "entity_id": ids.entity_id(i),
            "entity_name": name,
            "country_code": country,
            "functional_currency": ccy,
            "entity_type": "HOLDING" if holding else "OPERATING",
            "parent_entity_id": None if holding else ids.entity_id(1),
            "size_tier": tier,
            "min_liquidity_buffer": int(major_to_minor([sig3(buffer_usd / FX_START[ccy])], ccy)[0]),
            "effective_from": pd.Timestamp(cfg.lifecycle["acquisition_date"] if acquired else cfg.start_date),
            "effective_to": None,
            "status": "ACTIVE",
            "x_scale_usd": scale,
            "x_acquired": acquired,
        })
    return pd.DataFrame(rows)


def build_users(cfg: Config, entities: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"user_id": SYSTEM_USER, "display_name": "CashPilot Scheduler", "role": "SYSTEM", "entity_id": None},
        {"user_id": ADMIN_USER, "display_name": "System Administrator 01", "role": "SYS_ADMIN", "entity_id": None},
    ]
    n = 3
    for k in range(cfg.volumes["ops_analysts"]):
        rows.append({"user_id": ids.simple("USR", n, 4), "display_name": f"Operations Analyst {k + 1:02d}", "role": "OPS_ANALYST", "entity_id": None})
        n += 1
    for k in range(cfg.volumes["risk_reviewers"]):
        rows.append({"user_id": ids.simple("USR", n, 4), "display_name": f"Risk Reviewer {k + 1:02d}", "role": "RISK_REVIEWER", "entity_id": None})
        n += 1
    for _, e in entities.iterrows():
        rows.append({"user_id": ids.simple("USR", n, 4), "display_name": f"Account Holder {e.entity_id}", "role": "ACCOUNT_HOLDER", "entity_id": e.entity_id})
        n += 1
    users = pd.DataFrame(rows)
    eff = users["entity_id"].map(entities.set_index("entity_id")["effective_from"])
    users["active_from"] = (eff - pd.Timedelta(days=1)).where(eff.notna() & (eff > pd.Timestamp(cfg.start_date)), pd.Timestamp("2025-12-01"))
    return users


def users_by_role(users: pd.DataFrame, role: str) -> list[str]:
    return users.loc[users["role"] == role, "user_id"].tolist()


def build_counterparties(cfg: Config) -> pd.DataFrame:
    rng = stream(cfg.seed, "counterparties")
    n_c, n_s = cfg.volumes["customers"], cfg.volumes["suppliers"]
    weights = np.array([cfg.entity_mix.get(c, 0) for c in cfg.currencies], dtype=float)
    weights = weights / weights.sum() * 0.7
    weights[cfg.currencies.index(cfg.reporting_currency)] += 0.3  # many foreign customers pay in USD
    combos = [(r, a, nn) for r in CPTY_REGION for a in CPTY_ADJ for nn in CPTY_NOUN]
    order = rng.permutation(len(combos))
    terms_by_tier = {"A": [30, 45], "B": [30, 45, 60], "C": [45, 60, 90], "D": [60, 90]}
    rows = []
    for k in range(n_c + n_s):
        customer = k < n_c
        region, adj, noun = combos[order[k]]
        ccy = cfg.currencies[int(rng.choice(len(cfg.currencies), p=weights))]
        country = COUNTRIES[ccy][int(rng.integers(len(COUNTRIES[ccy])))]
        if customer:
            tier = str(rng.choice(["A", "B", "C", "D"], p=[0.40, 0.35, 0.18, 0.07]))
            terms = int(rng.choice(terms_by_tier[tier]))
        else:
            tier = str(rng.choice(["A", "B", "C", "D"], p=[0.55, 0.35, 0.08, 0.02]))
            terms = int(rng.choice([15, 30, 45, 60]))
        rows.append({
            "counterparty_id": ids.simple("CPTY", k + 1, 6),
            "counterparty_name": f"{region}{adj} {noun} {SUFFIX[country]}",
            "counterparty_type": "CUSTOMER" if customer else "SUPPLIER",
            "country_code": country,
            "default_currency": ccy,
            "risk_tier": tier,
            "payment_terms_days": terms,
            "x_weight": float(rng.pareto(1.3)) + 1.0,
        })
    return pd.DataFrame(rows)


def _foreign_pair(func: str, currencies: list[str]) -> tuple[str, str]:
    fx1 = "USD" if func != "USD" else "EUR"
    fx2 = "GBP" if func in ("USD", "EUR") else "EUR"
    others = [c for c in currencies if c != func]
    fx1 = fx1 if fx1 in currencies else others[0]
    fx2 = fx2 if fx2 in currencies and fx2 != fx1 else next(c for c in others if c != fx1)
    return fx1, fx2


def _account_counts(cfg: Config, entities: pd.DataFrame) -> list[int]:
    counts = [6 if e.entity_type == "HOLDING" else BASE_ACCOUNTS[e.size_tier] for e in entities.itertuples()]
    floors = [4 if e.entity_type == "HOLDING" else 2 for e in entities.itertuples()]
    scale = entities["x_scale_usd"].to_numpy()
    target = cfg.volumes["bank_accounts"]
    while sum(counts) < target:
        ratio = [scale[i] / counts[i] if counts[i] < 10 else -1 for i in range(len(counts))]
        counts[int(np.argmax(ratio))] += 1
    while sum(counts) > target:
        ratio = [scale[i] / counts[i] if counts[i] > floors[i] else np.inf for i in range(len(counts))]
        counts[int(np.argmin(ratio))] -= 1
    return counts


def build_accounts(cfg: Config, entities: pd.DataFrame) -> pd.DataFrame:
    rng = stream(cfg.seed, "accounts")
    counts = _account_counts(cfg, entities)
    rows = []
    for (_, e), count in zip(entities.iterrows(), counts):
        fx1, fx2 = _foreign_pair(e.functional_currency, cfg.currencies)
        seq = TYPES_HOLDING if e.entity_type == "HOLDING" else TYPES_OPERATING
        banks = BANKS[e.country_code]
        for k in range(count):
            acct_type, which = seq[k]
            ccy = (e.functional_currency, fx1, fx2)[which]
            opened = np.datetime64("2012-01-01") + np.timedelta64(int(rng.integers(0, 4900)), "D")
            rows.append({
                "account_id": ids.account_id(e.entity_id, k + 1),
                "entity_id": e.entity_id,
                "bank_name": banks[k % len(banks)],
                "account_number_masked": f"****{int(rng.integers(0, 10000)):04d}",
                "currency": ccy,
                "account_type": acct_type,
                "is_restricted": acct_type == "RESTRICTED",
                "is_pool_header": False,
                "opened_on": pd.Timestamp(opened),
                "closed_on": None,
                "x_seq": k,
                "x_functional": ccy == e.functional_currency,
                "x_freeze_from": None,
                "x_freeze_to": None,
            })
    accounts = pd.DataFrame(rows)
    ent = entities.set_index("entity_id")
    accounts["x_scale_usd"] = accounts["entity_id"].map(ent["x_scale_usd"])
    accounts["x_acquired"] = accounts["entity_id"].map(ent["x_acquired"]).astype(bool)
    accounts["x_entity_from"] = accounts["entity_id"].map(ent["effective_from"])
    accounts["x_entity_currency"] = accounts["entity_id"].map(ent["functional_currency"])

    _assign_pool_headers(cfg, accounts, entities)
    _assign_lifecycle(cfg, accounts)
    accounts["opening_balance_date"] = accounts[["opened_on", "x_entity_from"]].max(axis=1).clip(lower=pd.Timestamp(cfg.start_date))
    _assign_balances(cfg, accounts, entities, rng)
    return accounts


def _assign_pool_headers(cfg: Config, accounts: pd.DataFrame, entities: pd.DataFrame) -> None:
    """One cash-pool header per currency: the holding's concentration account for USD,
    otherwise the operating account of the largest entity using that currency."""
    holding = entities.loc[entities["entity_type"] == "HOLDING", "entity_id"].iloc[0]
    for ccy in cfg.currencies:
        if ccy == cfg.reporting_currency:
            mask = (accounts["entity_id"] == holding) & (accounts["account_type"] == "CONCENTRATION")
        else:
            cands = accounts[(accounts["currency"] == ccy) & (accounts["account_type"] == "OPERATING")]
            if cands.empty:
                continue
            pref = cands[cands["x_functional"] & ~cands["x_acquired"]]
            if pref.empty:
                pref = cands[~cands["x_acquired"]] if (~cands["x_acquired"]).any() else cands
            best = pref.sort_values(["x_scale_usd", "account_id"], ascending=[False, True]).index[0]
            mask = accounts.index == best
        accounts.loc[mask, "is_pool_header"] = True


def _assign_lifecycle(cfg: Config, accounts: pd.DataFrame) -> None:
    rng = stream(cfg.seed, "account_lifecycle")
    lc = cfg.lifecycle
    base = (accounts["x_seq"] >= 1) & ~accounts["is_pool_header"] & ~accounts["x_acquired"] & accounts["x_functional"]
    taken: set[int] = set()

    def pick(mask: pd.Series, k: int) -> list[int]:
        idx = [i for i in accounts.index[mask] if i not in taken]
        chosen = sorted(int(i) for i in rng.choice(idx, size=min(k, len(idx)), replace=False)) if idx and k else []
        taken.update(chosen)
        return chosen

    for j, i in enumerate(pick(base & accounts["account_type"].isin(["COLLECTION", "DEPOSIT"]), lc["new_accounts"])):
        accounts.loc[i, "opened_on"] = pd.Timestamp(NEW_ACCOUNT_DATES[j % len(NEW_ACCOUNT_DATES)])
    for j, i in enumerate(pick(base & accounts["account_type"].isin(["COLLECTION", "DEPOSIT"]), lc["closed_accounts"])):
        accounts.loc[i, "closed_on"] = pd.Timestamp(CLOSE_DATES[j % len(CLOSE_DATES)])
    for i in pick(base & (accounts["account_type"] == "COLLECTION"), lc["frozen_accounts"]):
        accounts.loc[i, "x_freeze_from"] = pd.Timestamp(FREEZE[0])
        accounts.loc[i, "x_freeze_to"] = pd.Timestamp(FREEZE[1])
    accounts["closed_on"] = pd.to_datetime(accounts["closed_on"])
    accounts["x_freeze_from"] = pd.to_datetime(accounts["x_freeze_from"])
    accounts["x_freeze_to"] = pd.to_datetime(accounts["x_freeze_to"])


def _assign_balances(cfg: Config, accounts: pd.DataFrame, entities: pd.DataFrame, rng: np.random.Generator) -> None:
    """Opening balances and sweep targets sized from each entity's activity level."""
    monthly_out_usd = accounts["x_scale_usd"].to_numpy()
    weekly_out_usd = monthly_out_usd * 12 / 52
    rate = accounts["currency"].map(FX_START).to_numpy()
    group_monthly_by_ccy = entities.groupby("functional_currency")["x_scale_usd"].sum()
    targets, openings, overdrafts = [], [], []
    for i, a in enumerate(accounts.itertuples()):
        w, m = weekly_out_usd[i], monthly_out_usd[i]
        u = float(rng.uniform(0.8, 1.5))
        target = np.nan
        if a.is_pool_header and a.currency == cfg.reporting_currency:
            acquired_scale = entities.loc[entities["x_acquired"], "x_scale_usd"].sum()
            opening = 1.3 * entities["x_scale_usd"].sum() + 4.0 * acquired_scale
            overdraft = 0.5 * entities["x_scale_usd"].sum()
        elif a.is_pool_header:
            target = 0.6 * group_monthly_by_ccy.get(a.currency, m)
            opening, overdraft = target * u, 0.5 * target
        elif a.account_type == "OPERATING":
            target = (1.0 if a.x_functional else 0.15) * w
            opening, overdraft = target * u, 0.3 * w
        elif a.account_type == "COLLECTION":
            target = 0.10 * w
            opening, overdraft = target * float(rng.uniform(0.5, 2.0)), 0.0
        elif a.account_type == "PAYROLL":
            target = 0.02 * w
            opening, overdraft = target * float(rng.uniform(1.0, 3.0)), 0.0
        elif a.account_type == "DEPOSIT":
            opening, overdraft = 1.5 * m * u, 0.0
        elif a.account_type == "RESTRICTED":
            opening, overdraft = 0.3 * m * u, 0.0
        else:  # CONCENTRATION that is not a header (not generated today)
            opening, overdraft = m * u, 0.0
        if pd.Timestamp(a.opened_on) > pd.Timestamp(cfg.start_date) and not a.x_acquired:
            opening = 0.0  # brand-new account
        targets.append(target / rate[i])
        openings.append(round(opening / rate[i]))
        overdrafts.append(round(overdraft / rate[i], -3))
    accounts["x_target"] = [np.nan if np.isnan(t) else int(major_to_minor([t], c)[0]) for t, c in zip(targets, accounts["currency"])]
    accounts["opening_balance"] = [int(major_to_minor([o], c)[0]) for o, c in zip(openings, accounts["currency"])]
    accounts["overdraft_limit"] = [int(major_to_minor([o], c)[0]) for o, c in zip(overdrafts, accounts["currency"])]


def build_account_events(cfg: Config, accounts: pd.DataFrame, users: pd.DataFrame) -> pd.DataFrame:
    reviewer = users_by_role(users, "RISK_REVIEWER")[0]
    rows = []
    for a in accounts.itertuples():
        rows.append((a.account_id, stamp(day(a.opened_on), 9 * 3600), "OPENED", None, "ACTIVE", ADMIN_USER, "Account opened at the bank"))
        if pd.notna(a.x_freeze_from):
            rows.append((a.account_id, stamp(day(a.x_freeze_from), 10 * 3600), "FROZEN", "ACTIVE", "FROZEN", reviewer,
                         "Compliance hold: refreshed KYC documents requested"))
            rows.append((a.account_id, stamp(day(a.x_freeze_to), 15 * 3600), "UNFROZEN", "FROZEN", "ACTIVE", reviewer,
                         "KYC documents received and verified"))
        if pd.notna(a.closed_on):
            rows.append((a.account_id, stamp(day(a.closed_on), 18 * 3600), "CLOSED", "ACTIVE", "CLOSED", ADMIN_USER,
                         "Account rationalisation; balance swept to the pool header"))
    ev = pd.DataFrame(rows, columns=["account_id", "event_ts", "event_type", "from_status", "to_status", "actor_id", "reason"])
    ev["event_ts"] = pd.to_datetime(ev["event_ts"])
    ev = ev.sort_values(["event_ts", "account_id"], kind="mergesort").reset_index(drop=True)
    ev.insert(0, "event_id", ids.sequence("BAE", cfg.cycle_year, 6, len(ev)))
    last = ev.groupby("account_id")["to_status"].last()
    accounts["status_at_end"] = accounts["account_id"].map(last)
    return ev


def build_fx_rates(cfg: Config) -> pd.DataFrame:
    """Daily closing rates: correlated geometric random walks plus two documented shocks."""
    rng = stream(cfg.seed, "fx")
    # Start early enough to convert invoices carried in from before the period.
    first = cal.roll_forward(day(cfg.start_date) - np.timedelta64(cfg.lookback_days, "D"))
    dates = cal.business_days(first, cfg.actuals_end)
    n, dt = len(dates), 1.0 / 252
    common = rng.standard_normal(n)
    frames = []
    for ccy in cfg.foreign_currencies:
        z = 0.5 * common + np.sqrt(0.75) * rng.standard_normal(n)
        r = (FX_DRIFT[ccy] - 0.5 * FX_VOL[ccy] ** 2) * dt + FX_VOL[ccy] * np.sqrt(dt) * z
        r[0] = 0.0
        for c, d, jump in FX_SHOCKS:
            hit = np.nonzero(dates == np.datetime64(d))[0]
            if c == ccy and hit.size:
                r[hit[0]] += np.log1p(jump)
        level = FX_START[ccy] * np.exp(np.cumsum(r))
        frames.append(pd.DataFrame({
            "rate_id": [ids.rate_id(d, ccy) for d in dates],
            "rate_date": pd.to_datetime(dates),
            "base_currency": ccy,
            "quote_currency": cfg.reporting_currency,
            "rate": [float(f"{v:.8f}") for v in level],
            "rate_type": "CLOSING",
            "source": "SYNTHETIC_GBM",
            "recorded_at": pd.to_datetime(stamp(dates, 16 * 3600)),
        }))
    return pd.concat(frames).sort_values(["rate_date", "base_currency"]).reset_index(drop=True)


def build_scenarios(cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    start = pd.Timestamp(cfg.start_date)
    published = pd.Timestamp("2025-12-15 10:00:00")
    recal = pd.Timestamp("2026-05-25 10:00:00")
    scenarios = pd.DataFrame([
        ("SCN-BASE-V01", "BASE", 1, "Base", "Latest known expected dates and amounts; FX held at the cutoff rate.",
         start, None, "ACTIVE", None, published),
        ("SCN-DELAY-V01", "DELAY", 1, "Delayed receipt", "Customer receipts slip by a number of days set per customer risk tier.",
         start, None, "ACTIVE", None, published),
        ("SCN-STRESS-V01", "STRESS", 1, "Stress",
         "Delayed receipts, collection haircuts on weaker customers, earlier supplier payments, weaker operating receipts and an 8% USD appreciation.",
         start, pd.Timestamp("2026-05-31"), "RETIRED", None, published),
        ("SCN-STRESS-V02", "STRESS", 2, "Stress",
         "As V01 but with a 10% USD appreciation, recalibrated after the May GBP shock.",
         pd.Timestamp("2026-06-01"), None, "ACTIVE", "SCN-STRESS-V01", recal),
    ], columns=["scenario_id", "scenario_code", "version", "scenario_name", "description", "effective_from",
                "effective_to", "status", "supersedes_scenario_id", "created_at"])
    scenarios["created_by"] = ADMIN_USER
    assumptions = pd.DataFrame([
        ("ASM-0001", "AR_DELAY_DAYS", "risk_tier", "A", "0", "days", "Tier A customers pay on time even in a downturn"),
        ("ASM-0002", "AR_DELAY_DAYS", "risk_tier", "B", "7", "days", "Tier B customers stretch payment by a week"),
        ("ASM-0003", "AR_DELAY_DAYS", "risk_tier", "C", "21", "days", "Tier C customers stretch payment by three weeks"),
        ("ASM-0004", "AR_DELAY_DAYS", "risk_tier", "D", "45", "days", "Tier D customers stretch payment by six weeks"),
        ("ASM-0005", "AR_COLLECTION_RATE", "risk_tier", "C", "0.90", "ratio", "10% of tier C receipts are not collected in the horizon"),
        ("ASM-0006", "AR_COLLECTION_RATE", "risk_tier", "D", "0.60", "ratio", "40% of tier D receipts are not collected in the horizon"),
        ("ASM-0007", "AP_TIMING_SHIFT_DAYS", None, None, "-5", "days", "Suppliers demand payment five days earlier"),
        ("ASM-0008", "RUN_RATE_INFLOW_FACTOR", None, None, "0.85", "ratio", "Small operating receipts fall 15%"),
        ("ASM-0009", "FX_SHOCK_PCT", "currency_not", "USD", "-8", "pct", "USD appreciates 8% against every other currency"),
        ("ASM-0010", "FX_SHOCK_PCT", "currency_not", "USD", "-10", "pct", "USD appreciates 10% against every other currency"),
    ], columns=["assumption_id", "parameter", "filter_field", "filter_value", "value", "unit", "rationale"])
    delay = ["ASM-0001", "ASM-0002", "ASM-0003", "ASM-0004"]
    links = []
    for sid, members in [
        ("SCN-DELAY-V01", delay),
        ("SCN-STRESS-V01", delay + ["ASM-0005", "ASM-0006", "ASM-0007", "ASM-0008", "ASM-0009"]),
        ("SCN-STRESS-V02", delay + ["ASM-0005", "ASM-0006", "ASM-0007", "ASM-0008", "ASM-0010"]),
    ]:
        links += [(sid, a, k + 1) for k, a in enumerate(members)]
    links_df = pd.DataFrame(links, columns=["scenario_id", "assumption_id", "apply_order"])
    return scenarios, assumptions, links_df
