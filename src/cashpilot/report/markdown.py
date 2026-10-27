"""Render the evaluation results as Markdown."""

from __future__ import annotations

import pandas as pd

from cashpilot.dataset import Dataset


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * float(x):.1f}%"


def _usd(x) -> str:
    return f"{float(x):,.0f}"


def evaluation_report(ev: dict) -> str:
    out = [f"# Evaluation — `{ev['profile']}` dataset (seed {ev['seed']})", ""]
    det = ev.get("detection")
    if det:
        out += ["## Detection quality against the ground truth", "",
                "Detectors run without the ground truth; labels are joined afterwards to score them.", "",
                "| Edge case | Labelled | Detected | Precision | Recall | F1 | Decision accuracy |", "|---|---|---|---|---|---|---|"]
        for r in det["by_issue"]:
            out.append(f"| {r['issue_type']} | {r['labelled']} | {r['detected']} | {_pct(r['precision'])} | {_pct(r['recall'])} | "
                       f"{_pct(r['f1'])} | {_pct(r['decision_accuracy'])} |")
        out += ["", "Recall by variant:", "", "| Edge case | Variant | Labelled | Detected | Recall |", "|---|---|---|---|---|"]
        for r in det["by_sub_type"]:
            out.append(f"| {r['issue_type']} | {r['sub_type']} | {r['labelled']} | {r['detected']} | {_pct(r['recall'])} |")
        out += ["", f"Negative controls (legitimate look-alikes): {det['negative_controls']}, flagged: **{det['negative_controls_flagged']}**.",
                "", "`FUZZY_BEYOND_TOLERANCE` duplicates are re-keyed 5-6 days away from the original, outside the documented "
                "3-day matching tolerance; they are included on purpose to show where the rule stops working.", ""]
    fa = ev.get("forecast_accuracy", {})
    if fa:
        out += ["## Forecast accuracy (approved versions, base scenario)", "",
                "Weekly **net external cash flow** per entity, compared with actuals for every fully elapsed horizon week. "
                "WAPE = Σ|actual − forecast| / Σ|actual|; bias = Σ(actual − forecast) / Σ|actual|.", "",
                "| Horizon | WAPE | Bias | Entity-weeks |", "|---|---|---|---|"]
        for k, v in fa["approved_versions"]["by_horizon"].items():
            out.append(f"| {k} | {_pct(v['wape'])} | {_pct(v['bias'])} | {v['entity_weeks']:,} |")
        out += ["", "By scenario (same versions):", "", "| Scenario | Week 1 WAPE | Weeks 2-4 WAPE | Weeks 5-13 WAPE |", "|---|---|---|---|"]
        for s, v in fa["approved_versions_by_scenario"].items():
            out.append(f"| {s} | {_pct(v['week 1']['wape'])} | {_pct(v['weeks 2-4']['wape'])} | {_pct(v['weeks 5-13']['wape'])} |")
        sig = fa.get("lookahead_signature")
        if sig:
            out += ["", "**Look-ahead signature.** Week-1 WAPE of the leaky legacy runs: "
                    f"{_pct(sig['leaky_runs_week1_wape'])}; of their as-of re-runs: {_pct(sig['their_as_of_reruns_week1_wape'])}; "
                    f"of all other approved runs: {_pct(sig['other_runs_week1_wape'])}. The leaky runs started from a balance seven "
                    "days old *and* dropped items already settled, so their first week is distorted; lineage, not accuracy, is "
                    "what proves the leak (rule R-LEAK-001)."]
    ba = ev.get("balance_accuracy")
    if ba:
        out += ["", "## Cash balance accuracy (group level)", "",
                "Projected group available cash at each forecast week-end vs actual group available cash "
                "(internal pooling nets out at group level; restricted cash excluded on both sides).", "",
                "Weeks whose actual could not be fully converted to USD (a missing FX rate) are excluded, not compared.", "",
                "| Horizon | MAPE | Bias | Observations | Excluded (incomplete FX) |", "|---|---|---|---|---|"]
        for k, v in ba.items():
            out.append(f"| {k} | {_pct(v['mape'])} | {_pct(v['bias'])} | {v['observations']} | {v['excluded_incomplete_fx']} |")
    vd = ev.get("variance_drivers")
    if vd:
        out += ["", "## What explains the variance", "",
                "Share of absolute variance by driver (approved versions, base scenario). Drivers add up exactly to "
                f"actual − forecast; total unexplained residual: **USD {vd['residual_usd']:,}**.", "",
                "| Driver | Share of absolute variance | Net effect (USD) |", "|---|---|---|"]
        for k, v in vd["share_of_absolute_variance"].items():
            out.append(f"| {k} | {_pct(v)} | {_usd(vd['net_by_driver_usd'][k])} |")
        out += ["", "Most variance comes from business that did not exist at the cutoff (invoices raised later and paid "
                "within the horizon) and from customers paying on a different week than their due date - exactly the "
                "levers the delayed-receipt scenario stresses."]
    rc = ev.get("reconciliation")
    if rc:
        out += ["", "## Reconciliation", "",
                f"{rc['statements']:,} bank statement days; {_pct(rc['statement_days_reconciled'])} reconcile to the ledger exactly. "
                f"{rc['breaks']} breaks raised ({rc['breaks_high']} above materiality). After a break the bank and book balances "
                f"stay apart until the item is booked: {rc['account_days_with_open_difference']:,} account-days across "
                f"{rc['accounts_affected']} accounts carry an open difference (visible in `daily_cash_position.bank_minus_book`)."]
    return "\n".join(out) + "\n"


