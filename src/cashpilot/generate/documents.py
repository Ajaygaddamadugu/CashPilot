"""Business documents, expected cash flows and the actual cash they produce.

Receivables, payables (including large one-offs), recurring schedules (payroll, rent, tax,
debt service), weekly run-rate estimates and manual submissions by account holders.

Actual behaviour comes from documented rules, never from independently random labels:
  * payment delay is drawn from a distribution chosen by the customer's risk tier
  * some customers pay part now and the rest later, some pay several invoices at once
  * risky suppliers' bills can be put on hold; treasury defers a few payments
  * customers that never pay are marked overdue after 30 days and written off after 90
Every outcome becomes explicit records: lifecycle events, forecast revisions and the
planned ledger postings ("moves") that the ledger simulation books.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from cashpilot.core import calendar as cal
from cashpilot.core import ids
from cashpilot.core.config import Config
from cashpilot.core.money import from_usd, major_to_minor, to_usd
from cashpilot.core.rng import stream
from cashpilot.generate.common import (
    FX_START, INFLOW_MIX, INFLOW_MULTIPLIER, OUTFLOW_MIX, day, migration_stamp, round_to, stamp,
)
from cashpilot.generate.master import SYSTEM_USER, users_by_role

DAY = np.timedelta64(1, "D")
SEC = np.timedelta64(1, "s")
HOUR = 3600

P_NEVER = {"A": 0.0, "B": 0.0, "C": 0.03, "D": 0.12}      # customer never pays
P_PARTIAL = {"A": 0.02, "B": 0.04, "C": 0.08, "D": 0.10}  # pays in two instalments
P_ADVISE = {"A": 0.30, "B": 0.50, "C": 0.60, "D": 0.40}   # warns of a late payment in advance
P_BULK = 0.30                                              # same-week invoices paid in one transfer
P_HOLD = 0.15                                              # tier C/D supplier bills put on hold
P_DEFER = 0.04                                             # treasury defers a payment by 1-2 weeks
P_MANUAL_REALISED = 0.80


# ----------------------------------------------------------------------- helpers

class Rates:
    """Point-in-time lookups in the generated FX table (USD per unit)."""

    def __init__(self, fx: pd.DataFrame, reporting: str):
        self.reporting = reporting
        self.by_ccy = {}
        for ccy, g in fx.groupby("base_currency"):
            g = g.sort_values("rate_date")
            self.by_ccy[ccy] = (g["rate_date"].to_numpy(dtype="datetime64[D]"), g["rate"].to_numpy(), g["rate_id"].to_numpy())

    def on_or_before(self, ccy: str, d) -> tuple[str | None, float]:
        if ccy == self.reporting:
            return None, 1.0
        dates, rates, rids = self.by_ccy[ccy]
        i = int(np.searchsorted(dates, np.datetime64(d, "D"), side="right")) - 1
        return str(rids[i]), float(rates[i])

    def before(self, ccy: str, d) -> tuple[str | None, float]:
        if ccy == self.reporting:
            return None, 1.0
        dates, rates, rids = self.by_ccy[ccy]
        i = int(np.searchsorted(dates, np.datetime64(d, "D"), side="left")) - 1
        return str(rids[i]), float(rates[i])


class AccountBook:
    """Which account an entity uses for what, respecting opening and closing dates."""

    def __init__(self, accounts: pd.DataFrame):
        self.accounts = accounts
        self.open = dict(zip(accounts["account_id"], accounts["opening_balance_date"].to_numpy(dtype="datetime64[D]")))
        close = accounts["closed_on"].to_numpy(dtype="datetime64[D]")
        self.close = {a: (None if np.isnat(c) else c) for a, c in zip(accounts["account_id"], close)}
        self.ccy = dict(zip(accounts["account_id"], accounts["currency"]))
        self.by_key: dict[tuple, list[str]] = {}
        for row in accounts.sort_values(["entity_id", "x_seq"]).itertuples():
            self.by_key.setdefault((row.entity_id, row.currency, row.account_type), []).append(row.account_id)

    def active(self, acct: str, d) -> bool:
        d = np.datetime64(d, "D")
        c = self.close[acct]
        return self.open[acct] <= d and (c is None or d < c)

    def find(self, entity: str, ccy: str, types: list[str], d_from, d_to=None) -> str | None:
        for t in types:
            for a in self.by_key.get((entity, ccy, t), []):
                if self.active(a, d_from) and (d_to is None or self.active(a, d_to)):
                    return a
        return None

    def operating(self, entity: str, ccy: str) -> str | None:
        for t in ("OPERATING", "CONCENTRATION"):
            found = self.by_key.get((entity, ccy, t))
            if found:
                return found[0]
        return None

    def currency_of(self, acct: str) -> str:
        return self.ccy[acct]


def allocate(total: int, weights) -> list[int]:
    """Split an integer total proportionally (largest remainder, deterministic)."""
    w = np.asarray(weights, dtype=float)
    if total <= 0 or w.sum() <= 0:
        return [0] * len(w)
    raw = total * w / w.sum()
    out = np.floor(raw).astype(int)
    for i in np.argsort(-(raw - out), kind="mergesort")[: total - int(out.sum())]:
        out[i] += 1
    return out.tolist()


def _ts(d, rng: np.random.Generator, lo_h: float, hi_h: float) -> np.datetime64:
    return stamp(np.datetime64(d, "D"), int(rng.integers(int(lo_h * HOUR), int(hi_h * HOUR))))


def _month_end_weights(days: np.ndarray) -> np.ndarray:
    """Invoicing peaks in the last four business days of each month."""
    s = pd.Series(pd.to_datetime(days))
    rank = s.groupby(s.dt.to_period("M")).rank(ascending=False)
    return np.where(rank.to_numpy() <= 4, 1.6, 1.0)


def _delay(tier: str, rng: np.random.Generator) -> int:
    if tier == "A":
        return int(np.clip(round(rng.normal(0.0, 2.0)), -5, 7))
    shape, scale = {"B": (2.0, 4.0), "C": (2.0, 10.0), "D": (2.0, 22.0)}[tier]
    return int(round(rng.gamma(shape, scale)))


@dataclass
class Context:
    cfg: Config
    entities: pd.DataFrame
    accounts: pd.DataFrame
    counterparties: pd.DataFrame
    users: pd.DataFrame
    rates: Rates
    book: AccountBook

    def __post_init__(self):
        self.end = np.datetime64(self.cfg.actuals_end, "D")
        self.end_ts = stamp(self.end, 24 * HOUR - 1)
        self.schedule_end = np.datetime64(self.cfg.schedule_end, "D")
        self.analysts = users_by_role(self.users, "OPS_ANALYST")
        self.reviewers = users_by_role(self.users, "RISK_REVIEWER")
        holders = self.users[self.users["role"] == "ACCOUNT_HOLDER"]
        self.holder = dict(zip(holders["entity_id"], holders["user_id"]))
        self.eff = dict(zip(self.entities["entity_id"], self.entities["effective_from"].to_numpy(dtype="datetime64[D]")))
        self.func = dict(zip(self.entities["entity_id"], self.entities["functional_currency"]))
        self.scale = dict(zip(self.entities["entity_id"], self.entities["x_scale_usd"]))
        self.months = {e: (self.end - self.eff[e]).astype(int) / 30.44 for e in self.eff}
        cp = self.counterparties
        self.tier = dict(zip(cp["counterparty_id"], cp["risk_tier"]))
        self.terms = dict(zip(cp["counterparty_id"], cp["payment_terms_days"]))
        self.cp_ccy = dict(zip(cp["counterparty_id"], cp["default_currency"]))
        self.cp_name = dict(zip(cp["counterparty_id"], cp["counterparty_name"]))

    def pool(self, kind: str, entity: str, domestic_share: float):
        cp = self.counterparties[self.counterparties["counterparty_type"] == kind]
        dom = cp[cp["default_currency"] == self.func[entity]]
        foreign = cp[cp["default_currency"] != self.func[entity]]
        if dom.empty:
            dom = cp
        def norm(df):
            w = df["x_weight"].to_numpy()
            return df["counterparty_id"].to_numpy(), w / w.sum()
        return norm(dom), (norm(foreign) if len(foreign) else norm(dom)), domestic_share

    @staticmethod
    def pick(pool, rng: np.random.Generator) -> str:
        (dom_ids, dom_w), (for_ids, for_w), share = pool
        if rng.random() < share:
            return str(dom_ids[rng.choice(len(dom_ids), p=dom_w)])
        return str(for_ids[rng.choice(len(for_ids), p=for_w)])


@dataclass
class Documents:
    receivables: pd.DataFrame
    payables: pd.DataFrame
    cf_items: pd.DataFrame
    moves: pd.DataFrame
    allocations: pd.DataFrame
    receivable_events: pd.DataFrame
    payable_events: pd.DataFrame
    revisions: pd.DataFrame
    counts: dict


class _Collector:
    """Accumulates planned records; keys tie them together until IDs are assigned."""

    def __init__(self):
        self.cf: list[dict] = []
        self.moves: list[dict] = []
        self.allocs: list[dict] = []
        self.ar_events: list[dict] = []
        self.ap_events: list[dict] = []
        self.revisions: list[dict] = []
        self.next_pkey = 0

    def pkey(self) -> int:
        self.next_pkey += 1
        return self.next_pkey

    def revision(self, cf_key, ts, rtype, reason, actor, new_date=None, new_amount=None):
        self.revisions.append({"x_key": cf_key, "recorded_at": ts, "revision_type": rtype, "reason": reason,
                               "actor_id": actor, "new_expected_date": new_date, "new_amount": new_amount})


# ---------------------------------------------------------------- recurring flows

def _recurring(ctx: Context, col: _Collector, rng: np.random.Generator) -> int:
    count = 0
    for e in ctx.entities.itertuples():
        func, scale, eff = e.functional_currency, e.x_scale_usd, ctx.eff[e.entity_id]
        rate0 = FX_START[func]
        recorded = migration_stamp(eff)
        op = ctx.book.operating(e.entity_id, func)
        plans = []
        for m in cal.month_starts(eff, ctx.schedule_end):
            month = pd.Timestamp(m)
            plans.append(("PAYROLL", "PAYROLL_SYSTEM", cal.roll_backward(np.datetime64(month.replace(day=25).date())), OUTFLOW_MIX["payroll"], 0.015))
            plans.append(("RENT", "LEASE_SYSTEM", cal.roll_forward(np.datetime64(month.date())), OUTFLOW_MIX["rent"], 0.0))
            if e.size_tier == "L" and e.entity_type == "OPERATING":
                plans.append(("DEBT_SERVICE", "LOAN_SYSTEM", cal.roll_backward(np.datetime64(month.replace(day=28).date())), OUTFLOW_MIX["debt"], 0.0))
            if month.month in (1, 4, 7, 10):
                plans.append(("TAX", "TAX_CALENDAR", cal.roll_forward(np.datetime64(month.replace(day=15).date())), OUTFLOW_MIX["tax_quarterly"], 0.08))
        for cat, source, d, share, noise in plans:
            if d < eff or d > ctx.schedule_end:
                continue
            acct = (ctx.book.find(e.entity_id, func, ["PAYROLL"], d) if cat == "PAYROLL" else None) or op
            planned = round_to(share * scale / rate0, 100.0)[()]
            amount = int(major_to_minor([planned], func)[0])
            key = f"REC:{e.entity_id}:{cat}:{d}"
            col.cf.append({"x_key": key, "entity_id": e.entity_id, "account_id": acct, "direction": "OUTFLOW",
                           "flow_category": cat, "source_system": source, "currency": func, "amount": amount,
                           "expected_date": d, "recorded_at": recorded, "created_by": SYSTEM_USER,
                           "source_reference": f"{source}-{str(d)}"})
            count += 1
            if d <= ctx.end:
                actual = int(major_to_minor([round(planned * (1 + rng.normal(0.0, noise)))], func)[0]) if noise else amount
                ts = _ts(d, rng, 10, 14)
                pk = col.pkey()
                col.moves.append({"pkey": pk, "account_id": acct, "posting_date": d, "recorded_at": ts, "amount": -actual,
                                  "entry_type": cat, "x_key": key, "description": f"{cat.replace('_', ' ').title()} {str(d)[:7]}",
                                  "x_prefund": cat in ("PAYROLL", "TAX")})
                col.revision(key, ts + SEC, "SETTLED", "REALIZED", SYSTEM_USER)
    return count


def _run_rate(ctx: Context, col: _Collector, rng: np.random.Generator) -> int:
    """Weekly estimates for the many small operating flows that are not forecast one by one."""
    count = 0
    first_wed = np.datetime64(ctx.cfg.start_date, "D")
    while pd.Timestamp(first_wed).weekday() != 2:
        first_wed += DAY
    for e in ctx.entities.itertuples():
        func, scale, eff = e.functional_currency, e.x_scale_usd, ctx.eff[e.entity_id]
        op = ctx.book.operating(e.entity_id, func)
        weekly = scale * 12 / 52 / FX_START[func]
        budget_in = round_to(weekly * INFLOW_MULTIPLIER * INFLOW_MIX["operating"] * (1 + rng.normal(0, 0.10)), 100.0)[()]
        budget_out = round_to(weekly * OUTFLOW_MIX["operating"] * (1 + rng.normal(0, 0.10)), 100.0)[()]
        recorded = migration_stamp(eff)
        d = first_wed
        while d <= ctx.schedule_end:
            if d >= eff:
                for direction, budget in (("INFLOW", budget_in), ("OUTFLOW", budget_out)):
                    key = f"RR:{e.entity_id}:{direction}:{d}"
                    col.cf.append({"x_key": key, "entity_id": e.entity_id, "account_id": op, "direction": direction,
                                   "flow_category": "OPERATING_RUN_RATE", "source_system": "RUN_RATE_MODEL", "currency": func,
                                   "amount": int(major_to_minor([budget], func)[0]), "expected_date": d,
                                   "recorded_at": recorded, "created_by": SYSTEM_USER,
                                   "source_reference": f"RUNRATE-{e.entity_id}-{direction[:2]}-{str(d)}"})
                    count += 1
            d += 7 * DAY
    return count


def _manual(ctx: Context, col: _Collector, rng: np.random.Generator, n: int) -> int:
    """Ad-hoc expected flows submitted by account holders; about a fifth never happen."""
    ents = ctx.entities
    w = ents["x_scale_usd"].to_numpy()
    seq: dict[str, int] = {}
    for k in range(n):
        e = ents.iloc[int(rng.choice(len(ents), p=w / w.sum()))]
        func, eff = e.functional_currency, ctx.eff[e.entity_id]
        direction = "INFLOW" if rng.random() < 0.6 else "OUTFLOW"
        amount_major = round(e.x_scale_usd * float(rng.lognormal(np.log(0.25), 0.6)) / FX_START[func], -2)
        lo = eff + 14 * DAY
        span = int((ctx.schedule_end - 7 * DAY - lo).astype(int))
        expected = cal.roll_forward(lo + int(rng.integers(0, span)) * DAY)
        recorded_day = expected - int(rng.integers(5, 61)) * DAY
        recorded_day = min(max(recorded_day, eff), ctx.end - int(rng.integers(0, 10)) * DAY)
        if recorded_day >= expected:
            recorded_day = expected - DAY
        recorded = _ts(recorded_day, rng, 9, 18)
        seq[e.entity_id] = seq.get(e.entity_id, 0) + 1
        key = f"MAN:{k}"
        amount = int(major_to_minor([amount_major], func)[0])
        col.cf.append({"x_key": key, "entity_id": e.entity_id, "account_id": ctx.book.operating(e.entity_id, func),
                       "direction": direction, "flow_category": "OTHER", "source_system": "MANUAL", "currency": func,
                       "amount": amount, "expected_date": expected, "recorded_at": recorded,
                       "created_by": ctx.holder[e.entity_id],
                       "source_reference": f"MAN-{e.entity_id[4:]}-{seq[e.entity_id]:04d}"})
        realised = rng.random() < P_MANUAL_REALISED
        shift = int(round(rng.normal(0, 3)))
        factor = 1 + rng.normal(0, 0.05)
        if expected > ctx.end:
            continue
        if realised:
            d = cal.roll_forward(max(expected + shift * DAY, recorded_day + DAY))
            if d > ctx.end:
                continue
            ts = _ts(d, rng, 9, 17)
            actual = int(major_to_minor([round(amount_major * factor, 2)], func)[0])
            pk = col.pkey()
            col.moves.append({"pkey": pk, "account_id": ctx.book.operating(e.entity_id, func), "posting_date": d, "recorded_at": ts,
                              "amount": actual if direction == "INFLOW" else -actual,
                              "entry_type": "OTHER_RECEIPT" if direction == "INFLOW" else "OTHER_PAYMENT",
                              "x_key": key, "description": "Manually forecast item realised", "x_prefund": False})
            col.revision(key, ts + SEC, "SETTLED", "REALIZED", SYSTEM_USER)
        elif rng.random() < 0.5:
            cancel_day = expected + int(rng.integers(5, 21)) * DAY
            if cancel_day <= ctx.end:
                col.revision(key, _ts(cancel_day, rng, 9, 17), "CANCELLED", "NOT_REALIZED", ctx.holder[e.entity_id])
    return n


# ------------------------------------------------------------------- receivables

def _receivables(ctx: Context, col: _Collector, rng: np.random.Generator, n_ar: int) -> list[dict]:
    cfg = ctx.cfg
    ents = ctx.entities
    weight = np.array([ctx.scale[e] * ctx.months[e] for e in ents["entity_id"]])
    lam = {e: n_ar * ctx.scale[e] / weight.sum() for e in ents["entity_id"]}  # invoices per month
    mean_usd = {e: INFLOW_MULTIPLIER * INFLOW_MIX["ar"] * ctx.scale[e] / lam[e] for e in lam}
    pools = {e: ctx.pool("CUSTOMER", e, 0.85) for e in lam}

    def make(entity: str, inv_day, recorded, prehistory: bool) -> dict | None:
        func = ctx.func[entity]
        cust = ctx.pick(pools[entity], rng)
        tier, terms, cust_ccy = ctx.tier[cust], ctx.terms[cust], ctx.cp_ccy[cust]
        due = inv_day + terms * DAY
        if cust_ccy == func:
            ccy, cross = func, False
        elif ctx.book.find(entity, cust_ccy, ["COLLECTION", "OPERATING"], max(inv_day, ctx.eff[entity])):
            ccy, cross = cust_ccy, False
        elif cust_ccy == cfg.reporting_currency:
            ccy, cross = cust_ccy, True  # USD invoice collected into a functional-currency account
        else:
            ccy, cross = func, False
        amount_usd = float(rng.lognormal(np.log(mean_usd[entity]) - 0.5, 1.0))
        amount = max(int(major_to_minor([amount_usd / FX_START[ccy]], ccy)[0]), int(major_to_minor([50.0], ccy)[0]))
        never = rng.random() < P_NEVER[tier]
        pay1 = cal.roll_forward(due + _delay(tier, rng) * DAY)
        payments = []
        if not never:
            if not cross and rng.random() < P_PARTIAL[tier]:
                a1 = int(round(amount * rng.uniform(0.4, 0.7)))
                pay2 = cal.roll_forward(pay1 + int(rng.integers(10, 41)) * DAY)
                payments = [[pay1, a1], [pay2, amount - a1]]
            else:
                payments = [[pay1, amount]]
        if prehistory and payments and payments[0][0] < ctx.eff[entity]:
            return None  # settled before the entity joined the dataset
        acct_ccy = func if cross else ccy
        last = payments[-1][0] if payments else ctx.schedule_end
        acct = ctx.book.find(entity, acct_ccy, ["COLLECTION", "OPERATING"], max(inv_day, ctx.eff[entity]), min(last, ctx.end)) \
            or ctx.book.operating(entity, acct_ccy)
        rec = {"entity_id": entity, "account_id": acct, "counterparty_id": cust, "invoice_date": inv_day, "due_date": due,
               "currency": ccy, "amount": amount, "recorded_at": recorded, "x_tier": tier, "x_cross": cross,
               "x_account_currency": acct_ccy, "x_payments": payments, "x_never": never, "x_advice": None, "x_promise": None}
        final = payments[-1][0] if payments else None
        if final is not None and (final - cal.roll_forward(due)).astype(int) >= 7 and rng.random() < P_ADVISE[tier]:
            ts = _ts(final - int(rng.integers(3, 16)) * DAY, rng, 10, 16)
            if ts > recorded + 3600 * SEC:
                rec["x_advice"] = (ts, cal.roll_forward(final + int(rng.integers(-2, 3)) * DAY))
        if never and tier == "D" and rng.random() < 0.3:
            ts = _ts(due + int(rng.integers(5, 21)) * DAY, rng, 10, 16)
            if recorded < ts <= ctx.end_ts:
                rec["x_promise"] = (ts, cal.roll_forward(due + 30 * DAY))
        return rec

    records: list[dict] = []
    for e in ents["entity_id"]:  # open items carried in from before the entity's start
        eff = ctx.eff[e]
        days = cal.business_days(eff - cfg.lookback_days * DAY, eff - DAY)
        n_pre = int(round(lam[e] * cfg.lookback_days / 30.44))
        for d in np.sort(rng.choice(days, size=n_pre)):
            r = make(e, d, migration_stamp(eff), True)
            if r:
                records.append(r)
    n_in = n_ar - len(records)
    if n_in < 0:
        records, n_in = records[:n_ar], 0
    for e, k in zip(ents["entity_id"], allocate(n_in, weight)):
        days = cal.business_days(ctx.eff[e], ctx.end)
        w = _month_end_weights(days)
        for d in np.sort(rng.choice(days, size=k, p=w / w.sum())):
            records.append(make(e, d, _ts(d, rng, 9, 17), False))

    _bulk_payments(ctx, records, rng)
    return records


def _bulk_payments(ctx: Context, records: list[dict], rng: np.random.Generator) -> None:
    """Some customers settle several same-week invoices with one transfer (N:M settlement)."""
    groups: dict[tuple, list[int]] = {}
    for i, r in enumerate(records):
        if len(r["x_payments"]) == 1 and not r["x_cross"] and r["x_payments"][0][0] <= ctx.end:
            iso = pd.Timestamp(r["x_payments"][0][0]).isocalendar()
            groups.setdefault((r["counterparty_id"], r["entity_id"], r["account_id"], r["currency"], iso[0], iso[1]), []).append(i)
    for key in sorted(groups):
        members = groups[key]
        if len(members) >= 2 and rng.random() < P_BULK:
            common = max(records[i]["x_payments"][0][0] for i in members)
            for i in members:
                records[i]["x_payments"][0][0] = common
                records[i]["x_bulk"] = key


def _receivable_flows(ctx: Context, col: _Collector, records: list[dict], rng: np.random.Generator) -> None:
    grace = ctx.cfg.policy["overdue_grace_days"]
    write_off = ctx.cfg.policy["write_off_after_days"]
    entries: dict = {}  # (bulk key or (idx, n)) -> (pkey, timestamp)
    seen_entries: set[int] = set()
    for i, r in enumerate(records):
        key = f"AR:{i}"
        r["x_key"] = key
        if r["x_cross"]:
            rid, rate = ctx.rates.before(ctx.func[r["entity_id"]], pd.Timestamp(r["recorded_at"]).date())
            cf_amount = int(from_usd([r["amount"]], r["x_account_currency"], [rate])[0])
            orig = (r["currency"], r["amount"], rid)
        else:
            cf_amount, orig = r["amount"], (None, None, None)
        col.cf.append({"x_key": key, "entity_id": r["entity_id"], "account_id": r["account_id"], "direction": "INFLOW",
                       "flow_category": "AR_COLLECTION", "source_system": "AR_SUBLEDGER", "x_receivable": i,
                       "counterparty_id": r["counterparty_id"], "x_invoice": i, "currency": r["x_account_currency"],
                       "amount": cf_amount, "original_currency": orig[0], "original_amount": orig[1], "fx_rate_id": orig[2],
                       "expected_date": cal.roll_forward(r["due_date"]), "recorded_at": r["recorded_at"], "created_by": SYSTEM_USER})

        timeline = [(r["recorded_at"], 0, "CREATED", None)]
        remaining = r["amount"]
        for n, (d, amt) in enumerate(r["x_payments"]):
            if d > ctx.end:
                break
            gkey = r.get("x_bulk") or (i, n)
            if gkey not in entries:
                entries[gkey] = (col.pkey(), _ts(d, rng, 9, 17))
            pk, ts = entries[gkey]
            if r["x_cross"]:
                rid, rate = ctx.rates.on_or_before(r["x_account_currency"], d)
                posted = int(from_usd([amt], r["x_account_currency"], [rate])[0])
                col.moves.append({"pkey": pk, "account_id": r["account_id"], "posting_date": d, "recorded_at": ts, "amount": posted,
                                  "entry_type": "AR_RECEIPT", "counterparty_id": r["counterparty_id"], "fx_rate_id": rid,
                                  "original_currency": r["currency"], "original_amount": amt,
                                  "description": f"Receipt from {ctx.cp_name[r['counterparty_id']]} (USD invoice converted)", "x_prefund": False})
            elif pk not in seen_entries:
                seen_entries.add(pk)
                col.moves.append({"pkey": pk, "account_id": r["account_id"], "posting_date": d, "recorded_at": ts, "amount": 0,
                                  "entry_type": "AR_RECEIPT", "counterparty_id": r["counterparty_id"],
                                  "description": f"Receipt from {ctx.cp_name[r['counterparty_id']]}", "x_prefund": False})
            col.allocs.append({"pkey": pk, "x_receivable": i, "currency": r["currency"], "allocated_amount": amt, "allocation_date": d,
                               "x_acct_amount": None if r["x_cross"] else amt})
            remaining -= amt
            timeline.append((ts, 1, "PAY", (amt, pk, remaining)))
            if remaining:
                col.revision(key, ts + SEC, "AMOUNT_CHANGE", "PARTIAL_PAYMENT", SYSTEM_USER, new_amount=remaining)
            else:
                col.revision(key, ts + SEC, "SETTLED", "PAID_IN_FULL", SYSTEM_USER)
        paid_ts = timeline[-1][0] if remaining == 0 else None
        overdue_ts = max(stamp(r["due_date"] + grace * DAY, 6 * HOUR), r["recorded_at"] + 60 * SEC)
        if overdue_ts <= ctx.end_ts and (paid_ts is None or paid_ts > overdue_ts):
            timeline.append((overdue_ts, 2, "OVERDUE", None))
        if r["x_never"]:
            wo_day = cal.first_business_days_of_months(r["due_date"] + (write_off + 1) * DAY, r["due_date"] + (write_off + 40) * DAY)
            if len(wo_day) and wo_day[0] <= ctx.end:
                wo_ts = stamp(wo_day[0], 11 * HOUR)
                timeline.append((wo_ts, 3, "WRITE_OFF", None))
                col.revision(key, wo_ts + SEC, "CANCELLED", "WRITTEN_OFF", ctx.analysts[0])
        if r["x_advice"]:
            col.revision(key, r["x_advice"][0], "DATE_CHANGE", "CUSTOMER_ADVISED_DELAY", SYSTEM_USER, new_date=r["x_advice"][1])
        if r["x_promise"]:
            col.revision(key, r["x_promise"][0], "DATE_CHANGE", "CUSTOMER_ADVISED_DELAY", SYSTEM_USER, new_date=r["x_promise"][1])

        state = None
        for ts, _, kind, payload in sorted(timeline, key=lambda x: (x[0], x[1])):
            if kind == "CREATED":
                new, ev, amount, pk = "OPEN", "CREATED", None, None
            elif kind == "PAY":
                amount, pk, left = payload
                new, ev = ("PAID", "PAID") if left == 0 else ("PARTIALLY_PAID", "PARTIAL_PAYMENT")
            elif kind == "OVERDUE":
                if state not in ("OPEN", "PARTIALLY_PAID"):
                    continue
                new, ev, amount, pk = "OVERDUE", "OVERDUE", None, None
            else:
                if state != "OVERDUE":
                    continue
                new, ev, amount, pk = "WRITTEN_OFF", "WRITTEN_OFF", None, None
            actor = ctx.analysts[0] if ev == "WRITTEN_OFF" else SYSTEM_USER
            col.ar_events.append({"x_receivable": i, "event_ts": ts, "event_type": ev, "from_status": state, "to_status": new,
                                  "currency": r["currency"], "amount": amount, "pkey": pk, "actor_id": actor})
            state = new
        r["status_at_end"] = state

    # Receipt amounts for same-currency entries are the sum of their allocations.
    totals: dict[int, int] = {}
    for a in col.allocs:
        if a["x_acct_amount"] is not None:
            totals[a["pkey"]] = totals.get(a["pkey"], 0) + a["x_acct_amount"]
    for m in col.moves:
        if m["entry_type"] == "AR_RECEIPT" and m["pkey"] in totals:
            m["amount"] = totals[m["pkey"]]


# ---------------------------------------------------------------------- payables

def _payables(ctx: Context, col: _Collector, rng: np.random.Generator, n_trade: int) -> list[dict]:
    cfg = ctx.cfg
    ents = ctx.entities
    threshold = cfg.policy["approval_threshold_usd"]
    weight = np.array([ctx.scale[e] * ctx.months[e] for e in ents["entity_id"]])
    lam = {e: n_trade * ctx.scale[e] / weight.sum() for e in ents["entity_id"]}
    share = {e.entity_id: OUTFLOW_MIX["trade_ap"] + (0.0 if (e.size_tier == "L" and e.entity_type == "OPERATING") else OUTFLOW_MIX["debt"])
             for e in ents.itertuples()}
    mean_usd = {e: share[e] * ctx.scale[e] / lam[e] for e in lam}
    pools = {e: ctx.pool("SUPPLIER", e, 0.90) for e in lam}

    def make(entity: str, bill_day, recorded, prehistory: bool) -> dict | None:
        func = ctx.func[entity]
        sup = ctx.pick(pools[entity], rng)
        tier, terms, sup_ccy = ctx.tier[sup], ctx.terms[sup], ctx.cp_ccy[sup]
        ccy = sup_ccy if ctx.book.operating(entity, sup_ccy) else func
        amount_usd = float(rng.lognormal(np.log(mean_usd[entity]) - 0.5, 1.0))
        amount = max(int(major_to_minor([amount_usd / FX_START[ccy]], ccy)[0]), int(major_to_minor([20.0], ccy)[0]))
        due = bill_day + terms * DAY
        planned = cal.roll_backward(due)
        if planned <= bill_day:
            planned = cal.roll_forward(bill_day + DAY)
        rec = {"entity_id": entity, "account_id": ctx.book.operating(entity, ccy), "counterparty_id": sup, "bill_date": bill_day,
               "due_date": due, "currency": ccy, "amount": amount, "category": "TRADE", "is_one_off": False,
               "recorded_at": recorded, "x_large": amount_usd >= threshold, "x_hold": None, "x_defer": None,
               "x_pay": planned, "x_cancel": False}
        if not prehistory and tier in ("C", "D") and rng.random() < P_HOLD:
            hold_day = bill_day + 2 * DAY
            release_day = hold_day + int(rng.integers(10, 31)) * DAY
            rec["x_hold"] = (stamp(hold_day, 10 * HOUR), stamp(release_day, 11 * HOUR))
            if rng.random() < 0.8:
                rec["x_pay"] = cal.roll_forward(release_day + DAY)
            else:
                rec["x_cancel"] = True
        elif not prehistory and rng.random() < P_DEFER:
            ts = stamp(planned - int(rng.integers(2, 6)) * DAY, 15 * HOUR)
            if ts > recorded + 3600 * SEC:
                rec["x_pay"] = cal.roll_forward(planned + int(rng.integers(7, 15)) * DAY)
                rec["x_defer"] = ts
        if prehistory and rec["x_pay"] < ctx.eff[entity]:
            return None
        return rec

    records: list[dict] = []
    for e in ents["entity_id"]:
        eff = ctx.eff[e]
        days = cal.business_days(eff - cfg.lookback_days * DAY, eff - DAY)
        for d in np.sort(rng.choice(days, size=int(round(lam[e] * cfg.lookback_days / 30.44)))):
            r = make(e, d, migration_stamp(eff), True)
            if r:
                records.append(r)
    n_in = n_trade - len(records)
    if n_in < 0:
        records, n_in = records[:n_trade], 0
    for e, k in zip(ents["entity_id"], allocate(n_in, weight)):
        days = cal.business_days(ctx.eff[e], ctx.end)
        w = _month_end_weights(days)
        for d in np.sort(rng.choice(days, size=k, p=w / w.sum())):
            records.append(make(e, d, _ts(d, rng, 9, 17), False))
    return records


def _one_offs(ctx: Context, rng: np.random.Generator, n: int) -> list[dict]:
    """Large non-recurring payments; some are known months ahead, some only days ahead."""
    cfg = ctx.cfg
    ents = ctx.entities
    suppliers = ctx.counterparties[ctx.counterparties["counterparty_type"] == "SUPPLIER"]
    holding = ents.loc[ents["entity_type"] == "HOLDING", "entity_id"].iloc[0]
    records = []
    acquired = ents[ents["x_acquired"]]
    if n and len(acquired):
        acq_day = np.datetime64(cfg.lifecycle["acquisition_date"], "D")
        pay = cal.roll_backward(acq_day - DAY)
        usd_seller = suppliers[suppliers["default_currency"] == cfg.reporting_currency]["counterparty_id"]
        seller = usd_seller.iloc[0] if len(usd_seller) else suppliers["counterparty_id"].iloc[0]
        amount_usd = 4.0 * float(acquired["x_scale_usd"].iloc[0])
        records.append(_one_off_record(ctx, holding, seller, pay, "ACQUISITION", amount_usd, pay - 75 * DAY, rng))
    w = ents["x_scale_usd"].to_numpy()
    cats = ["CAPEX", "TAX_SETTLEMENT", "DEBT_REPAYMENT", "LEGAL_SETTLEMENT"]
    while len(records) < n:
        e = ents.iloc[int(rng.choice(len(ents), p=w / w.sum()))]
        cat = cats[int(rng.choice(4, p=[0.4, 0.2, 0.2, 0.2]))]
        lo = ctx.eff[e.entity_id] + 30 * DAY
        span = int((ctx.schedule_end - 10 * DAY - lo).astype(int))
        pay = cal.roll_forward(lo + int(rng.integers(0, span)) * DAY)
        lead = int(rng.integers(30, 91)) if rng.random() < 0.7 else int(rng.integers(2, 11))
        sup = suppliers["counterparty_id"].iloc[int(rng.integers(len(suppliers)))]
        records.append(_one_off_record(ctx, e.entity_id, sup, pay, cat, e.x_scale_usd * float(rng.uniform(0.5, 1.5)), pay - lead * DAY, rng))
    return records


def _one_off_record(ctx: Context, entity, supplier, pay, category, amount_usd, recorded_day, rng) -> dict:
    func = ctx.func[entity]
    recorded_day = min(max(recorded_day, ctx.eff[entity]), ctx.end - DAY, pay - 2 * DAY)
    return {"entity_id": entity, "account_id": ctx.book.operating(entity, func), "counterparty_id": supplier,
            "bill_date": recorded_day, "due_date": pay, "currency": func,
            "amount": int(major_to_minor([round(amount_usd / FX_START[func], -3)], func)[0]),
            "category": category, "is_one_off": True, "recorded_at": stamp(recorded_day, 10 * HOUR),
            "x_large": True, "x_hold": None, "x_defer": None, "x_pay": pay, "x_cancel": False}


def _payable_flows(ctx: Context, col: _Collector, records: list[dict], rng: np.random.Generator) -> None:
    for i, r in enumerate(records):
        key = f"AP:{i}"
        r["x_key"] = key
        col.cf.append({"x_key": key, "entity_id": r["entity_id"], "account_id": r["account_id"], "direction": "OUTFLOW",
                       "flow_category": "AP_PAYMENT", "source_system": "AP_SUBLEDGER", "x_payable": i,
                       "counterparty_id": r["counterparty_id"], "x_bill": i, "currency": r["currency"], "amount": r["amount"],
                       "expected_date": cal.roll_backward(r["due_date"]) if not r["is_one_off"] else r["due_date"],
                       "recorded_at": r["recorded_at"], "created_by": SYSTEM_USER})
        rec_ts = r["recorded_at"]
        if r["x_large"]:
            nxt = cal.add_business_days(np.datetime64(rec_ts, "D"), 1)
            approve_ts, approver = stamp(nxt, 10 * HOUR), ctx.reviewers[i % len(ctx.reviewers)]
        else:
            approve_ts, approver = rec_ts + 3600 * SEC, SYSTEM_USER
        analyst = ctx.analysts[i % len(ctx.analysts)]
        timeline = [(rec_ts, "CREATED", None, "SCHEDULED", SYSTEM_USER, None), (approve_ts, "APPROVED", "SCHEDULED", "APPROVED", approver, None)]
        state = "APPROVED"
        if r["x_hold"]:
            hold_ts, release_ts = r["x_hold"]
            hold_ts = max(hold_ts, approve_ts + 3600 * SEC)
            timeline.append((hold_ts, "HELD", state, "ON_HOLD", analyst, None))
            col.revision(key, hold_ts + SEC, "DATE_CHANGE", "SUPPLIER_HOLD", analyst,
                         new_date=cal.roll_forward(np.datetime64(hold_ts, "D") + 30 * DAY))
            if r["x_cancel"]:
                timeline.append((release_ts, "CANCELLED", "ON_HOLD", "CANCELLED", analyst, None))
                col.revision(key, release_ts + SEC, "CANCELLED", "PAYMENT_CANCELLED", analyst)
            else:
                timeline.append((release_ts, "RELEASED", "ON_HOLD", "APPROVED", analyst, None))
                col.revision(key, release_ts + SEC, "DATE_CHANGE", "HOLD_RELEASED", analyst, new_date=r["x_pay"])
        if r["x_defer"] is not None:
            col.revision(key, r["x_defer"], "DATE_CHANGE", "PAYMENT_DEFERRED", analyst, new_date=r["x_pay"])
        if not r["x_cancel"] and r["x_pay"] <= ctx.end:
            pk = col.pkey()
            ts = _ts(r["x_pay"], rng, 11, 17)
            col.moves.append({"pkey": pk, "account_id": r["account_id"], "posting_date": r["x_pay"], "recorded_at": ts,
                              "amount": -r["amount"], "entry_type": "AP_PAYMENT", "counterparty_id": r["counterparty_id"],
                              "description": (f"{r['category'].replace('_', ' ').title()} payment to {ctx.cp_name[r['counterparty_id']]}"
                                              if r["is_one_off"] else f"Payment to {ctx.cp_name[r['counterparty_id']]}"),
                              "x_prefund": r["is_one_off"]})
            col.allocs.append({"pkey": pk, "x_payable": i, "currency": r["currency"], "allocated_amount": r["amount"],
                               "allocation_date": r["x_pay"], "x_acct_amount": r["amount"]})
            timeline.append((ts, "PAID", "APPROVED", "PAID", SYSTEM_USER, pk))
            col.revision(key, ts + SEC, "SETTLED", "PAID_IN_FULL", SYSTEM_USER)
        state = None
        for ts, ev, src, dst, actor, pk in sorted(timeline, key=lambda x: x[0]):
            if ts > ctx.end_ts:
                break
            col.ap_events.append({"x_payable": i, "event_ts": ts, "event_type": ev, "from_status": src, "to_status": dst,
                                  "pkey": pk, "actor_id": actor})
            state = dst
        r["status_at_end"] = state


# ------------------------------------------------------------------------ driver

def build_documents(cfg: Config, entities, accounts, counterparties, users, fx, n_duplicates: int) -> Documents:
    ctx = Context(cfg, entities, accounts, counterparties, users, Rates(fx, cfg.reporting_currency), AccountBook(accounts))
    col = _Collector()
    n_recurring = _recurring(ctx, col, stream(cfg.seed, "recurring"))
    n_run_rate = _run_rate(ctx, col, stream(cfg.seed, "run_rate"))
    n_manual = _manual(ctx, col, stream(cfg.seed, "manual"), cfg.volumes["manual_items"])
    budget = cfg.volumes["forecast_items"] - n_recurring - n_run_rate - n_manual - n_duplicates
    n_ar = int(round(budget * 0.55))
    n_ap = budget - n_ar
    if n_ar <= 0 or n_ap <= cfg.volumes["one_off_payments"]:
        raise ValueError("forecast_items is too small for the recurring, run-rate and manual items of this profile")

    ar = _receivables(ctx, col, stream(cfg.seed, "receivables"), n_ar)
    _receivable_flows(ctx, col, ar, stream(cfg.seed, "receivable_flows"))
    ap = _one_offs(ctx, stream(cfg.seed, "one_offs"), cfg.volumes["one_off_payments"])
    ap += _payables(ctx, col, stream(cfg.seed, "payables"), n_ap - len(ap))
    _payable_flows(ctx, col, ap, stream(cfg.seed, "payable_flows"))

    receivables, payables = _finalise_documents(cfg, ar, ap)
    cf_items = _finalise_cf(cfg, col, receivables, payables)
    key_to_cf = dict(zip(cf_items["x_key"], cf_items["cf_id"]))

    moves = pd.DataFrame(col.moves)
    moves["cf_id"] = moves.get("x_key", pd.Series(dtype=object)).map(key_to_cf)
    allocs = pd.DataFrame(col.allocs)
    allocs["receivable_id"] = allocs.get("x_receivable").map(lambda i: None if pd.isna(i) else receivables.at[int(i), "receivable_id"])
    allocs["payable_id"] = allocs.get("x_payable").map(lambda i: None if pd.isna(i) else payables.at[int(i), "payable_id"])

    ar_ev = pd.DataFrame(col.ar_events)
    ar_ev["receivable_id"] = ar_ev["x_receivable"].map(receivables["receivable_id"])
    ap_ev = pd.DataFrame(col.ap_events)
    ap_ev["payable_id"] = ap_ev["x_payable"].map(payables["payable_id"])

    revisions = pd.DataFrame(col.revisions)
    revisions = revisions[revisions["recorded_at"] <= ctx.end_ts].reset_index(drop=True)  # knowledge ends with the period
    revisions["cf_id"] = revisions["x_key"].map(key_to_cf)
    revisions = revisions.merge(cf_items[["cf_id", "currency"]], on="cf_id", how="left")

    counts = {"receivables": len(receivables), "payables": len(payables), "recurring_items": n_recurring,
              "run_rate_items": n_run_rate, "manual_items": n_manual}
    return Documents(receivables, payables, cf_items, moves, allocs, ar_ev, ap_ev, revisions, counts)


def _finalise_documents(cfg: Config, ar: list[dict], ap: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rec = pd.DataFrame(ar)
    rec["x_idx"] = range(len(rec))
    rec = rec.sort_values(["recorded_at", "entity_id", "invoice_date", "x_idx"], kind="mergesort")
    rec["receivable_id"] = ids.sequence("AR", cfg.cycle_year, 6, len(rec))
    rec["invoice_number"] = [f"INV-{e[4:]}-{k:06d}" for e, k in zip(rec["entity_id"], rec.groupby("entity_id").cumcount() + 1)]
    rec = rec.sort_values("x_idx").set_index("x_idx", drop=False)
    rec.index.name = None

    pay = pd.DataFrame(ap)
    pay["x_idx"] = range(len(pay))
    pay = pay.sort_values(["recorded_at", "entity_id", "bill_date", "x_idx"], kind="mergesort")
    pay["payable_id"] = ids.sequence("AP", cfg.cycle_year, 6, len(pay))
    pay["bill_number"] = [f"BILL-{e[4:]}-{k:06d}" for e, k in zip(pay["entity_id"], pay.groupby("entity_id").cumcount() + 1)]
    pay = pay.sort_values("x_idx").set_index("x_idx", drop=False)
    pay.index.name = None
    for df, cols in ((rec, ["invoice_date", "due_date"]), (pay, ["bill_date", "due_date"])):
        for c in cols:
            df[c] = pd.to_datetime(df[c].to_numpy(dtype="datetime64[D]"))
        df["recorded_at"] = pd.to_datetime(df["recorded_at"].to_numpy(dtype="datetime64[s]"))
    return rec, pay


def _finalise_cf(cfg: Config, col: _Collector, receivables: pd.DataFrame, payables: pd.DataFrame) -> pd.DataFrame:
    cf = pd.DataFrame(col.cf)
    cf["receivable_id"] = cf.get("x_receivable").map(lambda i: None if pd.isna(i) else receivables.at[int(i), "receivable_id"])
    cf["payable_id"] = cf.get("x_payable").map(lambda i: None if pd.isna(i) else payables.at[int(i), "payable_id"])
    inv = cf.get("x_invoice").map(lambda i: None if pd.isna(i) else receivables.at[int(i), "invoice_number"])
    bill = cf.get("x_bill").map(lambda i: None if pd.isna(i) else payables.at[int(i), "bill_number"])
    cf["source_reference"] = inv.where(inv.notna(), bill).where(lambda s: s.notna(), cf.get("source_reference"))
    cf["recorded_at"] = pd.to_datetime(cf["recorded_at"].to_numpy(dtype="datetime64[s]"))
    cf["expected_date"] = pd.to_datetime(cf["expected_date"].to_numpy(dtype="datetime64[D]"))
    cf = cf.sort_values(["recorded_at", "entity_id", "flow_category", "source_reference", "x_key"], kind="mergesort").reset_index(drop=True)
    cf["cf_id"] = ids.sequence("CF", cfg.cycle_year, 6, len(cf))
    return cf
