"""CashPilot dashboard (Streamlit). Read-only: it never writes to the dataset.

Start it with ``cashpilot dashboard`` (or ``streamlit run src/cashpilot/dashboard/app.py``).
All numbers come from ``cashpilot.dashboard.data``, which reuses the existing engine; this file only
lays them out and labels what is actual data, forecast output, scenario assumptions and ground truth.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from cashpilot.dashboard import data as D
from cashpilot.engine.explain import variance_breakdown

REQUIRED_TABLES = ("entity_cash_position", "daily_cash_position", "forecast_run", "forecast_position", "exception", "forecast_vs_actual")
GROUP = "All entities (group)"
ACTUAL, FORECAST, SCENARIO, EVAL, TRUTH = ":blue-badge[ACTUAL]", ":orange-badge[FORECAST]", ":violet-badge[SCENARIO ASSUMPTIONS]", ":green-badge[EVALUATION vs ACTUALS]", ":red-badge[GROUND TRUTH]"
USD_FORMAT = "localized"        # thousands separators in the viewer's locale


# ------------------------------------------------------------------ caching

@st.cache_resource(show_spinner="Loading dataset…")
def get_bundle(path: str, signature: tuple) -> D.Bundle:
    return D.load_bundle(path)          # `signature` changes when the files do, so a stale bundle is never reused


@st.cache_resource(show_spinner="Scoring against the ground truth…")
def get_evaluation(path: str, signature: tuple) -> dict:
    return D.evaluation(get_bundle(path, signature))


@st.cache_data(show_spinner="Rebuilding the scenario…")
def get_items(path: str, signature: tuple, run_id: str, scenario_id: str) -> pd.DataFrame:
    return D.cashflow_items(get_bundle(path, signature), run_id, scenario_id)


@st.cache_data(show_spinner="Comparing the two runs…")
def get_run_diff(path: str, signature: tuple, run_a: str, run_b: str) -> dict:
    return D.run_diff(get_bundle(path, signature), run_a, run_b)


# ------------------------------------------------------------------ helpers

def money_columns(df: pd.DataFrame) -> dict:
    return {c: st.column_config.NumberColumn(c, format=USD_FORMAT) for c in df.columns
            if c.endswith("_usd") or c in ("local_balance", "amount_local", "usd", "signed_usd", "net_usd", "usd_value", "local_total",
                                           "amount", "usd_impact_of_move")}


def _tidy_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Show whole-day timestamps as plain dates (2026-10-01, not 2026-10-01 00:00:00)."""
    df = df.copy()
    for c in df.select_dtypes(include=["datetime"]).columns:
        s = df[c].dropna()
        if len(s) and (s == s.dt.normalize()).all():
            df[c] = df[c].dt.date
    return df


def table(df: pd.DataFrame, **kwargs) -> None:
    if df is None or df.empty:
        st.caption("No records.")
        return
    df = _tidy_dates(df)
    st.dataframe(df, hide_index=True, column_config=money_columns(df), **kwargs)


def download(label: str, df: pd.DataFrame, name: str) -> None:
    c1, c2 = st.columns(2)
    c1.download_button(f"{label} (CSV)", D.to_csv_bytes(df), f"{name}.csv", "text/csv", key=f"{name}-csv")
    c2.download_button(f"{label} (JSON)", D.to_json_bytes(df), f"{name}.json", "application/json", key=f"{name}-json")


def usd(x: float) -> str:
    return f"{x:,.0f}"


def run_header(ds, run_id: str) -> None:
    r = ds["forecast_run"].set_index("run_id").loc[run_id]
    st.markdown(f"{FORECAST} **{run_id}** · {r['process']} / {r['run_purpose']} · status **{r['status_at_end']}** · cutoff {r['cutoff_date']:%Y-%m-%d} · "
                f"horizon to {r['horizon_end']:%Y-%m-%d} · knowledge cutoff {r['knowledge_cutoff_ts']:%Y-%m-%d %H:%M} UTC")


# --------------------------------------------------------------------- tabs

