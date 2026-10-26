"""Labelled edge cases, injected after the valid baseline has been generated and validated.

Injection rules (documented in docs/RULES.md):
  INJ-REC-01  bank-only charge: the bank debits a fee the ledger never booked
  INJ-REC-02  payment rejected by the bank: a booked payment never leaves the account
  INJ-FX-01   short gap: 1-3 consecutive business-day FX fixings deleted
  INJ-FX-02   long gap: 5 consecutive business-day fixings deleted
  INJ-DUP-01  account holder re-keys a subledger item with the same invoice/bill reference
  INJ-DUP-02  ... with their own reference and a date within the 3-day tolerance
  INJ-DUP-03  ... with their own reference and a date 5-6 days off (deliberately hard)
  INJ-CUR-01  converted item reverted to the invoice currency (currency differs from account)
  INJ-CUR-02  converted item given the invoice's foreign amount without conversion
  INJ-LEAK-01 a legacy weekly run re-generated a week late from the latest data
Each touches only the targeted records. Ground truth also lists legitimate look-alikes
(NEGATIVE_CONTROL / NO_ISSUE) so false positives can be measured.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashpilot.core import calendar as cal
from cashpilot.core import ids
from cashpilot.core.config import Config
from cashpilot.core.money import MINOR_UNITS, format_minor, major_to_minor, to_usd
from cashpilot.core.rng import stream
from cashpilot.dataset import Dataset, conform
from cashpilot.generate.common import FX_START
from cashpilot.generate.ledger import build_statements
from cashpilot.schema import load_schema

DAY = pd.Timedelta(days=1)


class Labels:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, label, issue, sub_type, table, record_id, rule, related=None, field=None, original=None,
            injected=None, expected_rule=None, decision=None, notes=None):
        self.rows.append({"label": label, "issue_type": issue, "sub_type": sub_type, "record_table": table,
                          "record_id": record_id, "related_record_id": related, "field": field,
                          "original_value": None if original is None else str(original),
                          "injected_value": None if injected is None else str(injected), "injection_rule": rule,
                          "expected_rule_id": expected_rule, "expected_decision": decision, "notes": notes})

    def frame(self) -> pd.DataFrame:
        gt = pd.DataFrame(self.rows).sort_values(["label", "issue_type", "record_id"], kind="mergesort").reset_index(drop=True)
        gt.insert(0, "gt_id", [ids.simple("GT", i + 1, 6) for i in range(len(gt))])
        return conform(gt, load_schema().table("anomaly_label"))


def weekly_cutoffs(cfg: Config) -> list[pd.Timestamp]:
    first = pd.Timestamp(cfg.forecast["first_cutoff"])
    last = pd.Timestamp(cfg.actuals_end) - 6 * DAY
    return list(pd.date_range(first, last, freq=f"{int(cfg.forecast['frequency_days'])}D"))


def inject(cfg: Config, ds: Dataset) -> tuple[Dataset, pd.DataFrame, list, list]:
    out = Dataset({k: v.copy() for k, v in ds.tables.items()})
    labels = Labels()
    a = cfg.anomalies
    _fx_gaps(cfg, out, labels, stream(cfg.seed, "inject_fx"), a["fx_missing_short_gaps"], a["fx_missing_long_gaps"])
    _duplicates(cfg, out, labels, stream(cfg.seed, "inject_dup"), a["duplicate_cash_flows"])
    _mixed_currency(cfg, out, labels, stream(cfg.seed, "inject_cur"), a["mixed_currency"])
    _balance_breaks(cfg, out, labels, stream(cfg.seed, "inject_rec"), a["balance_breaks"])
    leaky, benign = _choose_runs(cfg, labels, stream(cfg.seed, "inject_leak"), a["lookahead_runs"], cfg.forecast["benign_reruns"])
    _negative_controls(cfg, out, labels, stream(cfg.seed, "inject_neg"), a["negative_controls"], leaky)
    return out, labels.frame(), leaky, benign


# ------------------------------------------------------------------ FX gaps

def _fx_gaps(cfg, ds, labels, rng, n_short, n_long):
    fx = ds["currency_rate"]
    referenced = set(ds["cash_flow_forecast"]["fx_rate_id"].dropna()) | set(ds["ledger_entry"]["fx_rate_id"].dropna())
    tol = cfg.policy["fx_staleness_business_days"]
    window = cal.business_days(pd.Timestamp(cfg.start_date) + 14 * DAY, pd.Timestamp(cfg.actuals_end) - 15 * DAY)
    taken: dict[str, list[int]] = {}
    removed = []
    plan = [("SHORT_GAP", "INJ-FX-01", int(rng.integers(1, tol + 1))) for _ in range(n_short)] + \
           [("LONG_GAP", "INJ-FX-02", tol + 2) for _ in range(n_long)]
    for sub, rule, length in plan:
        for _ in range(500):
            ccy = cfg.foreign_currencies[int(rng.integers(len(cfg.foreign_currencies)))]
            start = int(rng.integers(0, len(window) - length))
            gap_days = window[start:start + length]
            rids = [ids.rate_id(d, ccy) for d in gap_days]
            near = any(abs(start - s) < 10 for s in taken.get(ccy, []))
            if not near and not (set(rids) & referenced):
                taken.setdefault(ccy, []).append(start)
                break
        else:
            raise RuntimeError("could not place an FX gap")
        for k, rid in enumerate(rids, start=1):
            rate = fx.loc[fx["rate_id"] == rid, "rate"].iloc[0]
            removed.append(rid)
            labels.add("ANOMALY", "FX_RATE_MISSING", sub, "currency_rate", rid, rule, field="row",
                       original=f"{rate:.8f}", injected="(deleted)", expected_rule="R-FX-001",
                       decision="USE_PREVIOUS_RATE" if k <= tol else "BLOCK_CONVERSION",
                       notes=f"day {k} of a {length}-business-day gap in {ccy}")
    ds["currency_rate"] = fx[~fx["rate_id"].isin(removed)].reset_index(drop=True)


# --------------------------------------------------------------- duplicates

def _duplicates(cfg, ds, labels, rng, n):
    cf = ds["cash_flow_forecast"]
    users = ds["app_user"]
    holder = dict(zip(users.loc[users["role"] == "ACCOUNT_HOLDER", "entity_id"], users.loc[users["role"] == "ACCOUNT_HOLDER", "user_id"]))
    end = pd.Timestamp(cfg.actuals_end)
    cand = cf[cf["source_system"].isin(["AR_SUBLEDGER", "AP_SUBLEDGER"]) & cf["original_currency"].isna()
              & (cf["expected_date"] >= pd.Timestamp(cfg.start_date) + 31 * DAY)
              & (cf["recorded_at"] <= end - 25 * DAY)]
    cand = cand[cand["amount"] >= cand.groupby("currency")["amount"].transform("median")]
    ar = cand[cand["source_system"] == "AR_SUBLEDGER"]
    ap = cand[cand["source_system"] == "AP_SUBLEDGER"]
    n_ar = int(round(n * 0.7))
    picks = pd.concat([ar.iloc[np.sort(rng.choice(len(ar), size=n_ar, replace=False))],
                       ap.iloc[np.sort(rng.choice(len(ap), size=n - n_ar, replace=False))]])
    next_n = int(cf["cf_id"].str[-6:].astype(int).max()) + 1
    rows = []
    tol = cfg.policy["duplicate_date_tolerance_days"]
    for k, (_, o) in enumerate(picks.sort_values("cf_id").iterrows()):
        u = rng.random()
        if u < 0.55:
            sub, rule, exp_rule, jitter, ref = "EXACT_REFERENCE", "INJ-DUP-01", "R-DUP-001", int(rng.integers(0, 3)), o.source_reference
        elif u < 0.90:
            sub, rule, exp_rule, jitter, ref = "FUZZY_MATCH", "INJ-DUP-02", "R-DUP-002", int(rng.integers(-tol, tol + 1)), None
        else:
            sub, rule, exp_rule, jitter, ref = "FUZZY_BEYOND_TOLERANCE", "INJ-DUP-03", "R-DUP-002", int(rng.choice([-6, -5, 5, 6])), None
        expected = o.expected_date + jitter * DAY
        recorded = min(o.recorded_at + int(rng.integers(1, 21)) * DAY + pd.Timedelta(hours=int(rng.integers(1, 8))),
                       end - DAY + pd.Timedelta(hours=10))
        new_id = f"CF-{cfg.cycle_year}-{next_n + k:06d}"
        rows.append({**o.to_dict(), "cf_id": new_id, "source_system": "MANUAL", "receivable_id": None, "payable_id": None,
                     "source_reference": ref or f"MAN-{o.entity_id[4:]}-D{k + 1:03d}", "expected_date": expected,
                     "recorded_at": recorded, "created_by": holder[o.entity_id]})
        labels.add("ANOMALY", "DUPLICATE_CASH_FLOW", sub, "cash_flow_forecast", new_id, rule, related=o.cf_id, field="row",
                   injected=f"manual copy, date {'+' if jitter >= 0 else ''}{jitter}d", expected_rule=exp_rule,
                   decision="EXCLUDE_DUPLICATE",
                   notes="beyond the 3-day matching tolerance: expected to be missed" if sub == "FUZZY_BEYOND_TOLERANCE" else None)
    new = pd.DataFrame(rows).astype({c: cf[c].dtype for c in cf.columns if c in rows[0]})
    ds["cash_flow_forecast"] = conform(pd.concat([cf, new], ignore_index=True), load_schema().table("cash_flow_forecast"))


# ----------------------------------------------------------- mixed currency

def _mixed_currency(cfg, ds, labels, rng, n):
    cf = ds["cash_flow_forecast"]
    cand = cf[cf["original_currency"].notna() & (cf["expected_date"] >= pd.Timestamp(cfg.start_date) + 31 * DAY)]
    if len(cand) < n:
        raise RuntimeError(f"only {len(cand)} converted items available for {n} mixed-currency injections")
    chosen = cand.iloc[np.sort(rng.choice(len(cand), size=n, replace=False))]
    for k, (i, o) in enumerate(chosen.iterrows()):
        before = f"{o.currency} {format_minor([o.amount], o.currency)[0]} (converted from {o.original_currency} {format_minor([o.original_amount], o.original_currency)[0]})"
        if k % 2 == 0:
            cf.loc[i, ["currency", "amount"]] = [o.original_currency, o.original_amount]
            rev = ds["cf_revision"]  # the item's own revisions follow its (now wrong) currency
            rev.loc[rev["cf_id"] == o.cf_id, "currency"] = o.original_currency
            sub, rule, exp_rule = "ITEM_CURRENCY_MISMATCH", "INJ-CUR-01", "R-CUR-001"
            after = f"{o.original_currency} {format_minor([o.original_amount], o.original_currency)[0]} on a {o.currency} account"
        else:
            major = o.original_amount / 10 ** MINOR_UNITS[o.original_currency]
            cf.loc[i, "amount"] = int(major_to_minor([major], o.currency)[0])
            sub, rule, exp_rule = "UNCONVERTED_AMOUNT", "INJ-CUR-02", "R-CUR-002"
            after = f"{o.currency} {format_minor([cf.loc[i, 'amount']], o.currency)[0]} (foreign figure, no conversion)"
        cf.loc[i, ["original_currency", "original_amount", "fx_rate_id"]] = [None, None, None]
        labels.add("ANOMALY", "MIXED_CURRENCY", sub, "cash_flow_forecast", o.cf_id, rule, related=o.receivable_id,
                   field="currency/amount", original=before, injected=after, expected_rule=exp_rule, decision="CONVERT_AT_CUTOFF_RATE")
    ds["cash_flow_forecast"] = cf


# ------------------------------------------------------------ balance breaks

def _balance_breaks(cfg, ds, labels, rng, n):
    st, led, acc = ds["bank_statement"], ds["ledger_entry"], ds["bank_account"]
    lo, hi = pd.Timestamp(cfg.start_date) + 9 * DAY, pd.Timestamp(cfg.actuals_end) - 5 * DAY
    eligible = st[(st["statement_date"] >= lo) & (st["statement_date"] <= hi) & (st["transaction_count"] > 0)]
    payments = led[led["entry_type"].isin(["AP_PAYMENT", "OPERATING_PAYMENT"])]
    pay_index = payments.groupby(["account_id", "posting_date"]).groups
    materiality = cfg.policy["recon_materiality_usd"]
    adjustments, chosen, notes = [], set(), {}
    while len(adjustments) < n:
        row = eligible.iloc[int(rng.integers(len(eligible)))]
        key = (row.account_id, row.statement_date)
        if key in chosen or any(a == row.account_id and abs((d - row.statement_date).days) < 7 for a, d in chosen):
            continue
        ccy = row.currency
        if rng.random() < 0.6:
            usd = float(rng.uniform(5, 500)) if rng.random() < 0.7 else float(rng.uniform(1500, 50000))
            fee = max(int(major_to_minor([usd / FX_START[ccy]], ccy)[0]), 1)
            adjustments.append({"account_id": row.account_id, "statement_date": row.statement_date, "credit_delta": 0,
                                "debit_delta": fee, "count_delta": 1})
            notes[key] = ("BANK_ONLY_CHARGE", "INJ-REC-01", None, -fee)
        else:
            hits = pay_index.get(key)
            if hits is None:
                continue
            entry = payments.loc[hits[int(rng.integers(len(hits)))]]
            amt = int(-entry.amount)
            adjustments.append({"account_id": row.account_id, "statement_date": row.statement_date, "credit_delta": 0,
                                "debit_delta": -amt, "count_delta": -1})
            notes[key] = ("PAYMENT_REJECTED_BY_BANK", "INJ-REC-02", entry.ledger_entry_id, amt)
        chosen.add(key)
    adj = pd.DataFrame(adjustments)
    new_st = build_statements(cfg, acc, led, adj)
    new_st = conform(new_st, load_schema().table("bank_statement"))
    old = st.set_index(["account_id", "statement_date"])
    new = new_st.set_index(["account_id", "statement_date"])
    assert (old["statement_id"] == new.loc[old.index, "statement_id"]).all(), "statement IDs must not move"
    for (acct, d), (sub, rule, related, diff) in sorted(notes.items()):
        s_old, s_new = old.loc[(acct, d)], new.loc[(acct, d)]
        usd = abs(int(to_usd([diff], s_old.currency, [FX_START[s_old.currency]])[0])) / 100
        labels.add("ANOMALY", "BALANCE_BREAK", sub, "bank_statement", s_old.statement_id, rule, related=related,
                   field="closing_balance", original=format_minor([s_old.closing_balance], s_old.currency)[0],
                   injected=format_minor([s_new.closing_balance], s_old.currency)[0], expected_rule="R-RECON-001",
                   decision="RAISE_RECON_BREAK", notes=f"expected severity {'HIGH' if usd >= materiality else 'LOW'}")
    ds["bank_statement"] = new_st


# --------------------------------------------------------- look-ahead runs

def _choose_runs(cfg, labels, rng, n_leaky, n_benign):
    cutoffs = weekly_cutoffs(cfg)
    pool = [c for c in cutoffs if pd.Timestamp(cfg.start_date) + 30 * DAY <= c <= pd.Timestamp(cfg.actuals_end) - 30 * DAY]
    leaky: list[pd.Timestamp] = []
    while len(leaky) < n_leaky:
        c = pool[int(rng.integers(len(pool)))]
        if all(abs((c - x).days) >= 21 for x in leaky):
            leaky.append(c)
    rest = [c for c in pool if all(abs((c - x).days) >= 14 for x in leaky)]
    benign = sorted(pd.Timestamp(c) for c in rng.choice(rest, size=n_benign, replace=False))
    for c in sorted(leaky):
        labels.add("ANOMALY", "LOOKAHEAD_LEAKAGE", "LATEST_SNAPSHOT_USED", "forecast_run", ids.run_id(c, 1), "INJ-LEAK-01",
                   field="input snapshot", original="records before the knowledge cutoff",
                   injected="records up to 7 days after the cutoff", expected_rule="R-LEAK-001", decision="SUPERSEDE_WITH_RERUN",
                   notes="re-generated a week late by the legacy job")
    return sorted(leaky), benign


# ------------------------------------------------------- negative controls

def _negative_controls(cfg, ds, labels, rng, n, leaky):
    """Legitimate records that look like anomalies; none of them should be flagged."""
    per = max(n // 5, 1)
    cf = ds["cash_flow_forecast"]
    converted = cf[cf["original_currency"].notna()]
    for _, r in converted.iloc[np.sort(rng.choice(len(converted), size=min(per, len(converted)), replace=False))].iterrows():
        labels.add("NEGATIVE_CONTROL", "NO_ISSUE", "LEGIT_CONVERTED_ITEM", "cash_flow_forecast", r.cf_id, "NEG-CUR",
                   notes="cross-currency item with a recorded conversion")
    manual = cf[(cf["source_system"] == "MANUAL") & (cf["flow_category"] == "OTHER")]
    for _, r in manual.iloc[np.sort(rng.choice(len(manual), size=min(per, len(manual)), replace=False))].iterrows():
        labels.add("NEGATIVE_CONTROL", "NO_ISSUE", "LEGIT_MANUAL_ITEM", "cash_flow_forecast", r.cf_id, "NEG-DUP",
                   notes="genuine manual forecast item")
    weekends = [d for d in pd.date_range(cfg.start_date, cfg.actuals_end) if not cal.is_business_day(d)]
    for d in [weekends[int(i)] for i in np.sort(rng.choice(len(weekends), size=per, replace=False))]:
        ccy = cfg.foreign_currencies[int(rng.integers(len(cfg.foreign_currencies)))]
        labels.add("NEGATIVE_CONTROL", "NO_ISSUE", "NON_BUSINESS_DAY", "currency_rate", ids.rate_id(d, ccy), "NEG-FX",
                   notes="no fixing is expected on weekends and holidays")
    st = ds["bank_statement"]
    busiest = st.assign(move=(st["total_credits"] + st["total_debits"])).sort_values(["move", "statement_id"], ascending=[False, True])
    flagged = {r["record_id"] for r in labels.rows if r["issue_type"] == "BALANCE_BREAK"}
    for _, r in busiest[~busiest["statement_id"].isin(flagged)].head(per).iterrows():
        labels.add("NEGATIVE_CONTROL", "NO_ISSUE", "LARGE_LEGIT_MOVEMENT", "bank_statement", r.statement_id, "NEG-REC",
                   notes="unusually large but fully booked movement")
    for c in sorted(leaky):
        nxt = c + 7 * DAY
        labels.add("NEGATIVE_CONTROL", "NO_ISSUE", "NORMAL_RUN_AFTER_LEAK", "forecast_run", ids.run_id(nxt, 1), "NEG-LEAK",
                   notes="ordinary weekly run next to a leaky one")
