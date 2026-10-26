"""Ledger simulation and bank statements.

1. Book every planned movement from the documents (receipts, payments, payroll, ...).
2. Add the treasury's routine postings: pre-funding of payroll/tax/one-off payments from the
   currency's pool header, and monthly bank fees.
3. Run the cash-pooling routine business day by business day: account closures, weekly
   sweeps to target balances, monthly FX rebalancing of non-USD pool headers into USD and
   monthly interest on deposit accounts. Amounts depend on balances; *which* postings happen
   is scheduled up front.
4. Fill the remaining volume with high-frequency operating flows (card settlements, small
   receipts and payments) so the ledger holds exactly the configured number of entries.

Bank statements are then derived from the ledger (plus any bank-side differences injected
later as labelled anomalies). Nothing here is sampled independently of its source records.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from cashpilot.core import calendar as cal
from cashpilot.core import ids
from cashpilot.core.config import Config
from cashpilot.core.money import major_to_minor, to_usd
from cashpilot.core.rng import stream
from cashpilot.generate.common import DEPOSIT_RATES, FX_START, INFLOW_MIX, INFLOW_MULTIPLIER, OUTFLOW_MIX, day, round_to, stamp
from cashpilot.generate.documents import Documents, Rates, allocate
from cashpilot.generate.master import SYSTEM_USER

DAY = np.timedelta64(1, "D")
HOUR = 3600
WEEKDAY_FACTOR = np.array([1.1, 1.0, 1.0, 1.0, 1.2])
COLUMNS = ["account_id", "posting_date", "recorded_at", "amount", "entry_type", "cf_id", "counterparty_id", "x_transfer",
           "fx_rate_id", "original_currency", "original_amount", "description", "x_pkey"]


@dataclass
class LedgerResult:
    ledger: pd.DataFrame
    allocations: pd.DataFrame
    receivable_events: pd.DataFrame
    payable_events: pd.DataFrame
    revisions: pd.DataFrame


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    with warnings.catch_warnings():  # all-null optional columns are expected here
        warnings.simplefilter("ignore", FutureWarning)
        return pd.concat(frames, ignore_index=True)


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = None
    return df[COLUMNS]


def build_ledger(cfg: Config, entities: pd.DataFrame, accounts: pd.DataFrame, fx: pd.DataFrame, docs: Documents) -> LedgerResult:
    rng = stream(cfg.seed, "ledger")
    start, end = day(cfg.start_date), day(cfg.actuals_end)
    days = cal.business_days(start, end)
    n_days = len(days)
    acct = accounts.reset_index(drop=True)
    n_acct = len(acct)
    a_idx = {a: i for i, a in enumerate(acct["account_id"])}
    ccy = acct["currency"].to_numpy()
    acct_type = acct["account_type"].to_numpy()
    target = acct["x_target"].to_numpy(dtype=float)
    headers = {c: a_idx[a] for c, a in zip(acct.loc[acct["is_pool_header"], "currency"], acct.loc[acct["is_pool_header"], "account_id"])}
    usd_header = headers[cfg.reporting_currency]
    open_day = cal.roll_forward(acct["opening_balance_date"].to_numpy(dtype="datetime64[D]"))
    open_t = np.searchsorted(days, open_day)
    close_raw = acct["closed_on"].to_numpy(dtype="datetime64[D]")
    close_t = np.where(np.isnat(close_raw), n_days + 1, np.searchsorted(days, np.where(np.isnat(close_raw), days[-1], close_raw)))
    freeze_from = acct["x_freeze_from"].to_numpy(dtype="datetime64[D]")
    freeze_to = acct["x_freeze_to"].to_numpy(dtype="datetime64[D]")
    rates = Rates(fx, cfg.reporting_currency)
    transfer = iter(range(1, 10**9))

    def active(a: int, t: int) -> bool:
        return open_t[a] <= t < close_t[a]

    def frozen(a: int, t: int) -> bool:
        return not np.isnat(freeze_from[a]) and freeze_from[a] <= days[t] < freeze_to[a]

    def legs(src: int, dst: int, amount: int, d, ts, etype: str, desc: str, tid: int) -> list[dict]:
        return [
            {"account_id": acct.at[src, "account_id"], "posting_date": d, "recorded_at": ts, "amount": -amount,
             "entry_type": etype, "x_transfer": tid, "description": desc},
            {"account_id": acct.at[dst, "account_id"], "posting_date": d, "recorded_at": ts, "amount": amount,
             "entry_type": etype, "x_transfer": tid, "description": desc},
        ]

    # 1. planned movements from the documents
    moves = docs.moves.copy()
    moves["x_pkey"] = moves["pkey"]
    doc_rows = _frame(moves.to_dict("records"))

    # 2a. pre-funding the business day before payroll, tax and one-off payments
    prefund = []
    for m in moves[moves["x_prefund"].astype(bool)].itertuples():
        a = a_idx[m.account_id]
        h = headers.get(ccy[a])
        if h is None or h == a:
            continue
        d = cal.add_business_days(np.datetime64(m.posting_date, "D"), -1)
        t = int(np.searchsorted(days, d))
        if d < start or not active(a, t) or not active(h, t):
            d, t = np.datetime64(m.posting_date, "D"), int(np.searchsorted(days, np.datetime64(m.posting_date, "D")))
        prefund += legs(h, a, int(-m.amount), d, stamp(d, 7 * HOUR if d == np.datetime64(m.posting_date, "D") else 18 * HOUR),
                        "POOL_FUNDING", f"Pre-funding for {m.entry_type.replace('_', ' ').lower()}", next(transfer))

    # 2b. monthly bank fees
    fees = []
    for d in cal.last_business_days_of_months(start, end):
        t = int(np.searchsorted(days, d))
        for a in range(n_acct):
            if active(a, t):
                fee = max(int(major_to_minor([rng.uniform(15, 120) / FX_START[ccy[a]]], ccy[a])[0]), 1)
                fees.append({"account_id": acct.at[a, "account_id"], "posting_date": d, "recorded_at": stamp(d, 22 * HOUR),
                             "amount": -fee, "entry_type": "BANK_FEE", "description": "Monthly account maintenance fee"})

    # 3. schedule of balance-dependent postings (decided now, amounts computed in the loop)
    sweepable = [a for a in range(n_acct) if acct_type[a] in ("OPERATING", "COLLECTION", "PAYROLL")
                 and a not in headers.values() and ccy[a] in headers and not np.isnan(target[a])]
    fridays = [t for t in range(n_days) if pd.Timestamp(days[t]).weekday() == 4]
    sweeps = {t: [a for a in sweepable if active(a, t) and active(headers[ccy[a]], t) and not frozen(a, t)] for t in fridays}
    month_first = [int(np.searchsorted(days, d)) for d in cal.first_business_days_of_months(start, end)][1:]
    fx_events = {t: [h for c, h in sorted(headers.items()) if c != cfg.reporting_currency and active(h, t) and active(usd_header, t)]
                 for t in month_first}
    month_last = [int(np.searchsorted(days, d)) for d in cal.last_business_days_of_months(start, end)]
    deposits = [a for a in range(n_acct) if acct_type[a] == "DEPOSIT"]
    interest_events = {t: [a for a in deposits if active(a, t)] for t in month_last}
    closures: dict[int, list[int]] = {}
    for a in range(n_acct):
        if close_t[a] <= n_days - 1:
            closures.setdefault(int(close_t[a]), []).append(a)
    scheduled = (2 * sum(len(v) for v in sweeps.values()) + 2 * sum(len(v) for v in fx_events.values())
                 + sum(len(v) for v in interest_events.values()) + 2 * sum(len(v) for v in closures.values()))

    # 4. operating flows fill the remaining volume. Whether a scheduled pooling posting moves any
    # money depends on balances (an idle account needs no sweep), so the filler count is found by a
    # short fixed-point iteration: simulate, count the pooling postings, adjust the filler, repeat.
    structural = _concat([doc_rows, _frame(prefund), _frame(fees)])
    opening = acct["opening_balance"].to_numpy(dtype=np.int64)
    month_last_set = set(month_last)

    def run_pool(base: pd.DataFrame) -> list[dict]:
        """The day-by-day pooling routine over the balance-independent postings in ``base``."""
        a_arr = base["account_id"].map(a_idx).to_numpy()
        t_arr = np.searchsorted(days, base["posting_date"].to_numpy(dtype="datetime64[D]"))
        if (days[t_arr] != base["posting_date"].to_numpy(dtype="datetime64[D]")).any():
            raise AssertionError("planned posting on a non-business day")
        matrix = np.zeros((n_acct, n_days), dtype=np.int64)
        np.add.at(matrix, (a_arr, t_arr), base["amount"].to_numpy(dtype=np.int64))
        tids = iter(range(10**6, 10**9))
        balance = np.zeros(n_acct, dtype=np.int64)
        month_sum = np.zeros(n_acct)
        month_cnt = np.zeros(n_acct)
        loop: list[dict] = []
        for t in range(n_days):
            d = days[t]
            balance[open_t == t] += opening[open_t == t]
            balance += matrix[:, t]
            for a in closures.get(t, []):
                h, amt = headers[ccy[a]], int(balance[a])
                if amt:
                    loop += legs(a, h, amt, d, stamp(d, 17 * HOUR + 1800), "ACCOUNT_CLOSURE",
                                 "Closing balance swept to pool header", next(tids))
                    balance[a] -= amt
                    balance[h] += amt
            for a in sweeps.get(t, []):
                h, delta = headers[ccy[a]], int(balance[a] - target[a])
                if delta:
                    desc = "Cash pool sweep to header" if delta > 0 else "Cash pool top-up from header"
                    loop += legs(a, h, delta, d, stamp(d, 18 * HOUR + 1800), "POOL_SWEEP", desc, next(tids))
                    balance[a] -= delta
                    balance[h] += delta
            for h in fx_events.get(t, []):
                c, delta = ccy[h], int(balance[h] - target[h])
                if delta:
                    rid, rate = rates.on_or_before(c, d)
                    usd = int(to_usd([abs(delta)], c, [rate])[0]) * (1 if delta > 0 else -1)
                    tid, ts = next(tids), stamp(d, 19 * HOUR)
                    desc = f"Pool rebalancing: {c} {'sold for' if delta > 0 else 'bought with'} USD"
                    loop.append({"account_id": acct.at[h, "account_id"], "posting_date": d, "recorded_at": ts, "amount": -delta,
                                 "entry_type": "FX_CONVERSION", "x_transfer": tid, "fx_rate_id": rid,
                                 "original_currency": cfg.reporting_currency, "original_amount": -usd, "description": desc})
                    loop.append({"account_id": acct.at[usd_header, "account_id"], "posting_date": d, "recorded_at": ts,
                                 "amount": usd, "entry_type": "FX_CONVERSION", "x_transfer": tid, "fx_rate_id": rid,
                                 "original_currency": c, "original_amount": delta, "description": desc})
                    balance[h] -= delta
                    balance[usd_header] += usd
            live = (open_t <= t) & (t < close_t)
            month_sum[live] += balance[live]
            month_cnt[live] += 1
            for a in interest_events.get(t, []):
                month_days = pd.Timestamp(d).days_in_month
                interest = int(np.rint(month_sum[a] / max(month_cnt[a], 1) * DEPOSIT_RATES[ccy[a]] * month_days / 365))
                if interest > 0:
                    loop.append({"account_id": acct.at[a, "account_id"], "posting_date": d, "recorded_at": stamp(d, 21 * HOUR),
                                 "amount": interest, "entry_type": "INTEREST", "description": "Monthly deposit interest"})
                    balance[a] += interest
            if t in month_last_set:
                month_sum[:] = 0
                month_cnt[:] = 0
        return loop

    total_target = cfg.volumes["ledger_entries"]
    expected_loop, best = scheduled, None
    for _ in range(8):
        n_fill = total_target - len(structural) - expected_loop
        if n_fill < 0.3 * total_target:
            raise ValueError(f"ledger_entries too small: structural postings leave only {n_fill} operating flows")
        filler = _operating_flows(cfg, entities, acct, days, open_t, close_t, n_fill, stream(cfg.seed, "ledger_filler"))
        base = _concat([structural, filler])
        loop = run_pool(base)
        total = len(base) + len(loop)
        if total <= total_target and (best is None or total > best[0]):
            best = (total, base, loop)
        if total == total_target:
            break
        expected_loop = len(loop)
    if best is None:
        raise AssertionError("could not reach the ledger volume target")
    _, base, loop = best

    # 5. residual after the iteration (normally zero): transaction charges on the last day
    missing = total_target - len(base) - len(loop)
    last = days[-1]
    fillers = [a for a in range(n_acct) if active(a, n_days - 1) and acct_type[a] != "RESTRICTED"]
    for k in range(missing):
        a = fillers[k % len(fillers)]
        loop.append({"account_id": acct.at[a, "account_id"], "posting_date": last, "recorded_at": stamp(last, 23 * HOUR + 1800),
                     "amount": -max(int(major_to_minor([1.0], ccy[a])[0]), 1), "entry_type": "BANK_FEE",
                     "description": "Transaction charge"})

    ledger = _finalise_ledger(cfg, acct, _concat([base, _frame(loop)]))
    if len(ledger) != cfg.volumes["ledger_entries"]:
        raise AssertionError(f"ledger has {len(ledger)} entries, expected {cfg.volumes['ledger_entries']}")

    pkey_to_id = dict(zip(ledger["x_pkey"].dropna().astype(int), ledger.loc[ledger["x_pkey"].notna(), "ledger_entry_id"]))
    allocations = _finalise_allocations(cfg, docs.allocations, pkey_to_id)
    ar_events = _finalise_events(cfg, docs.receivable_events, "receivable_id", "ARE", 7, pkey_to_id)
    ap_events = _finalise_events(cfg, docs.payable_events, "payable_id", "APE", 7, pkey_to_id)
    revisions = _finalise_revisions(cfg, _concat([docs.revisions, _run_rate_reestimates(cfg, docs.cf_items, ledger, entities)]),
                                    docs.cf_items)
    return LedgerResult(ledger, allocations, ar_events, ap_events, revisions)


def _operating_flows(cfg, entities, acct, days, open_t, close_t, n_fill, rng) -> pd.DataFrame:
    """High-frequency small receipts and payments with weekday, month-end and seasonal patterns."""
    eff_t = {e: int(np.searchsorted(days, cal.roll_forward(np.datetime64(f, "D")))) for e, f in
             zip(entities["entity_id"], entities["effective_from"])}
    weights = [s * (len(days) - eff_t[e]) for e, s in zip(entities["entity_id"], entities["x_scale_usd"])]
    counts = allocate(n_fill, weights)
    ts = pd.to_datetime(days)
    month_rank = pd.Series(ts).groupby(ts.to_period("M")).rank(ascending=False).to_numpy()
    months = ts.month.to_numpy()
    base_w = WEEKDAY_FACTOR[ts.weekday.to_numpy()] * np.where(month_rank <= 3, 1.3, 1.0) * (1 + 0.1 * np.sin(2 * np.pi * (months - 1) / 12))
    frames = []
    for e, n in zip(entities.itertuples(), counts):
        if n == 0:
            continue
        func = e.functional_currency
        g = acct[(acct["entity_id"] == e.entity_id) & (acct["currency"] == func)]
        ops = g[g["account_type"] == "OPERATING"].sort_values("x_seq")
        op = (ops if len(ops) else g[g["account_type"] == "CONCENTRATION"])["account_id"].iloc[0]
        coll = g[g["account_type"] == "COLLECTION"].sort_values("x_seq")
        t0 = eff_t[e.entity_id]
        w = base_w[t0:] / base_w[t0:].sum()
        weeks = (len(days) - t0) / 5
        n_in = int(round(0.55 * n))
        n_out = n - n_in
        weekly = e.x_scale_usd * 12 / 52 / FX_START[func]
        rows = []
        for direction, k, budget in (("IN", n_in, weekly * INFLOW_MULTIPLIER * INFLOW_MIX["operating"] * weeks),
                                     ("OUT", n_out, weekly * OUTFLOW_MIX["operating"] * weeks)):
            if k == 0:
                continue
            t = np.sort(t0 + rng.choice(len(days) - t0, size=k, p=w))
            mean = budget / k
            amt = np.maximum(major_to_minor(rng.lognormal(np.log(mean) - 0.405, 0.9, size=k), func), 1)
            accounts = np.full(k, op, dtype=object)
            if direction == "IN" and len(coll):
                ci = acct.index[acct["account_id"] == coll["account_id"].iloc[0]][0]
                use = (open_t[ci] <= t) & (t < close_t[ci])
                accounts[use] = coll["account_id"].iloc[0]
            secs = rng.integers(int(8.5 * HOUR), 18 * HOUR, size=k)
            rows.append(pd.DataFrame({
                "account_id": accounts, "posting_date": days[t], "recorded_at": stamp(days[t], secs),
                "amount": amt if direction == "IN" else -amt,
                "entry_type": "OPERATING_RECEIPT" if direction == "IN" else "OPERATING_PAYMENT",
                "description": "Card and small customer receipts" if direction == "IN" else "Small supplier and expense payments",
            }))
        frames.append(pd.concat(rows, ignore_index=True))
    return _frame(pd.concat(frames, ignore_index=True).to_dict("records"))


def _finalise_ledger(cfg: Config, acct: pd.DataFrame, led: pd.DataFrame) -> pd.DataFrame:
    led = led.copy()
    led["x_order"] = np.arange(len(led))
    led["posting_date"] = pd.to_datetime(led["posting_date"].to_numpy(dtype="datetime64[D]"))
    led["recorded_at"] = pd.to_datetime(led["recorded_at"].to_numpy(dtype="datetime64[s]"))
    led = led.sort_values(["posting_date", "recorded_at", "account_id", "x_order"], kind="mergesort").reset_index(drop=True)
    years = led["posting_date"].dt.year.unique()
    if list(years) != [cfg.cycle_year]:
        raise AssertionError(f"ledger postings outside {cfg.cycle_year}: {years}")
    led["ledger_entry_id"] = ids.sequence("LED", cfg.cycle_year, 8, len(led))
    info = acct.set_index("account_id")
    led["entity_id"] = led["account_id"].map(info["entity_id"])
    led["currency"] = led["account_id"].map(info["currency"])
    first = led.dropna(subset=["x_transfer"]).drop_duplicates("x_transfer")["x_transfer"]
    tmap = dict(zip(first, ids.sequence("TRF", cfg.cycle_year, 6, len(first))))
    led["transfer_group_id"] = led["x_transfer"].map(tmap)
    return led


def _finalise_allocations(cfg: Config, allocs: pd.DataFrame, pkey_to_id: dict) -> pd.DataFrame:
    al = allocs.copy()
    al["ledger_entry_id"] = al["pkey"].map(pkey_to_id)
    al["allocation_date"] = pd.to_datetime(al["allocation_date"].to_numpy(dtype="datetime64[D]"))
    al["x_doc"] = al["receivable_id"].fillna(al["payable_id"])
    al = al.sort_values(["allocation_date", "ledger_entry_id", "x_doc"], kind="mergesort").reset_index(drop=True)
    al["settlement_id"] = ids.sequence("SETL", cfg.cycle_year, 7, len(al))
    return al


def _finalise_events(cfg: Config, ev: pd.DataFrame, key: str, prefix: str, width: int, pkey_to_id: dict) -> pd.DataFrame:
    ev = ev.copy()
    ev["ledger_entry_id"] = ev["pkey"].map(lambda p: None if pd.isna(p) else pkey_to_id[int(p)])
    ev["event_ts"] = pd.to_datetime(ev["event_ts"].to_numpy(dtype="datetime64[s]"))
    ev["x_order"] = np.arange(len(ev))
    ev = ev.sort_values(["event_ts", key, "x_order"], kind="mergesort").reset_index(drop=True)
    ev["event_id"] = ids.sequence(prefix, cfg.cycle_year, width, len(ev))
    return ev


def _run_rate_reestimates(cfg: Config, cf: pd.DataFrame, ledger: pd.DataFrame, entities: pd.DataFrame) -> pd.DataFrame:
    """Each month the run-rate model re-estimates the next 13 weeks from the last 28 days of actuals."""
    ops = ledger[ledger["entry_type"].isin(["OPERATING_RECEIPT", "OPERATING_PAYMENT"])]
    rr = cf[cf["flow_category"] == "OPERATING_RUN_RATE"].copy()
    rr["x_current"] = rr["amount"]
    eff = dict(zip(entities["entity_id"], entities["effective_from"]))
    func = dict(zip(entities["entity_id"], entities["functional_currency"]))
    rows = []
    starts = cal.first_business_days_of_months(cfg.start_date, cfg.actuals_end)[1:]
    for d in starts:
        d_ts = pd.Timestamp(d)
        window = ops[(ops["posting_date"] >= d_ts - pd.Timedelta(days=28)) & (ops["posting_date"] < d_ts)]
        sums = window.groupby(["entity_id", "entry_type"])["amount"].sum()
        due = rr[(rr["expected_date"] >= d_ts) & (rr["expected_date"] <= d_ts + pd.Timedelta(days=90))]
        for i, item in due.iterrows():
            if eff[item.entity_id] > d_ts - pd.Timedelta(days=28):
                continue
            etype = "OPERATING_RECEIPT" if item.direction == "INFLOW" else "OPERATING_PAYMENT"
            weekly_major = abs(sums.get((item.entity_id, etype), 0)) / 4 / 10 ** (0 if func[item.entity_id] == "JPY" else 2)
            new = int(major_to_minor([round_to(weekly_major, 100.0)[()]], func[item.entity_id])[0])
            if new and new != rr.at[i, "x_current"]:
                rr.at[i, "x_current"] = new
                rows.append({"cf_id": item.cf_id, "recorded_at": stamp(d, 5 * HOUR), "revision_type": "AMOUNT_CHANGE",
                             "reason": "RUN_RATE_REESTIMATE", "actor_id": SYSTEM_USER, "new_expected_date": None,
                             "new_amount": new, "currency": item.currency})
    return pd.DataFrame(rows)


def _finalise_revisions(cfg: Config, rev: pd.DataFrame, cf: pd.DataFrame) -> pd.DataFrame:
    rev = rev.copy()
    rev["recorded_at"] = pd.to_datetime(rev["recorded_at"].to_numpy(dtype="datetime64[s]"))
    rev["new_expected_date"] = pd.to_datetime(pd.Series(rev["new_expected_date"]).map(lambda v: None if v is None or pd.isna(v) else pd.Timestamp(v)))
    order = {"DATE_CHANGE": 0, "AMOUNT_CHANGE": 1, "SETTLED": 2, "CANCELLED": 3}
    rev["x_kind"] = rev["revision_type"].map(order)
    rev = rev.sort_values(["cf_id", "recorded_at", "x_kind"], kind="mergesort").reset_index(drop=True)
    rev["revision_no"] = rev.groupby("cf_id").cumcount() + 1
    rev = rev.sort_values(["recorded_at", "cf_id", "revision_no"], kind="mergesort").reset_index(drop=True)
    rev["revision_id"] = ids.sequence("CFR", cfg.cycle_year, 7, len(rev))
    rev["currency"] = rev["cf_id"].map(cf.set_index("cf_id")["currency"])
    return rev


# --------------------------------------------------------------------- statements

def build_statements(cfg: Config, accounts: pd.DataFrame, ledger: pd.DataFrame, adjustments: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily bank statements per account. ``adjustments`` holds bank-side differences
    (account_id, statement_date, credit_delta, debit_delta, count_delta) used to inject
    labelled reconciliation breaks."""
    end = day(cfg.actuals_end)
    grids = []
    for a in accounts.itertuples():
        obd = np.datetime64(a.opening_balance_date, "D")
        last = min(np.datetime64(a.closed_on, "D"), end) if pd.notna(a.closed_on) else end
        stmt_days = cal.business_days(obd, last)
        initial = None
        if np.datetime64(a.opened_on, "D") < obd:  # the account existed: the bank's statement of the previous day
            initial = cal.add_business_days(obd, -1)
            stmt_days = np.concatenate([[initial], stmt_days])
        grids.append(pd.DataFrame({"account_id": a.account_id, "statement_date": pd.to_datetime(stmt_days), "currency": a.currency,
                                   "x_opening": a.opening_balance, "x_obd": pd.Timestamp(obd),
                                   "x_initial": stmt_days == initial if initial is not None else False}))
    grid = pd.concat(grids, ignore_index=True)
    led = ledger.assign(credit=ledger["amount"].clip(lower=0), debit=(-ledger["amount"]).clip(lower=0), n=1)
    mov = led.groupby(["account_id", "posting_date"])[["credit", "debit", "n"]].sum().reset_index()
    mov = mov.rename(columns={"posting_date": "statement_date"})
    if adjustments is not None and len(adjustments):
        adj = adjustments.rename(columns={"credit_delta": "credit", "debit_delta": "debit", "count_delta": "n"})
        mov = pd.concat([mov, adj[["account_id", "statement_date", "credit", "debit", "n"]]]).groupby(
            ["account_id", "statement_date"])[["credit", "debit", "n"]].sum().reset_index()
    st = grid.merge(mov, on=["account_id", "statement_date"], how="left").fillna({"credit": 0, "debit": 0, "n": 0})
    st = st.sort_values(["account_id", "statement_date"]).reset_index(drop=True)
    st["x_move"] = (st["credit"] - st["debit"]).astype(np.int64)
    st["closing_balance"] = st["x_opening"].astype(np.int64) + st.groupby("account_id")["x_move"].cumsum()
    st["opening_balance"] = st["closing_balance"] - st["x_move"]
    st["total_credits"] = st["credit"].astype(np.int64)
    st["total_debits"] = st["debit"].astype(np.int64)
    st["transaction_count"] = st["n"].astype(np.int64)
    next_bd = cal.add_business_days(st["statement_date"].to_numpy(dtype="datetime64[D]"), 1)
    st["recorded_at"] = pd.to_datetime(stamp(next_bd, 6 * HOUR))
    # The opening statement is loaded with the migration, at 20:00 on the eve of the opening date.
    initial = st["x_initial"].astype(bool).to_numpy()
    initial_ts = stamp(st["x_obd"].to_numpy(dtype="datetime64[D]") - DAY, 20 * HOUR)
    st.loc[initial, "recorded_at"] = pd.to_datetime(initial_ts[initial])
    st = st.sort_values(["statement_date", "account_id"], kind="mergesort").reset_index(drop=True)
    st["statement_id"] = ids.sequence("STM", cfg.cycle_year, 7, len(st))
    return st