def tab_overview(b: D.Bundle, on, entity) -> None:
    st.markdown(f"{ACTUAL} Booked cash, valued in {b.reporting} at each day's FX rate. Entity totals add up account balances converted account by account.")
    overview = D.cash_overview(b, on)
    if (overview["buffer_status"] == "INCOMPLETE FX").any():
        st.warning("Some balances could not be converted on this date (missing FX rate): those entities' totals exclude the unconverted balance and are marked INCOMPLETE.")
    g = D.group_summary(overview)
    cols = st.columns(5)
    cols[0].metric(f"Total cash ({b.reporting})", usd(g["total_usd"]))
    cols[1].metric("Available", usd(g["available_usd"]), help="Total minus restricted accounts")
    cols[2].metric("Restricted", usd(g["restricted_usd"]))
    cols[3].metric("Headroom over buffers", usd(g["headroom_usd"]), help="Available cash minus the sum of the entities' minimum buffers")
    cols[4].metric("Entities below buffer", g["entities_below_buffer"], help=f"of {g['entities']} entities")
    view = overview if not entity else overview[overview["entity_id"] == entity]
    table(view.drop(columns=["size_tier"]))
    hist = D.cash_history(b, entity)
    st.subheader("Actual cash over time" + (f" · {b.entity_names[entity]}" if entity else " · group"))
    st.line_chart(hist.set_index("position_date")[["total_usd", "available_usd", "min_buffer_usd"]])
    if hist["incomplete"].any():
        st.caption(f"{int(hist['incomplete'].sum())} day(s) are INCOMPLETE (a balance could not be converted); the dips on those days are missing data, not cash leaving.")
    download("Cash overview", view, f"cash_overview_{pd.Timestamp(on):%Y%m%d}")


def tab_accounts(b: D.Bundle, on, entity) -> None:
    st.markdown(f"{ACTUAL} Balances per bank account in their own currency, the FX rate used and the {b.reporting} value (local balance × rate).")
    acc = D.account_balances(b, on)
    if entity:
        acc = acc[acc["entity_id"] == entity]
    ccys = st.multiselect("Currencies", sorted(acc["currency"].unique()), default=sorted(acc["currency"].unique()))
    acc = acc[acc["currency"].isin(ccys)]
    problems = acc[acc["fx_status"].isin(["FALLBACK", "MISSING"])]
    if len(problems):
        st.warning(f"{len(problems)} account(s) use a fallback or missing rate on this date (FALLBACK = previous rate within tolerance; MISSING = not converted).")
    table(acc.drop(columns=["entity_name"]))
    st.subheader("Currency exposure")
    shock = st.slider("FX sensitivity: every non-reporting currency moves by (%)", -30, 30, -10)
    expo = D.currency_exposure(b, on, shock)
    left, right = st.columns([3, 2])
    left.bar_chart(expo.set_index("currency")["usd_value"])
    right.caption("Sensitivity is plain arithmetic (value × move), not a forecast.")
    table(expo.rename(columns={"usd_impact_of_shock": "usd_impact_of_move"}))
    st.caption("Cash by entity and currency (reporting-currency value)")
    table(D.exposure_matrix(b, on))
    st.subheader("FX rates")
    hist = D.fx_history(b)
    pick = st.selectbox("Currency", [c for c in hist.columns if c != "rate_date"])
    st.line_chart(hist.set_index("rate_date")[[pick]])
    gaps = D.fx_gaps(b)
    mine = gaps[gaps["currency"] == pick]
    st.caption(f"{len(gaps)} business-day fixings are missing in this dataset in total; {len(mine)} for {pick}. "
               "Each shows the decision the rules apply (previous rate within tolerance, otherwise conversion blocked):")
    table(mine)