def liquidity_report(ev: dict, ds: Dataset) -> str:
    lo = ev.get("liquidity_outlook")
    if not lo:
        return "# Liquidity outlook\n\nNo live run.\n"
    out = [f"# 13-week liquidity outlook — run `{lo['run_id']}` (cutoff {lo['cutoff']})", "",
           "Available cash excludes restricted accounts. Entity figures are standalone (before cash pooling); "
           "the group pool covers entity shortfalls, which is the decision the alerts drive.", "",
           "| Scenario | Opening available | Lowest available | Lowest on | Closing available | Entities below buffer | Funding gap |",
           "|---|---|---|---|---|---|---|"]
    for sid, s in lo["scenarios"].items():
        out.append(f"| {sid} | {_usd(s['opening_available_usd'])} | {_usd(s['lowest_available_usd'])} | {s['lowest_on']} | "
                   f"{_usd(s['closing_available_usd'])} | {s['entities_breaching']} | {_usd(s['funding_gap_usd'])} |")
    eff = ds["scenario_assumption_effect"]
    eff = eff[eff["run_id"] == lo["run_id"]].merge(ds["scenario_assumption"][["assumption_id", "parameter", "filter_value", "value", "rationale"]],
                                                   on="assumption_id")
    out += ["", "## What each documented assumption does to this forecast", "",
            "Assumptions are applied in order to the same snapshot; their effects add up exactly to the difference from base.", "",
            "| Scenario | # | Assumption | Parameter | Items changed | Δ net flow (USD) | Δ lowest group cash (USD) |", "|---|---|---|---|---|---|---|"]
    for r in eff.sort_values(["scenario_id", "apply_order"]).itertuples():
        out.append(f"| {r.scenario_id} | {r.apply_order} | {r.assumption_id}: {r.rationale} | {r.parameter} {r.filter_value or ''} = {r.value} | "
                   f"{r.items_affected} | {_usd(r.delta_net_flow_usd / 100)} | {_usd(r.delta_min_available_usd / 100)} |")
    out += ["", "## Entities below their buffer", ""]
    for sid, s in lo["scenarios"].items():
        out += [f"### {sid}", "", "| Entity | Name | First breach | Days below | Largest shortfall (USD) |", "|---|---|---|---|---|"]
        for b in s["breaches"]:
            out.append(f"| {b['entity_id']} | {b['entity_name']} | {b['first_breach']} | {b['days_below_buffer']} | {_usd(b['max_shortfall_usd'])} |")
        out.append("")
    exc = ds["exception"]
    alerts = exc[(exc["run_id"] == lo["run_id"]) & (exc["category"] == "BUSINESS_ALERT")]
    out += ["## Alerts raised on this run", "", f"{len(alerts)} liquidity alerts (rule R-LIQ-001), all worked through the playbook: "
            + ", ".join(f"{k}: {v}" for k, v in alerts["status_at_end"].value_counts().items()) + "."]
    return "\n".join(out) + "\n"


