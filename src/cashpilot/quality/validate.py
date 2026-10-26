"""Validation suite (Step 8 of the brief).

Checks, grouped by category:
  STRUCTURE   primary keys, required fields, allowed values, ID patterns, minimums (from the dictionary)
  INTEGRITY   foreign keys, uniqueness and join consistency (e.g. ledger entity = account entity)
  DATES       date ordering and active periods
  ARITHMETIC  reconciliations: statements, positions, allocations, transfers, forecasts, variance
  LIFECYCLE   state machines of every event table; derived status equals the last event
  DUPLICATES  exact duplicate rows
  ANOMALY     the five edge-case rules (expected to fire only on labelled records)
  VOLUME      row counts against the profile

Each violation is matched against the ground truth when one is supplied: a check is PASS when
it finds nothing, EXPECTED when everything it finds is a labelled anomaly, FAIL otherwise.
The ground truth is used only here, after detection, to classify results.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from cashpilot.core import calendar as cal
from cashpilot.core.config import Config
from cashpilot.core.money import to_usd
from cashpilot.dataset import Dataset
from cashpilot.engine.fx import FxBook
from cashpilot.quality.detectors import lookahead_runs, missing_fx_rates, reconciliation_breaks
from cashpilot.quality.rules import duplicate_pairs, mixed_currency
from cashpilot.schema import load_schema

LABEL_COLUMNS = ("issue_type", "is_anomaly", "anomaly", "label", "ground_truth", "injected")


@dataclass
class Check:
    check_id: str
    category: str
    target: str
    description: str
    rows_checked: int
    violations: int
    expected: int = 0
    status: str = "PASS"
    sample: list = field(default_factory=list)


class Report:
    def __init__(self, gt: pd.DataFrame | None):
        self.checks: list[Check] = []
        self.gt = gt

    def add(self, check_id, category, target, description, rows, bad_keys, issue_type: str | None = None) -> None:
        keys = sorted({str(k) for k in bad_keys})
        expected = 0
        if issue_type and self.gt is not None:
            labelled = set(self.gt.loc[(self.gt["label"] == "ANOMALY") & (self.gt["issue_type"] == issue_type), "record_id"])
            expected = len([k for k in keys if k in labelled])
        n = len(keys)
        status = "PASS" if n == 0 else ("EXPECTED" if expected == n and issue_type else "FAIL")
        unexpected = [k for k in keys if not (issue_type and self.gt is not None and k in set(
            self.gt.loc[self.gt["issue_type"] == issue_type, "record_id"]))]
        self.checks.append(Check(check_id, category, target, description, int(rows), n, expected, status, (unexpected or keys)[:5]))

    @property
    def ok(self) -> bool:
        return all(c.status != "FAIL" for c in self.checks)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(c) for c in self.checks])


def _keys(df: pd.DataFrame, mask, pk) -> list:
    sub = df.loc[np.asarray(mask, dtype=bool), list(pk)]
    return ["|".join(map(str, r)) for r in sub.itertuples(index=False, name=None)]


# ------------------------------------------------------------------- structure

def _structure(ds: Dataset, rep: Report) -> None:
    schema = load_schema()
    for name, df in ds.tables.items():
        t = schema.table(name)
        pk = list(t.primary_key)
        rep.add(f"S-PK-{name}", "STRUCTURE", name, "primary key unique and not null", len(df),
                _keys(df, df.duplicated(pk, keep=False) | df[pk].isna().any(axis=1), pk))
        bad_req, bad_enum, bad_pat, bad_min = [], [], [], []
        for c in t.columns:
            s = df[c.name]
            if c.required:
                bad_req += _keys(df, s.isna(), pk)
            if c.allowed:
                bad_enum += _keys(df, s.notna() & ~s.isin(c.allowed), pk)
            if c.pattern:
                bad_pat += _keys(df, s.notna() & ~s.astype(str).str.match(c.pattern), pk)
            if c.minimum is not None and c.type in ("int", "money", "rate"):
                bad_min += _keys(df, s.notna() & (s < c.minimum), pk)
        rep.add(f"S-REQ-{name}", "STRUCTURE", name, "required fields present", len(df), bad_req)
        rep.add(f"S-ENUM-{name}", "STRUCTURE", name, "values within allowed sets", len(df), bad_enum)
        rep.add(f"S-PAT-{name}", "STRUCTURE", name, "IDs match their documented patterns", len(df), bad_pat)
        rep.add(f"S-MIN-{name}", "STRUCTURE", name, "numeric minimums respected", len(df), bad_min)


# ------------------------------------------------------------------- integrity

def _integrity(ds: Dataset, rep: Report) -> None:
    schema = load_schema()
    for name, df in ds.tables.items():
        t = schema.table(name)
        pk = list(t.primary_key)
        bad_fk = []
        for c in t.columns:
            if c.fk and c.fk_table in ds:
                parent = set(ds[c.fk_table][c.fk_column])
                bad_fk += _keys(df, df[c.name].notna() & ~df[c.name].isin(parent), pk)
        rep.add(f"I-FK-{name}", "INTEGRITY", name, "every foreign key resolves", len(df), bad_fk)
        bad_u = []
        for c in t.columns:
            if c.unique and t.primary_key != (c.name,):
                bad_u += _keys(df, df[c.name].notna() & df[c.name].duplicated(keep=False), pk)
        for group in t.unique_together:
            bad_u += _keys(df, df.duplicated(list(group), keep=False), pk)
        rep.add(f"I-UNQ-{name}", "INTEGRITY", name, "unique columns and natural keys", len(df), bad_u)

    acc = ds["bank_account"].set_index("account_id")
    led = ds["ledger_entry"]
    rep.add("I-JOIN-ledger-account", "INTEGRITY", "ledger_entry", "ledger entity and currency equal the account's", len(led),
            led.loc[(led["entity_id"] != led["account_id"].map(acc["entity_id"])) | (led["currency"] != led["account_id"].map(acc["currency"])), "ledger_entry_id"])
    rep.add("I-EMBED-account", "INTEGRITY", "bank_account", "account ID embeds its entity ID", len(acc),
            acc.index[acc.index.str.slice(8, 18) != acc["entity_id"]])
    for name, id_col in (("receivable", "receivable_id"), ("payable", "payable_id"), ("cash_flow_forecast", "cf_id")):
        df = ds[name]
        rep.add(f"I-JOIN-{name}-account", "INTEGRITY", name, "document account belongs to the document entity", len(df),
                df.loc[df["entity_id"] != df["account_id"].map(acc["entity_id"]), id_col])
    led_year = led["ledger_entry_id"].str.slice(4, 8).astype(int) != led["posting_date"].dt.year
    rep.add("I-EMBED-ledger-year", "INTEGRITY", "ledger_entry", "LED ID year equals the posting year", len(led), led.loc[led_year, "ledger_entry_id"])
    fx = ds["currency_rate"]
    expected_ids = "FXR-" + fx["rate_date"].dt.strftime("%Y-%m-%d") + "-" + fx["base_currency"] + "-" + fx["quote_currency"]
    rep.add("I-EMBED-rate", "INTEGRITY", "currency_rate", "rate ID embeds date and currencies", len(fx), fx.loc[fx["rate_id"] != expected_ids, "rate_id"])
    users = ds["app_user"]
    bad = users[(users["role"] == "ACCOUNT_HOLDER") != users["entity_id"].notna()]
    rep.add("I-JOIN-user-entity", "INTEGRITY", "app_user", "only account holders carry an entity", len(users), bad["user_id"])
    st = ds["bank_statement"]
    rep.add("I-JOIN-statement-currency", "INTEGRITY", "bank_statement", "statement currency equals account currency", len(st),
            st.loc[st["currency"] != st["account_id"].map(acc["currency"]), "statement_id"])
    al = ds["settlement_allocation"]
    one_doc = al["receivable_id"].notna() ^ al["payable_id"].notna()
    doc_ccy = al["receivable_id"].map(ds["receivable"].set_index("receivable_id")["currency"]).fillna(
        al["payable_id"].map(ds["payable"].set_index("payable_id")["currency"]))
    post = al["ledger_entry_id"].map(led.set_index("ledger_entry_id")["posting_date"])
    rep.add("I-JOIN-allocation", "INTEGRITY", "settlement_allocation", "one document per allocation, in its currency, on the posting date",
            len(al), al.loc[~one_doc | (al["currency"] != doc_ccy) | (al["allocation_date"] != post), "settlement_id"])
    rev = ds["cf_revision"]
    rep.add("I-JOIN-revision-currency", "INTEGRITY", "cf_revision", "revision currency equals the item currency", len(rev),
            rev.loc[rev["currency"] != rev["cf_id"].map(ds["cash_flow_forecast"].set_index("cf_id")["currency"]), "revision_id"])
    if "forecast_run" in ds:
        runs = ds["forecast_run"]
        embed = "FCAST-" + runs["cutoff_date"].dt.strftime("%Y-%m-%d") + "-" + runs["version"].map(lambda v: f"{int(v):03d}")
        rep.add("I-EMBED-run", "INTEGRITY", "forecast_run", "run ID embeds cutoff date and version", len(runs), runs.loc[runs["run_id"] != embed, "run_id"])


# ----------------------------------------------------------------------- dates

def _dates(ds: Dataset, rep: Report) -> None:
    r, p = ds["receivable"], ds["payable"]
    rep.add("D-AR-due", "DATES", "receivable", "invoice date on or before due date", len(r), r.loc[r["invoice_date"] > r["due_date"], "receivable_id"])
    rep.add("D-AP-due", "DATES", "payable", "bill date on or before due date", len(p), p.loc[p["bill_date"] > p["due_date"], "payable_id"])
    led, acc = ds["ledger_entry"], ds["bank_account"].set_index("account_id")
    opened = led["account_id"].map(acc["opening_balance_date"])
    closed = led["account_id"].map(acc["closed_on"])
    outside = (led["posting_date"] < opened) | (closed.notna() & (led["posting_date"] > closed))
    rep.add("D-LED-active", "DATES", "ledger_entry", "postings inside the account's active period", len(led), led.loc[outside, "ledger_entry_id"])
    rep.add("D-LED-busday", "DATES", "ledger_entry", "postings on business days", len(led),
            led.loc[~cal.is_business_day(led["posting_date"]), "ledger_entry_id"])
    cf, rev = ds["cash_flow_forecast"], ds["cf_revision"]
    early = rev["recorded_at"] < rev["cf_id"].map(cf.set_index("cf_id")["recorded_at"])
    rs = rev.sort_values(["cf_id", "revision_no"])
    not_monotonic = rs.groupby("cf_id")["recorded_at"].diff() < pd.Timedelta(0)
    gaps = rs.groupby("cf_id")["revision_no"].diff().fillna(rs["revision_no"]) != 1
    rep.add("D-CFR-order", "DATES", "cf_revision", "revisions after the item, in order, numbered consecutively", len(rev),
            list(rev.loc[early, "revision_id"]) + list(rs.loc[not_monotonic | gaps, "revision_id"]))
    st = ds["bank_statement"]
    rep.add("D-STM-recorded", "DATES", "bank_statement", "statements received after the day they cover", len(st),
            st.loc[st["recorded_at"] < st["statement_date"], "statement_id"])
    for table, key, created_table, created_col in (("receivable_event", "receivable_id", "receivable", "recorded_at"),
                                                   ("payable_event", "payable_id", "payable", "recorded_at")):
        ev = ds[table]
        created = ev[key].map(ds[created_table].set_index(key)[created_col])
        rep.add(f"D-{table}", "DATES", table, "events not before the document was recorded", len(ev), ev.loc[ev["event_ts"] < created, "event_id"])
    if "forecast_run" in ds:
        runs = ds["forecast_run"]
        bad = (runs["horizon_start"] != runs["cutoff_date"]) | (
            runs["horizon_end"] != runs["cutoff_date"] + pd.to_timedelta(runs["horizon_days"] - 1, unit="D")) | (runs["created_at"] < runs["cutoff_date"])
        rep.add("D-RUN-horizon", "DATES", "forecast_run", "horizon starts at the cutoff, spans horizon_days, created on/after cutoff", len(runs),
                runs.loc[bad, "run_id"])


# ------------------------------------------------------------------ arithmetic

def _arithmetic(ds: Dataset, cfg: Config, fx: FxBook, rep: Report) -> None:
    st = ds["bank_statement"]
    rep.add("A-STM-rollforward", "ARITHMETIC", "bank_statement", "closing = opening + credits - debits", len(st),
            st.loc[st["closing_balance"] != st["opening_balance"] + st["total_credits"] - st["total_debits"], "statement_id"])
    s = st.sort_values(["account_id", "statement_date"])
    prev = s.groupby("account_id")["closing_balance"].shift()
    first = s.groupby("account_id").head(1)
    acc = ds["bank_account"].set_index("account_id")
    rep.add("A-STM-continuity", "ARITHMETIC", "bank_statement", "opening = previous closing; first opening = account opening balance", len(st),
            list(s.loc[prev.notna() & (s["opening_balance"] != prev), "statement_id"]) +
            list(first.loc[first["opening_balance"] != first["account_id"].map(acc["opening_balance"]), "statement_id"]))
    led = ds["ledger_entry"]
    al = ds["settlement_allocation"]
    same = al[al["currency"] == al["ledger_entry_id"].map(led.set_index("ledger_entry_id")["currency"])]
    alloc_sum = same.groupby("ledger_entry_id")["allocated_amount"].sum()
    led_amt = led.set_index("ledger_entry_id")["amount"].abs().reindex(alloc_sum.index)
    rep.add("A-ALLOC-ledger", "ARITHMETIC", "settlement_allocation", "allocations add up to their cash posting", len(alloc_sum),
            alloc_sum.index[alloc_sum != led_amt])
    rec = ds["receivable"].set_index("receivable_id")
    paid = al.dropna(subset=["receivable_id"]).groupby("receivable_id")["allocated_amount"].sum().reindex(rec.index, fill_value=0)
    bad = (paid > rec["amount"]) | ((rec["status_at_end"] == "PAID") & (paid != rec["amount"]))
    rep.add("A-AR-settled", "ARITHMETIC", "receivable", "settled amount never exceeds the invoice; PAID means fully settled", len(rec), rec.index[bad])
    trf = led.dropna(subset=["transfer_group_id"])
    plain = trf[trf["entry_type"] != "FX_CONVERSION"].groupby("transfer_group_id")["amount"].sum()
    conv = trf[trf["entry_type"] == "FX_CONVERSION"]
    conv_bad = []
    if len(conv):
        rate = conv["fx_rate_id"].map(ds["currency_rate"].set_index("rate_id")["rate"])
        for g, legs in conv.assign(rate=rate).groupby("transfer_group_id"):
            usd_leg = legs[legs["currency"] == cfg.reporting_currency]
            other = legs[legs["currency"] != cfg.reporting_currency]
            if len(usd_leg) != 1 or len(other) != 1:
                conv_bad.append(g)
                continue
            o = other.iloc[0]
            if int(to_usd([-o.amount], o.currency, [o.rate])[0]) != int(usd_leg.iloc[0].amount):
                conv_bad.append(g)
    rep.add("A-TRF-net", "ARITHMETIC", "ledger_entry", "transfers net to zero; FX legs agree at the recorded rate", trf["transfer_group_id"].nunique(),
            list(plain.index[plain != 0]) + conv_bad)
    if "daily_cash_position" in ds:
        d = ds["daily_cash_position"].sort_values(["account_id", "position_date"])
        prev = d.groupby("account_id")["closing_balance"].shift()
        bad = (d["closing_balance"] != d["opening_balance"] + d["inflows"] - d["outflows"]) | (prev.notna() & (d["opening_balance"] != prev))
        rep.add("A-POS-rollforward", "ARITHMETIC", "daily_cash_position", "daily balances roll forward from the ledger", len(d),
                _keys(d, bad, ["account_id", "position_date"]))
        ent = ds["entity_cash_position"]
        summed = d.groupby(["entity_id", "position_date"])["closing_balance_usd"].sum()
        e = ent.set_index(["entity_id", "position_date"])
        bad = (e["total_usd"] != summed.reindex(e.index)) | (e["available_usd"] + e["restricted_usd"] != e["total_usd"])
        rep.add("A-POS-consolidation", "ARITHMETIC", "entity_cash_position", "entity totals equal the sum of their accounts in USD", len(ent),
                ["|".join(map(str, k)) for k in e.index[bad]])
    if "forecast_position" in ds:
        fp = ds["forecast_position"]
        bad = fp["closing_available_usd"] != fp["opening_available_usd"] + fp["inflows_usd"] - fp["outflows_usd"]
        rep.add("A-FCST-rollforward", "ARITHMETIC", "forecast_position", "projected balances roll forward", len(fp),
                _keys(fp, bad, ["run_id", "scenario_id", "entity_id", "position_date"]))
        eff = ds["scenario_assumption_effect"]
        g = fp.groupby(["run_id", "scenario_id"])
        net = g["inflows_usd"].sum() - g["outflows_usd"].sum()
        mins = fp.groupby(["run_id", "scenario_id", "position_date"])["closing_available_usd"].sum().groupby(level=[0, 1]).min()
        base = {r: s for r, s in net.index if s.startswith("SCN-BASE")}
        bad = []
        for (run, sid), e in eff.groupby(["run_id", "scenario_id"]):
            b = base[run]
            if e["delta_net_flow_usd"].sum() != net[(run, sid)] - net[(run, b)] or \
                    e["delta_min_available_usd"].sum() != mins[(run, sid)] - mins[(run, b)]:
                bad.append(f"{run}|{sid}")
        rep.add("A-SCN-attribution", "ARITHMETIC", "scenario_assumption_effect", "assumption effects add up to the scenario's difference from base",
                eff.groupby(["run_id", "scenario_id"]).ngroups, bad)
    if "forecast_vs_actual" in ds and len(ds["forecast_vs_actual"]):
        fva = ds["forecast_vs_actual"]
        drivers = [c for c in fva.columns if c.endswith("_usd") and c not in ("forecast_net_usd", "actual_net_usd", "variance_usd", "residual_usd")]
        bad = (fva["residual_usd"] != 0) | (fva["variance_usd"] != fva["actual_net_usd"] - fva["forecast_net_usd"]) | (
            fva[drivers].sum(axis=1) != fva["variance_usd"])
        rep.add("A-VAR-explained", "ARITHMETIC", "forecast_vs_actual", "variance fully explained by drivers (residual 0)", len(fva),
                _keys(fva, bad, ["run_id", "scenario_id", "entity_id", "week_no"]))
        va = ds["variance_attribution"]
        col_of = {"TIMING": "timing_usd", "AMOUNT": "amount_usd", "FX": "fx_usd", "NEW_AFTER_CUTOFF": "new_after_cutoff_usd",
                  "UNFORECASTED": "unforecasted_usd", "NOT_REALIZED": "not_realized_usd", "RUN_RATE": "run_rate_usd", "DATA_QUALITY": "data_quality_usd"}
        drill = va.groupby(["run_id", "scenario_id", "entity_id", "week_no", "driver"])["amount_usd"].sum().unstack(fill_value=0)
        f = fva.set_index(["run_id", "scenario_id", "entity_id", "week_no"]).loc[drill.index]
        bad = [("|".join(map(str, k))) for k in drill.index if any(drill.at[k, d] != f.at[k, col_of[d]] for d in drill.columns)]
        rep.add("A-VAR-drilldown", "ARITHMETIC", "variance_attribution", "item-level attribution adds up to each driver", len(drill), bad)


# ------------------------------------------------------------------- lifecycle

def _lifecycles(ds: Dataset, rep: Report) -> None:
    for lc in load_schema().lifecycles.values():
        if lc.event_table not in ds or lc.entity not in ds:
            continue
        ev = ds[lc.event_table]
        order = [lc.key, lc.order_column] if lc.order_column else [lc.key, "event_ts", "event_id"]
        ev = ev.sort_values(order, kind="mergesort")
        trans = {(e, s): t for e, s, t in lc.transitions}
        has_from = "from_status" in ev.columns
        bad, final = [], {}
        id_col = ev.columns[0]
        for key, g in ev.groupby(lc.key, sort=False):
            state = lc.initial
            for row in g.itertuples(index=False):
                event = getattr(row, lc.event_column)
                nxt = trans.get((event, state))
                frm = getattr(row, "from_status") if has_from else state
                frm = None if frm is None or (isinstance(frm, float) and np.isnan(frm)) else frm
                if nxt is None or (has_from and (frm != state or getattr(row, "to_status") != nxt)):
                    bad.append(getattr(row, id_col))
                    break
                state = nxt
            final[key] = state
        rep.add(f"L-{lc.entity}", "LIFECYCLE", lc.event_table, f"{lc.entity} events follow the state machine", len(ev), bad)
        if lc.status_column:
            ent = ds[lc.entity]
            pk = load_schema().table(lc.entity).primary_key[0]
            derived = ent[pk].map(final)
            rep.add(f"L-{lc.entity}-status", "LIFECYCLE", lc.entity, "status_at_end equals the last event", len(ent),
                    ent.loc[derived != ent[lc.status_column], pk])


# ------------------------------------------------------------- dups & anomalies

def _duplicates(ds: Dataset, rep: Report) -> None:
    schema = load_schema()
    for name, df in ds.tables.items():
        pk = list(schema.table(name).primary_key)
        cols = [c for c in df.columns if c not in pk and not c.endswith("_id") or c in ("entity_id", "account_id")]
        if name in ("forecast_position", "daily_cash_position", "entity_cash_position", "forecast_vs_actual", "variance_attribution",
                    "forecast_run_item", "forecast_run_balance_input", "forecast_run_fx_input", "forecast_run_scenario",
                    "scenario_assumption_link", "scenario_assumption_effect", "audit_event", "exception_event", "currency"):
            continue
        dup = df.duplicated([c for c in df.columns if c not in pk], keep=False)
        rep.add(f"U-ROW-{name}", "DUPLICATES", name, "no exact duplicate rows (ignoring the ID)", len(df), _keys(df, dup, pk))


def _anomalies(ds: Dataset, cfg: Config, fx: FxBook, rep: Report) -> None:
    br = reconciliation_breaks(ds, cfg, fx)
    rep.add("R-RECON-001", "ANOMALY", "bank_statement", "bank movement equals the booked ledger movement (opening + ledger = closing)",
            len(ds["bank_statement"]), br["record_id"], "BALANCE_BREAK")
    fxm = missing_fx_rates(ds, cfg)
    rep.add("R-FX-001", "ANOMALY", "currency_rate", "a fixing exists for every business day", len(ds["currency_rate"]), fxm["record_id"], "FX_RATE_MISSING")
    cf = ds["cash_flow_forecast"]
    dups = duplicate_pairs(cf, cfg.policy["duplicate_date_tolerance_days"])
    rep.add("R-DUP", "ANOMALY", "cash_flow_forecast", "no cash flow forecast twice", len(cf), dups["cf_id"], "DUPLICATE_CASH_FLOW")
    mixed = mixed_currency(cf, ds["bank_account"], ds["receivable"], ds["payable"])
    rep.add("R-CUR", "ANOMALY", "cash_flow_forecast", "no currency mixed without conversion", len(cf), mixed["cf_id"], "MIXED_CURRENCY")
    if "forecast_run" in ds:
        leaks = lookahead_runs(ds)
        rep.add("R-LEAK-001", "ANOMALY", "forecast_run", "runs only use records known before their cutoff", len(ds["forecast_run"]),
                leaks["record_id"], "LOOKAHEAD_LEAKAGE")


def _volumes(ds: Dataset, cfg: Config, rep: Report) -> None:
    v = cfg.volumes
    targets = {"legal_entity": v["legal_entities"], "bank_account": v["bank_accounts"], "ledger_entry": v["ledger_entries"]}
    if "forecast_run" in ds:  # forecast items are complete once the labelled duplicates are in
        targets["cash_flow_forecast"] = v["forecast_items"]
    for name, n in targets.items():
        rep.add(f"V-{name}", "VOLUME", name, f"exactly {n:,} rows", len(ds[name]), [] if len(ds[name]) == n else [f"{len(ds[name])} rows"])
    used = set(ds["bank_account"]["currency"])
    rep.add("V-currencies", "VOLUME", "bank_account", f"{len(cfg.currencies)} currencies in use", len(used),
            [] if used == set(cfg.currencies) else sorted(set(cfg.currencies) - used))
    leaked = [f"{n}.{c}" for n, df in ds.tables.items() for c in df.columns if c in LABEL_COLUMNS]
    rep.add("G-no-labels", "VOLUME", "dataset", "no ground-truth label columns inside the dataset", len(ds.tables), leaked)


def validate(ds: Dataset, cfg: Config, fx: FxBook, ground_truth: pd.DataFrame | None = None) -> Report:
    rep = Report(ground_truth)
    _structure(ds, rep)
    _integrity(ds, rep)
    _dates(ds, rep)
    _arithmetic(ds, cfg, fx, rep)
    _lifecycles(ds, rep)
    _duplicates(ds, rep)
    _anomalies(ds, cfg, fx, rep)
    _volumes(ds, cfg, rep)
    return rep


# ------------------------------------------------------------------- rendering

def summary_dict(rep: Report, baseline: Report | None = None) -> dict:
    df = rep.frame()
    out = {
        "overall": "PASS" if rep.ok else "FAIL",
        "checks": int(len(df)),
        "by_status": {k: int(v) for k, v in df["status"].value_counts().sort_index().items()},
        "by_category": {cat: {k: int(v) for k, v in g["status"].value_counts().sort_index().items()} for cat, g in df.groupby("category")},
        "results": df.to_dict("records"),
    }
    if baseline is not None:
        b = baseline.frame()
        out["baseline"] = {"overall": "PASS" if (b["violations"] == 0).all() else "FAIL", "checks": int(len(b)),
                           "violations": int(b["violations"].sum())}
    return out


def render_markdown(rep: Report, profile: str, baseline: Report | None = None) -> str:
    df = rep.frame()
    lines = [f"# Validation summary — `{profile}` dataset", ""]
    lines.append(f"**Overall: {'PASS' if rep.ok else 'FAIL'}** — {len(df)} checks; a check is PASS when it finds nothing, "
                 "EXPECTED when everything it finds is a labelled anomaly from the ground truth, FAIL otherwise.")
    lines.append("")
    if baseline is not None:
        b = baseline.frame()
        lines.append(f"**Clean baseline (before anomaly injection): {len(b)} checks, {int(b['violations'].sum())} violations.** "
                     "The generator produces valid data; every finding below comes from a labelled injection.")
        lines.append("")
    lines.append("| Category | PASS | EXPECTED | FAIL |")
    lines.append("|---|---|---|---|")
    for cat, g in df.groupby("category", sort=False):
        c = g["status"].value_counts()
        lines.append(f"| {cat} | {c.get('PASS', 0)} | {c.get('EXPECTED', 0)} | {c.get('FAIL', 0)} |")
    lines.append("")
    lines.append("## Checks that found something")
    lines.append("")
    hits = df[df["violations"] > 0]
    if hits.empty:
        lines.append("None.")
    else:
        lines.append("| Check | Description | Rows | Found | Labelled | Status | Sample |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in hits.itertuples():
            lines.append(f"| `{r.check_id}` | {r.description} | {r.rows_checked:,} | {r.violations} | {r.expected} | {r.status} | "
                         f"{', '.join(map(str, r.sample[:3]))} |")
    lines.append("")
    lines.append("## All checks")
    lines.append("")
    lines.append("| Check | Category | Target | Description | Rows | Status |")
    lines.append("|---|---|---|---|---|---|")
    for r in df.itertuples():
        lines.append(f"| `{r.check_id}` | {r.category} | {r.target} | {r.description} | {r.rows_checked:,} | {r.status} |")
    return "\n".join(lines) + "\n"


def write_summary(rep: Report, path_md, path_json, profile: str, baseline: Report | None = None) -> None:
    from pathlib import Path
    Path(path_md).write_text(render_markdown(rep, profile, baseline), encoding="utf-8", newline="\n")
    Path(path_json).write_text(json.dumps(summary_dict(rep, baseline), indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