def tab_forecast(b: D.Bundle, run_id: str, scenario: str, entity) -> None:
    ds = b.ds
    run_header(ds, run_id)
    series = D.forecast_series(ds, run_id, scenario, entity)
    cur = D.scenario_curves(ds, run_id, entity)
    label = b.entity_names[entity] if entity else "group (buffers summed)"
    st.subheader(f"Daily projected available cash · {scenario} · {label}")
    st.line_chart(series.set_index("position_date")[["closing_available_usd", "min_buffer_usd"]])
    below = int((series["headroom_usd"] < 0).sum())
    worst = int(series["entities_below_buffer"].max())
    if below:
        st.error(f"{below} of {len(series)} projected days are below the minimum buffer.")
    elif worst:
        st.warning(f"The {'group total' if not entity else 'entity'} stays above {'the summed buffers' if not entity else 'its buffer'}, but up to {worst} "
                   f"entit{'y falls' if worst == 1 else 'ies fall'} below {'its' if worst == 1 else 'their'} own buffer (listed below). "
                   "A group total can hide an entity shortfall.")
    else:
        st.success("No projected day is below the minimum buffer.")
    st.subheader("13-week view (weekly)")
    table(D.weekly_view(series))
    st.subheader(f"Scenario comparison {SCENARIO}")
    st.line_chart(cur.set_index("position_date"))
    comp = D.scenario_comparison(ds, run_id)
    table(comp)
    st.caption("Scenarios differ only by the documented assumptions below, applied in order to the same snapshot; their effects add up exactly to the difference from base.")
    assumptions = D.assumption_table(ds, run_id)
    if scenario in set(assumptions["scenario_id"]):
        table(assumptions[assumptions["scenario_id"] == scenario])
    else:
        st.caption(f"{scenario} has no assumptions: latest known dates and amounts, FX held at the cutoff rate.")
    st.subheader(f"Entities that breach their buffer · {scenario}")
    breaches = D.entity_breaches(ds, run_id, scenario)
    table(breaches)
    if entity and not breaches[breaches["entity_id"] == entity].empty:
        first = pd.Timestamp(breaches.loc[breaches["entity_id"] == entity, "first_breach"].iloc[0])
        with st.expander(f"Why does {b.entity_names[entity]} fall below its buffer on {first:%Y-%m-%d}?", expanded=True):
            items = get_items(str(b.path), D.dataset_signature(b.path), run_id, scenario)
            window = items[(items["entity_id"] == entity) & items["in_horizon"] & (items["date"] <= first)]
            opening = series["opening_usd"].iloc[0]
            st.write(f"Opening available cash {usd(opening)}; net of the items below up to the first breach: {usd(window['signed_usd'].sum())}.")
            table(window.reindex(window["usd"].sort_values(ascending=False).index).head(10)[
                ["cf_id", "direction", "flow_category", "counterparty_id", "date", "shifted_days", "usd"]])
    download("Daily projection", series, f"forecast_{run_id}_{scenario}")


def tab_drivers(b: D.Bundle, run_id: str, scenario: str, entity) -> None:
    ds = b.ds
    run_header(ds, run_id)
    items = get_items(str(b.path), D.dataset_signature(b.path), run_id, scenario)
    st.subheader(f"What drives cash in the 13-week horizon · {scenario}")
    drivers = D.driver_summary(items, entity)
    if len(drivers):
        st.bar_chart(drivers.set_index("week_no"))
    st.caption("Net cash per week by flow category (inflows positive). Amounts are in the reporting currency at the scenario's FX rates.")
    c1, c2, c3 = st.columns(3)
    direction = c1.selectbox("Direction", ["All", "INFLOW", "OUTFLOW"])
    moved = c2.checkbox("Only items this scenario moved in time", value=False)
    cats = c3.multiselect("Flow category", sorted(items["flow_category"].unique()))
    view = items[items["in_horizon"]]
    if entity:
        view = view[view["entity_id"] == entity]
    if direction != "All":
        view = view[view["direction"] == direction]
    if moved:
        view = view[view["shifted_days"].fillna(0) != 0]
    if cats:
        view = view[view["flow_category"].isin(cats)]
    st.write(f"{len(view):,} items. Delayed receipts keep their cash: they land on the shifted date (items moved past the horizon fall out of the window).")
    table(view.sort_values(["date", "cf_id"]).drop(columns=["entity_name", "live", "in_horizon", "week_no"]).head(1000))
    download("Cash-flow items", view, f"items_{run_id}_{scenario}")

    st.subheader("Why did the forecast change?")
    runs = D.run_catalog(ds)
    ids = runs["run_id"].tolist()
    pos = ids.index(run_id)
    default = ids[pos - 1] if pos > 0 else ids[pos]
    other = st.selectbox("Compare with run", ids, index=ids.index(default), format_func=lambda r: runs.set_index("run_id").at[r, "label"])
    if other == run_id:
        st.info("Pick a different run to compare.")
        return
    diff = get_run_diff(str(b.path), D.dataset_signature(b.path), other, run_id)
    s = diff["summary"]
    cols = st.columns(4)
    cols[0].metric("Opening available", usd(s["opening_available_b_usd"]), usd(s["opening_available_b_usd"] - s["opening_available_a_usd"]))
    cols[1].metric("Lowest projected cash (base)", usd(s["lowest_available_b_usd"]), usd(s["lowest_available_b_usd"] - s["lowest_available_a_usd"]))
    cols[2].metric("Items added / removed", f"{s['items_added']} / {s['items_removed']}")
    cols[3].metric("Items changed", s["items_changed"])
    st.caption(f"{other} → {run_id}. Opening cash moves with new bank statements and FX rates; items change through documented revisions, "
               "newly known items and items leaving the horizon.")
    types = ["All"] + sorted(diff["items"]["change_type"].unique())
    kind = st.selectbox("Change type", types)
    items_diff = diff["items"] if kind == "All" else diff["items"][diff["items"]["change_type"] == kind]
    if entity:
        items_diff = items_diff[items_diff["entity_id"] == entity]
    table(items_diff.head(200))
    st.caption("FX rates used by the two runs")
    table(diff["fx"])


