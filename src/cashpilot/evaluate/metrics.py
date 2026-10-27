"""Measurable outputs.

* Detection quality: precision / recall / F1 per edge case and sub-type, decision accuracy,
  false positives on negative controls. Ground truth is joined here, after detection.
* Forecast accuracy: WAPE and bias of weekly net external cash flow by horizon bucket,
  for the approved forecast versions; the look-ahead signature of leaky runs.
* Variance drivers: share of absolute variance explained by each driver.
* Liquidity outlook: the live run per scenario (lowest group cash, breaches, funding gap).
* Reconciliation and data profile (distributions that show realistic variation).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashpilot.core.config import Config
from cashpilot.dataset import Dataset
from cashpilot.generate.common import FX_VOL

BUCKETS = [("week 1", 1, 1), ("weeks 2-4", 2, 4), ("weeks 5-13", 5, 13)]
DRIVER_COLUMNS = ["timing_usd", "amount_usd", "fx_usd", "new_after_cutoff_usd", "unforecasted_usd", "not_realized_usd",
                  "run_rate_usd", "data_quality_usd"]


def _ratio(a: float, b: float) -> float:
    return round(float(a) / float(b), 4) if b else 0.0


def detection_quality(ds: Dataset, gt: pd.DataFrame) -> dict:
    exc = ds["exception"]
    found = exc[exc["category"] == "DATA_QUALITY"][["exception_type", "record_id", "decision"]].rename(columns={"exception_type": "issue_type"})
    truth = gt[gt["label"] == "ANOMALY"][["issue_type", "sub_type", "record_id", "expected_decision"]]
    controls = set(gt.loc[gt["label"] == "NEGATIVE_CONTROL", "record_id"])
    rows, subtypes = [], []
    for issue in sorted(set(truth["issue_type"]) | set(found["issue_type"])):
        t = truth[truth["issue_type"] == issue]
        f = found[found["issue_type"] == issue]
        hit = t.merge(f, on=["issue_type", "record_id"])
        tp, fp, fn = len(hit), len(f) - len(hit), len(t) - len(hit)
        p, r = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
        rows.append({"issue_type": issue, "labelled": len(t), "detected": len(f), "tp": tp, "fp": fp, "fn": fn,
                     "precision": p, "recall": r, "f1": _ratio(2 * p * r, p + r),
                     "decision_accuracy": _ratio((hit["decision"] == hit["expected_decision"]).sum(), tp)})
        for sub, g in t.groupby("sub_type"):
            got = g["record_id"].isin(f["record_id"]).sum()
            subtypes.append({"issue_type": issue, "sub_type": sub, "labelled": len(g), "detected": int(got), "recall": _ratio(got, len(g))})
    flagged_controls = sorted(controls & set(found["record_id"]))
    return {"by_issue": rows, "by_sub_type": subtypes, "negative_controls": len(controls),
            "negative_controls_flagged": len(flagged_controls), "flagged_control_ids": flagged_controls}


def _wape(fva: pd.DataFrame) -> dict:
    out = {}
    for name, lo, hi in BUCKETS:
        b = fva[(fva["week_no"] >= lo) & (fva["week_no"] <= hi)]
        actual = b["actual_net_usd"].abs().sum()
        out[name] = {"wape": _ratio(b["variance_usd"].abs().sum(), actual), "bias": _ratio(b["variance_usd"].sum(), actual),
                     "entity_weeks": int(len(b))}
    return out


def forecast_accuracy(ds: Dataset, gt: pd.DataFrame | None) -> dict:
    fva = ds["forecast_vs_actual"]
    runs = ds["forecast_run"].set_index("run_id")
    if fva.empty:
        return {}
    fva = fva.join(runs[["process", "run_purpose", "status_at_end"]], on="run_id")
    base = fva[fva["scenario_id"].str.startswith("SCN-BASE")]
    approved = base[base["status_at_end"] == "APPROVED"]
    result = {"approved_versions": {"runs": int(approved["run_id"].nunique()), "by_horizon": _wape(approved)}}
    by_scenario = {}
    for sid, g in fva[fva["status_at_end"] == "APPROVED"].groupby(fva["scenario_id"].str.split("-").str[1]):
        by_scenario[sid] = _wape(g)
    result["approved_versions_by_scenario"] = by_scenario
    if gt is not None:
        leaky = set(gt.loc[gt["issue_type"] == "LOOKAHEAD_LEAKAGE", "record_id"])
        fixes = set(runs.index[runs["supersedes_run_id"].isin(leaky)])
        others = base[~base["run_id"].isin(leaky | fixes) & (base["status_at_end"] == "APPROVED")]
        result["lookahead_signature"] = {
            "leaky_runs_week1_wape": _wape(base[base["run_id"].isin(leaky)])["week 1"]["wape"],
            "their_as_of_reruns_week1_wape": _wape(base[base["run_id"].isin(fixes)])["week 1"]["wape"],
            "other_runs_week1_wape": _wape(others)["week 1"]["wape"],
            "note": "A forecast that has seen the future is suspiciously accurate in its first week.",
        }
    return result


def balance_accuracy(ds: Dataset) -> dict:
    """Group available cash at each forecast week-end vs the actual group available cash.

    Comparable like for like at group level: internal pooling nets out, restricted cash is
    excluded on both sides and only entities in the run's scope are counted.
    """
    runs = ds["forecast_run"]
    runs = runs[runs["status_at_end"] == "APPROVED"]
    fp = ds["forecast_position"]
    fp = fp[fp["run_id"].isin(runs["run_id"]) & fp["scenario_id"].str.startswith("SCN-BASE")]
    ecp = ds["entity_cash_position"]
    end = ecp["position_date"].max()
    incomplete = {(e, d) for e, d in ecp.loc[ecp["fx_status"] == "INCOMPLETE", ["entity_id", "position_date"]].itertuples(index=False, name=None)}
    rows = []
    for run in runs.itertuples():
        f = fp[fp["run_id"] == run.run_id]
        entities = set(f["entity_id"])
        for w in range(1, int(run.horizon_days) // 7 + 1):
            d = run.cutoff_date + pd.Timedelta(days=7 * w - 1)
            if d > end:
                break
            # An actual that could not be fully converted to USD understates cash: never compare against it.
            skipped = any((e, d) in incomplete for e in entities)
            fc = f.loc[f["position_date"] == d, "closing_available_usd"].sum()
            ac = ecp.loc[(ecp["position_date"] == d) & ecp["entity_id"].isin(entities), "available_usd"].sum()
            rows.append({"week_no": w, "forecast": fc, "actual": ac, "skipped": skipped})
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    out = {}
    for name, lo, hi in BUCKETS:
        week = df[(df["week_no"] >= lo) & (df["week_no"] <= hi)]
        b = week[~week["skipped"]]
        err = (b["forecast"] - b["actual"]) / b["actual"].abs()
        out[name] = {"mape": round(float(err.abs().mean()), 4) if len(b) else None,
                     "bias": round(float(err.mean()), 4) if len(b) else None,
                     "observations": int(len(b)), "excluded_incomplete_fx": int(week["skipped"].sum())}
    return out


def variance_drivers(ds: Dataset) -> dict:
    fva = ds["forecast_vs_actual"]
    if fva.empty:
        return {}
    runs = ds["forecast_run"].set_index("run_id")
    base = fva[fva["scenario_id"].str.startswith("SCN-BASE") & fva["run_id"].map(runs["status_at_end"]).eq("APPROVED")]
    absolute = base[DRIVER_COLUMNS].abs().sum()
    total = absolute.sum()
    return {"share_of_absolute_variance": {c.replace("_usd", ""): _ratio(v, total) for c, v in absolute.items()},
            "net_by_driver_usd": {c.replace("_usd", ""): round(int(v) / 100, 2) for c, v in base[DRIVER_COLUMNS].sum().items()},
            "residual_usd": int(base["residual_usd"].abs().sum()), "rows": int(len(base))}


def liquidity_outlook(ds: Dataset, run_id: str | None = None) -> dict:
    """Per-scenario liquidity summary of one run (default: the latest LIVE run)."""
    runs = ds["forecast_run"]
    if run_id is None:
        live = runs[runs["run_purpose"] == "LIVE"]
        if live.empty:
            return {}
        run_id = live["run_id"].iloc[-1]
    chosen = runs[runs["run_id"] == run_id]
    if chosen.empty:
        return {}
    live = chosen
    pos = ds["forecast_position"]
    pos = pos[pos["run_id"] == run_id]
    names = ds["legal_entity"].set_index("entity_id")["entity_name"]
    out = {"run_id": run_id, "cutoff": str(live["cutoff_date"].iloc[-1].date()), "scenarios": {}}
    for sid, g in pos.groupby("scenario_id"):
        group = g.groupby("position_date")[["closing_available_usd", "restricted_usd", "min_buffer_usd"]].sum()
        low_day = group["closing_available_usd"].idxmin()
        breaches = g[g["breach_flag"].astype(bool)]
        per_entity = []
        for ent, e in breaches.groupby("entity_id"):
            per_entity.append({"entity_id": ent, "entity_name": names[ent], "first_breach": str(e["position_date"].min().date()),
                               "days_below_buffer": int(len(e)),
                               "max_shortfall_usd": round(int((e["min_buffer_usd"] - e["closing_available_usd"]).max()) / 100, 2)})
        out["scenarios"][sid] = {
            "opening_available_usd": round(int(group["closing_available_usd"].iloc[0]) / 100, 2),
            "lowest_available_usd": round(int(group["closing_available_usd"].min()) / 100, 2),
            "lowest_on": str(low_day.date()),
            "closing_available_usd": round(int(group["closing_available_usd"].iloc[-1]) / 100, 2),
            "restricted_usd": round(int(group["restricted_usd"].iloc[0]) / 100, 2),
            "entities_breaching": len(per_entity),
            "funding_gap_usd": round(sum(e["max_shortfall_usd"] for e in per_entity), 2),
            "breaches": sorted(per_entity, key=lambda e: -e["max_shortfall_usd"]),
        }
    return out


def reconciliation_stats(ds: Dataset) -> dict:
    st = ds["bank_statement"]
    exc = ds["exception"]
    breaks = exc[exc["exception_type"] == "BALANCE_BREAK"]
    daily = ds["daily_cash_position"]
    open_diff = daily[daily["bank_minus_book"].fillna(0) != 0]
    return {"statements": int(len(st)), "statement_days_reconciled": _ratio(len(st) - len(breaks), len(st)),
            "breaks": int(len(breaks)), "breaks_high": int((breaks["severity"] == "HIGH").sum()),
            "account_days_with_open_difference": int(len(open_diff)), "accounts_affected": int(open_diff["account_id"].nunique())}


def data_profile(ds: Dataset, cfg: Config) -> dict:
    led, rec = ds["ledger_entry"], ds["receivable"]
    tier = rec["counterparty_id"].map(ds["counterparty"].set_index("counterparty_id")["risk_tier"])
    ev = ds["receivable_event"]
    paid = ev[ev["event_type"] == "PAID"].set_index("receivable_id")["event_ts"]
    delay = (paid.reindex(rec["receivable_id"]).dt.normalize().to_numpy() - rec["due_date"].to_numpy()) / np.timedelta64(1, "D")
    rec = rec.assign(tier=tier, delay=delay)
    delays = {}
    for t, g in rec.groupby("tier"):
        d = g["delay"].dropna()
        delays[t] = {"invoices": int(len(g)), "paid": int(len(d)), "median_days_late": float(np.median(d)) if len(d) else None,
                     "share_paid_over_7_days_late": _ratio((d > 7).sum(), len(d)),
                     "written_off": int((g["status_at_end"] == "WRITTEN_OFF").sum())}
    fx = ds["currency_rate"].sort_values("rate_date")
    vol = {}
    for c, g in fx.groupby("base_currency"):
        r = np.diff(np.log(g["rate"].to_numpy()))
        vol[c] = {"realised_annual_vol": round(float(np.std(r) * np.sqrt(252)), 4), "configured": FX_VOL.get(c),
                  "change_over_period": round(float(g["rate"].iloc[-1] / g["rate"].iloc[0] - 1), 4)}
    amounts = {}
    for c, g in led.groupby("currency"):
        a = g["amount"].abs().astype(float) / (1 if c == "JPY" else 100)
        amounts[c] = {q: round(float(a.quantile(p)), 2) for q, p in (("p10", 0.1), ("p50", 0.5), ("p90", 0.9), ("p99", 0.99))}
    weekday = led["posting_date"].dt.day_name().value_counts()
    one_offs = ds["payable"][ds["payable"]["is_one_off"]]
    return {
        "rows": {k: int(len(v)) for k, v in ds.tables.items()},
        "ledger_entry_types": {k: int(v) for k, v in led["entry_type"].value_counts().items()},
        "ledger_amount_quantiles_by_currency": amounts,
        "postings_by_weekday": {k: int(weekday.get(k, 0)) for k in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]},
        "receivable_delay_by_risk_tier": delays,
        "fx": vol,
        "one_off_payments": {"count": int(len(one_offs)), "categories": {k: int(v) for k, v in one_offs["category"].value_counts().items()}},
        "entities_by_size": {k: int(v) for k, v in ds["legal_entity"]["size_tier"].value_counts().sort_index().items()},
        "accounts_by_currency": {k: int(v) for k, v in ds["bank_account"]["currency"].value_counts().sort_index().items()},
    }


def evaluate(ds: Dataset, cfg: Config, gt: pd.DataFrame | None) -> dict:
    out = {"profile": cfg.profile, "seed": cfg.seed}
    if gt is not None:
        out["detection"] = detection_quality(ds, gt)
    out["forecast_accuracy"] = forecast_accuracy(ds, gt)
    out["balance_accuracy"] = balance_accuracy(ds)
    out["variance_drivers"] = variance_drivers(ds)
    out["liquidity_outlook"] = liquidity_outlook(ds)
    out["reconciliation"] = reconciliation_stats(ds)
    out["data_profile"] = data_profile(ds, cfg)
    return out