def data_profile_report(ev: dict) -> str:
    p = ev["data_profile"]
    out = [f"# Data profile — `{ev['profile']}` dataset", "", "## Row counts", "", "| Table | Rows |", "|---|---|"]
    out += [f"| `{k}` | {v:,} |" for k, v in p["rows"].items()]
    out += ["", "## Customer payment behaviour by risk tier (rule-driven)", "",
            "| Tier | Invoices | Paid | Median days late | Paid > 7 days late | Written off |", "|---|---|---|---|---|---|"]
    for t, d in p["receivable_delay_by_risk_tier"].items():
        out.append(f"| {t} | {d['invoices']:,} | {d['paid']:,} | {d['median_days_late']} | {_pct(d['share_paid_over_7_days_late'])} | {d['written_off']} |")
    out += ["", "## FX movement", "", "| Currency | Realised annual volatility | Configured | Change over the period |", "|---|---|---|---|"]
    for c, d in p["fx"].items():
        out.append(f"| {c}/USD | {_pct(d['realised_annual_vol'])} | {_pct(d['configured'])} | {_pct(d['change_over_period'])} |")
    out += ["", "## Ledger", "", "| Entry type | Count |", "|---|---|"]
    out += [f"| {k} | {v:,} |" for k, v in p["ledger_entry_types"].items()]
    out += ["", "Absolute posting amounts by currency (major units):", "", "| Currency | p10 | p50 | p90 | p99 |", "|---|---|---|---|---|"]
    for c, q in p["ledger_amount_quantiles_by_currency"].items():
        out.append(f"| {c} | {_usd(q['p10'])} | {_usd(q['p50'])} | {_usd(q['p90'])} | {_usd(q['p99'])} |")
    out += ["", "Postings by weekday: " + ", ".join(f"{k} {v:,}" for k, v in p["postings_by_weekday"].items()) + ".",
            "", f"Large one-off payments: {p['one_off_payments']['count']} ("
            + ", ".join(f"{k} {v}" for k, v in p["one_off_payments"]["categories"].items()) + ").",
            "", "Entities by size tier: " + ", ".join(f"{k} {v}" for k, v in p["entities_by_size"].items())
            + ". Accounts by currency: " + ", ".join(f"{k} {v}" for k, v in p["accounts_by_currency"].items()) + "."]
    return "\n".join(out) + "\n"


def reproducibility_report(rep: dict) -> str:
    out = [f"# Reproducibility — `{rep['profile']}` dataset, seed {rep['seed']}", "",
           f"The full pipeline was run twice from scratch with the same seed. **Result: {'IDENTICAL' if rep['identical'] else 'DIFFERENT'}** "
           f"— {rep['files_compared']} files compared, {rep['files_identical']} byte-identical (SHA-256), "
           f"{rep['rows_compared']:,} rows in total.", "",
           "| File | Rows | SHA-256 (run 1) | Match |", "|---|---|---|---|"]
    for f in rep["files"]:
        out.append(f"| `{f['path']}` | {f['rows'] if f['rows'] is not None else ''} | `{f['sha256_run1'][:16]}…` | {'yes' if f['match'] else '**no**'} |")
    return "\n".join(out) + "\n"