def tab_exceptions(b: D.Bundle) -> None:
    st.markdown(f"{ACTUAL} Findings raised by CashPilot's rules on the data and on the forecast runs. Detectors never read the ground truth.")
    exc = D.exceptions_table(b)
    c1, c2, c3 = st.columns(3)
    types = c1.multiselect("Type", sorted(exc["exception_type"].unique()))
    sev = c2.multiselect("Severity", ["CRITICAL", "HIGH", "MEDIUM", "LOW"])
    status = c3.multiselect("Status", sorted(exc["status_at_end"].unique()))
    view = exc
    if types:
        view = view[view["exception_type"].isin(types)]
    if sev:
        view = view[view["severity"].isin(sev)]
    if status:
        view = view[view["status_at_end"].isin(status)]
    st.write(f"{len(view)} of {len(exc)} exceptions")
    table(view.drop(columns=["details", "entity_name"]))
    download("Exceptions", view, "exceptions")
    if view.empty:
        return
    pick = st.selectbox("Trace an exception", view["exception_id"].tolist(),
                        format_func=lambda i: f"{i} · {view.set_index('exception_id').at[i, 'exception_type']} · {view.set_index('exception_id').at[i, 'record_id']}")
    t = D.exception_trace(b, pick)
    e = t["exception"]
    st.markdown(f"### {e['exception_type']} · {e['severity']} · {e['status_at_end']}")
    st.write(f"**Why it was flagged:** {e['details']}")
    st.write(f"**Rule {e['rule_id']}:** {t['rule_text']}")
    st.write(f"**Decision `{e['decision']}`:** {t['decision_text']}")
    ids = {k: e[k] for k in ("record_table", "record_id", "related_record_id", "entity_id", "account_id", "run_id") if pd.notna(e[k])}
    st.write("**Identifiers:** " + " · ".join(f"{k} = `{v}`" for k, v in ids.items()))
    st.write("**Workflow history** (append-only)")
    table(t["events"])
    for title, frame in t["evidence"]:
        st.write(f"**{title}**")
        table(frame)
    st.subheader("Reconciliation")
    rec = D.reconciliation_overview(b)
    cols = st.columns(4)
    cols[0].metric("Bank statement days", f"{rec['statements']:,}")
    cols[1].metric("Breaks raised", rec["breaks"], help=f"{rec['breaks_high']} above materiality")
    cols[2].metric("Account-days with open difference", f"{rec['account_days_with_open_difference']:,}")
    cols[3].metric("Accounts affected", len(rec["accounts"]))
    table(rec["accounts"])
    st.caption("After a break the bank and book balances stay apart until the item is booked (see `bank_minus_book` in the daily positions).")


def tab_accuracy(b: D.Bundle, run_id: str, scenario: str, entity) -> None:
    ds = b.ds
    st.markdown(f"{EVAL} How each forecast version compared with what actually happened. Weeks count only once fully elapsed.")
    run_header(ds, run_id)
    fva = D.forecast_vs_actual(ds, run_id, scenario, entity)
    if fva.empty:
        st.info("No fully elapsed week to compare for this run yet (the run's horizon is still in the future).")
    else:
        st.subheader("Weekly forecast vs actual (net external cash flow)")
        table(fva)
        drivers = [c for c in fva.columns if c.endswith("_usd") and c not in ("forecast_net_usd", "actual_net_usd", "variance_usd", "residual_usd")]
        st.bar_chart(fva.set_index("week_no")[drivers])
        st.caption(f"Drivers add up to actual − forecast; unexplained residual: {fva['residual_usd'].abs().sum():,.2f}.")
        week = st.selectbox("Drill into week", fva["week_no"].tolist())
        ents = [entity] if entity else sorted(ds["forecast_vs_actual"].query("run_id == @run_id")["entity_id"].unique())
        who = st.selectbox("Entity", ents, format_func=lambda x: f"{x} · {b.entity_names[x]}")
        br = variance_breakdown(ds, run_id, who, int(week), scenario_prefix=scenario, top=5)
        if br:
            st.write(f"Forecast {br['forecast_usd'] / 100:,.2f} · actual {br['actual_usd'] / 100:,.2f} · variance **{br['variance_usd'] / 100:,.2f}** (residual {br['residual_usd'] / 100:,.2f})")
            if not br["drivers"]:
                st.caption("The item-level drill-down is stored for the base scenario only; the weekly driver totals above exist for every scenario.")
            for d in br["drivers"]:
                with st.expander(f"{d['driver']} · {d['total_usd'] / 100:,.2f} · {d['records']} record(s)"):
                    table(pd.DataFrame(d["top"]).assign(amount_usd=lambda x: x["amount_usd"] / 100.0))
        download("Forecast vs actual", fva, f"fva_{run_id}_{scenario}")
    ev = get_evaluation(str(b.path), D.dataset_signature(b.path))
    st.subheader("Accuracy of approved forecast versions")
    fa = ev["forecast_accuracy"]["approved_versions"]
    st.caption(f"{fa['runs']} approved versions. WAPE of weekly net flows per entity, and MAPE of group available cash at week-ends.")
    flows = pd.DataFrame(fa["by_horizon"]).T.reset_index().rename(columns={"index": "horizon"})
    balance = pd.DataFrame(ev["balance_accuracy"]).T.reset_index().rename(columns={"index": "horizon"})
    c1, c2 = st.columns(2)
    with c1:
        st.write("Weekly net cash flow")
        table(flows)
    with c2:
        st.write("Group cash balance")
        table(balance)
    st.write("What explains the variance (share of absolute variance)")
    shares = pd.Series(ev["variance_drivers"]["share_of_absolute_variance"], name="share")
    st.bar_chart(shares)
    with st.expander(f"Reviewer view {TRUTH} · detection quality against the labelled anomalies"):
        st.caption("The ground truth is kept apart from the dataset and read only here, after detection, to score it.")
        det = ev.get("detection")
        if det:
            table(pd.DataFrame(det["by_issue"]))
            table(pd.DataFrame(det["by_sub_type"]))
            st.write(f"Negative controls (legitimate look-alikes): {det['negative_controls']}, wrongly flagged: **{det['negative_controls_flagged']}**")
        else:
            st.info("No ground truth in this dataset folder.")


def tab_audit(b: D.Bundle, run_id: str) -> None:
    ds = b.ds
    path = b.path
    run_header(ds, run_id)
    trail = D.audit_trail(ds, run_id)
    r = trail["run"]
    st.write(f"Version {r['version']} of cutoff {r['cutoff_date']:%Y-%m-%d} · created by {r['created_by']} · supersedes: {r['supersedes_run_id'] if pd.notna(r['supersedes_run_id']) else '—'}")
    st.code(f"input hash   {r['input_hash']}\nresult hash  {r['result_hash']}", language="text")
    st.write("**Lifecycle** (append-only events)")
    table(trail["events"])
    st.write("**Access and action audit for this run**")
    table(trail["audit"])
    st.write("**Input lineage** (how each forecast item was treated)")
    table(trail["lineage"])
    if st.button("Verify reproducibility", help="Re-run this version from the data known at its cutoff and compare the hashes"):
        with st.spinner("Re-running…"):
            v = D.verify_reproducibility(b, run_id)
        if v["reproduced"]:
            st.success("Reproduced: re-running from the data known at the cutoff gives identical input and result hashes.")
        else:
            st.error("Not reproducible as-of its cutoff: this run used inputs recorded after its claimed knowledge cutoff (see rule R-LEAK-001).")
        st.json(v)
    st.subheader("Dataset and validation")
    val = D.validation_overview(path)
    if val:
        cols = st.columns(4)
        cols[0].metric("Validation", val["overall"])
        cols[1].metric("Checks", val["checks"])
        cols[2].metric("PASS / EXPECTED / FAIL", " / ".join(str(val["by_status"].get(k, 0)) for k in ("PASS", "EXPECTED", "FAIL")),
                       help="EXPECTED = found only labelled anomalies")
        cols[3].metric("Clean baseline violations", val.get("baseline", {}).get("violations", "n/a"))
    manifest_path = Path(path) / "manifest.json"
    if manifest_path.is_file():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        st.write(f"Profile **{m['profile']}**, seed **{m['seed']}**. Reproduce this dataset with:")
        st.code(m["command"], language="bash")
        st.caption(f"Provenance: {m['provenance']}")
    files = D.manifest_files(path)
    with st.expander(f"Files and checksums ({len(files)})"):
        table(files)
    st.subheader("Export")
    runs = D.run_catalog(ds)
    download("Run catalogue", runs.drop(columns=["label"]), "forecast_runs")
    st.caption("Complete CSV, JSON and SQL exports of every table are in the dataset folder (`csv/`, `json/`, `sql/`).")


# --------------------------------------------------------------------- main

def main() -> None:
    st.set_page_config(page_title="CashPilot", layout="wide")
    st.title("CashPilot")
    st.caption("Multi-entity cash consolidation and 13-week liquidity forecasting · synthetic data · read-only")

    default = os.environ.get("CASHPILOT_DATA", "data/starter")
    options = [str(p) for p in D.discover_datasets(Path.cwd())]
    if default not in options and Path(default, "generation_config.json").is_file():
        options.insert(0, default)
    if not options:
        st.error("No dataset found. Create one with `cashpilot all --profile starter` and restart.")
        st.stop()
    path = st.sidebar.selectbox("Dataset", options, index=options.index(default) if default in options else 0)
    b = get_bundle(path, D.dataset_signature(path))
    missing = [t for t in REQUIRED_TABLES if t not in b.ds.tables]
    if missing:
        st.error(f"This folder has not been processed yet (missing {', '.join(missing)}). Run `cashpilot all` or `cashpilot run --data {path}`.")
        st.stop()

    ds = b.ds
    st.sidebar.markdown(f"Profile **{b.cfg.profile}** · seed **{b.cfg.seed}** · reporting currency **{b.reporting}**")
    names = {e: f"{e} · {n}" for e, n in b.entity_names.items()}
    entity = st.sidebar.selectbox("Entity", [None, *names], format_func=lambda e: GROUP if e is None else names[e])
    on = st.sidebar.date_input("Actuals as of", value=D.default_date(ds), min_value=ds["entity_cash_position"]["position_date"].min(),
                               max_value=ds["entity_cash_position"]["position_date"].max())
    runs = D.run_catalog(ds)
    labels = runs.set_index("run_id")["label"].to_dict()
    run_id = st.sidebar.selectbox("Forecast run", runs["run_id"].tolist()[::-1], index=runs["run_id"].tolist()[::-1].index(D.default_run(ds)),
                                  format_func=lambda r: labels[r])
    scenario = st.sidebar.selectbox("Scenario", D.run_scenarios(ds, run_id))
    val = D.validation_overview(path)
    if val:
        st.sidebar.markdown(f"Validation **{val['overall']}** · {val['checks']} checks")
    st.sidebar.caption("Actual data, forecast outputs, scenario assumptions and ground-truth evaluation are labelled separately throughout.")

    names = ["Cash overview", "Accounts & currencies", "Forecast", "Cash-flow drivers", "Exceptions", "Actual vs forecast", "Audit & exports"]
    wanted = st.query_params.get("tab")                    # deep link: ?tab=Forecast
    tabs = st.tabs(names, default=wanted if wanted in names else None)
    with tabs[0]:
        tab_overview(b, on, entity)
    with tabs[1]:
        tab_accounts(b, on, entity)
    with tabs[2]:
        tab_forecast(b, run_id, scenario, entity)
    with tabs[3]:
        tab_drivers(b, run_id, scenario, entity)
    with tabs[4]:
        tab_exceptions(b)
    with tabs[5]:
        tab_accuracy(b, run_id, scenario, entity)
    with tabs[6]:
        tab_audit(b, run_id)


main()
