"""CashPilot dashboard (Streamlit). Read-only: it never writes to the dataset.

Start it with ``cashpilot dashboard`` (or ``streamlit run src/cashpilot/dashboard/app.py``).
All numbers come from ``cashpilot.dashboard`` (``data``, ``explorer``, ``guide``), which reuse the existing engine; this file only
lays them out in plain language and labels what is actual data, forecast output, scenario assumptions and ground truth.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from cashpilot.dashboard import charts as C
from cashpilot.dashboard import data as D
from cashpilot.dashboard import explorer as X
from cashpilot.dashboard import guide as G
from cashpilot.dashboard import text as T
from cashpilot.engine.explain import variance_breakdown

REQUIRED_TABLES = ("entity_cash_position", "daily_cash_position", "forecast_run", "forecast_position", "exception", "forecast_vs_actual")
GROUP = "All entities (group)"
ACTUAL, FORECAST, SCENARIO, EVAL, TRUTH = (":blue-badge[ACTUAL]", ":orange-badge[FORECAST]", ":violet-badge[SCENARIO ASSUMPTIONS]",
                                           ":green-badge[EVALUATION vs ACTUALS]", ":red-badge[GROUND TRUTH]")
TAB_NAMES = ["Start here", "Cash overview", "Accounts & currencies", "Entities & transactions", "Forecast", "Cash-flow drivers", "Exceptions",
             "Actual vs forecast", "Audit & exports"]
MONEY_NAMES = {"local_balance", "amount_local", "usd", "signed_usd", "usd_value", "local_total", "amount", "money_in", "money_out", "min_liquidity_buffer",
               "overdraft_limit", "opening_balance", "usd_impact_of_move", "bank_minus_book_local", "balance_usd", "opening", "inflows", "outflows"}
STATUS_ICON = {"PASS": "✅", "FAIL": "❌"}
PEOPLE_COLUMNS = ("actor_id", "created_by", "assigned_to")
# names for the ids shown in tables (filled in by main(); the data keeps the ids)
SHOW = {"users": {}, "entities": {}, "scenarios": {}}


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

def _is_money(column: str) -> bool:
    return column.endswith("_usd") or column in MONEY_NAMES


def column_config(df: pd.DataFrame, labels: dict | None = None, pct: tuple = ()) -> dict:
    cfg = {}
    for c in df.columns:
        label = (labels or {}).get(c) or T.LABELS.get(c) or c.replace("_", " ").capitalize()
        help_text = T.HELP.get(c)
        if c in pct:
            cfg[c] = st.column_config.NumberColumn(label, format="%.1f%%", help=help_text)
        elif _is_money(c):
            cfg[c] = st.column_config.NumberColumn(label, format="accounting", help=help_text)
        elif pd.api.types.is_bool_dtype(df[c]):
            cfg[c] = st.column_config.CheckboxColumn(label, help=help_text)
        else:
            cfg[c] = st.column_config.Column(label, help=help_text)
    return cfg


def _tidy(df: pd.DataFrame) -> pd.DataFrame:
    """Whole-day timestamps as plain dates, and empty cells instead of the word None."""
    df = df.copy()
    for c in df.select_dtypes(include=["datetime"]).columns:
        s = df[c].dropna()
        whole_days = len(s) == 0 or bool((s == s.dt.normalize()).all())
        # ISO text keeps the column one type (Arrow cannot mix dates with blanks) and still sorts correctly
        df[c] = df[c].dt.strftime("%Y-%m-%d" if whole_days else "%Y-%m-%d %H:%M").fillna("")
    for c in df.columns:
        if c in T.CODE_COLUMNS:
            df[c] = df[c].map(lambda v, c=c: T.plain_value(c, v))
        elif c in PEOPLE_COLUMNS:
            df[c] = df[c].map(lambda v: SHOW["users"].get(v, v))
        elif c == "parent_entity_id":
            df[c] = df[c].map(lambda v: SHOW["entities"].get(v, v))
        elif c == "scenario_id":
            df[c] = df[c].map(lambda v: SHOW["scenarios"].get(v, v))
    for c in df.select_dtypes(include=["object"]).columns:
        df[c] = df[c].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT else v)
        if df[c].map(type).nunique() > 1:          # mixed numbers and text would also fail to serialise
            df[c] = df[c].astype(str)
    return df


def table(df: pd.DataFrame, labels: dict | None = None, pct: tuple = (), empty: str = "Nothing to show.", **kwargs) -> None:
    if df is None or df.empty:
        st.caption(empty)
        return
    df = _tidy(df)
    st.dataframe(df, hide_index=True, column_config=column_config(df, labels, pct), **kwargs)


def static_table(df: pd.DataFrame, labels: dict | None = None) -> None:
    """A fully wrapped table for text-heavy content (nothing is cut off with an ellipsis)."""
    out = _tidy(df).rename(columns=lambda c: (labels or {}).get(c) or T.LABELS.get(c) or c.replace("_", " ").capitalize())
    for c in out.columns:
        if pd.api.types.is_integer_dtype(out[c]):
            out[c] = out[c].map(lambda v: f"{v:,}")
        elif pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].map(lambda v: f"{v:,.2f}")
    st.table(out.set_index(out.columns[0]))


def download(label: str, df: pd.DataFrame, name: str) -> None:
    c1, c2 = st.columns(2)
    c1.download_button(f"{label} (CSV)", D.to_csv_bytes(df), f"{name}.csv", "text/csv", key=f"{name}-csv")
    c2.download_button(f"{label} (JSON)", D.to_json_bytes(df), f"{name}.json", "application/json", key=f"{name}-json")


def chart(c) -> None:
    st.altair_chart(c, width="stretch")


def sname(scenario_id: str) -> str:
    return SHOW["scenarios"].get(scenario_id, scenario_id)


def usd(x: float) -> str:
    return f"{x:,.0f}"


def how_to_read(*points: str) -> None:
    with st.expander("How to read this tab"):
        for p in points:
            st.markdown(f"- {p}")


def run_header(ds, run_id: str) -> None:
    r = ds["forecast_run"].set_index("run_id").loc[run_id]
    purpose = T.PURPOSE_TEXT.get(r["run_purpose"], r["run_purpose"].lower())
    st.markdown(f"{FORECAST} **{run_id}** · {purpose} forecast, version {r['version']} · status **{r['status_at_end'].lower()}** · as of {r['cutoff_date']:%Y-%m-%d} · "
                f"projects to {r['horizon_end']:%Y-%m-%d} · uses only records known before {r['knowledge_cutoff_ts']:%Y-%m-%d %H:%M} UTC")


# --------------------------------------------------------------------- tabs

def tab_start(b: D.Bundle) -> None:
    ds = b.ds
    st.subheader("What is CashPilot?")
    st.write("CashPilot answers one treasury question: **will each company in the group, and the group as a whole, have enough cash over the next "
             "13 weeks** - normally, if customers pay late, and under stress? It adds up bank balances held in several currencies into one reporting "
             "currency (USD), projects the receipts and payments we expect, keeps every forecast version, and later compares each forecast with what "
             "really happened. It also checks its own data and raises problems for people to resolve.")
    st.write("**How to use it:** choose a dataset, an entity (or the whole group), a date and a forecast run in the left sidebar - every tab follows those "
             "choices. The tabs follow the treasury workflow:")
    guide = pd.DataFrame({"tab": TAB_NAMES[1:], "question it answers": [
        "How much cash do we have, and are we above our minimum buffers?",
        "Where is the cash - which bank, which currency, at which exchange rate?",
        "Which companies, accounts, bank transactions, invoices and bills sit behind the numbers?",
        "Will we stay above our buffers over the next 13 weeks? What if customers pay late, or under stress?",
        "Which receipts and payments drive the forecast, and why did it change since the last run?",
        "Which data problems were found, why, and what was decided?",
        "How accurate were past forecasts, and why were they off?",
        "Who did what, can a forecast be reproduced, and how do I export results?"]})
    st.dataframe(guide, hide_index=True, column_config={"tab": st.column_config.Column("Tab"), "question it answers": st.column_config.Column("The question it answers", width="large")})

    st.subheader("This dataset at a glance")
    cols = st.columns(5)
    for col, (item, n) in zip(cols, [("Companies", len(ds["legal_entity"])), ("Bank accounts", len(ds["bank_account"])), ("Currencies", len(ds["currency"])),
                                     ("Ledger entries", len(ds["ledger_entry"])), ("Forecast items", len(ds["cash_flow_forecast"]))]):
        col.metric(item, f"{n:,}")
    scale = G.dataset_scale(b)
    st.caption("The brief asks for 30 entities, 150 accounts, 100,000 ledger entries, 20,000 forecast items and 5 currencies. "
               "The small *starter* profile and the full profile come from the same generator.")
    static_table(scale)

    st.subheader("Does it meet the brief? The four acceptance criteria")
    for _, r in G.acceptance_summary(b).iterrows():
        with st.container(border=True):
            st.markdown(f"**{STATUS_ICON.get(r['status_text'], '⚪')} {r['criterion']}** - {r['status_text']}")
            st.write(r["what_it_means"])
            st.caption(f"Evidence: {r['proof']}. See: {r['where']}.")

    st.subheader("The five edge cases the brief requires")
    st.caption("Each problem was injected on purpose into otherwise clean data, so it can be detected and scored. Detection never reads the answer key.")
    static_table(G.edge_case_summary(b), labels={"edge_case": "Edge case", "found": "Found"})

    st.subheader("Who does what")
    st.caption("Four kinds of people use the system; actions are checked against the role and every attempt - allowed or refused - is recorded.")
    static_table(G.actors_table(b))

    with st.expander("Glossary: the words used in this dashboard"):
        for term, meaning in T.GLOSSARY.items():
            st.markdown(f"**{term}** - {meaning}")
    st.caption("Everything here is synthetic and read-only: no real company or person appears, and nothing you click changes the data.")


def tab_overview(b: D.Bundle, on, entity) -> None:
    st.markdown(f"{ACTUAL} How much cash the group actually holds, in {b.reporting}, as of the date chosen in the sidebar.")
    overview = D.cash_overview(b, on)
    if (overview["buffer_status"] == "INCOMPLETE FX").any():
        st.warning("On this date some balances could not be converted because an exchange rate is missing. Those entities' totals leave the unconverted "
                   "balance out and are marked INCOMPLETE.")
    g = D.group_summary(overview)
    cols = st.columns(5)
    cols[0].metric(f"Total cash ({b.reporting})", usd(g["total_usd"]), help="Every bank account, converted at the day's exchange rate")
    cols[1].metric("Available", usd(g["available_usd"]), help="Total minus restricted accounts")
    cols[2].metric("Restricted", usd(g["restricted_usd"]), help="Held in restricted accounts and not usable")
    cols[3].metric("Headroom over buffers", usd(g["headroom_usd"]), help="Available cash minus the sum of the entities' minimum buffers")
    cols[4].metric("Entities below buffer", g["entities_below_buffer"], help=f"out of {g['entities']} entities")
    view = overview if not entity else overview[overview["entity_id"] == entity]
    table(view.drop(columns=["size_tier"]))
    hist = D.cash_history(b, entity)
    st.subheader("Actual cash over time" + (f" - {b.entity_names[entity]}" if entity else " - whole group"))
    chart(C.line_chart(hist.rename(columns={"total_usd": "Total cash", "available_usd": "Available cash", "min_buffer_usd": "Minimum buffer"}),
                       "position_date", ["Total cash", "Available cash", "Minimum buffer"], f"Cash ({b.reporting})"))
    if hist["incomplete"].any():
        st.caption(f"{int(hist['incomplete'].sum())} day(s) are INCOMPLETE (a balance could not be converted); the dips on those days are missing data, not cash leaving.")
    how_to_read("Each row is one company. **Available** = total cash minus restricted accounts; **Headroom** = available cash minus the company's minimum buffer.",
                "A negative headroom (shown as BELOW BUFFER) is a shortfall: the company holds less than it must keep.",
                "The chart shows the whole group (or the entity chosen in the sidebar). The flat line is the minimum buffer the available cash must stay above.")
    download("Cash overview", view, f"cash_overview_{pd.Timestamp(on):%Y%m%d}")


def tab_accounts(b: D.Bundle, on, entity) -> None:
    st.markdown(f"{ACTUAL} Every bank account with its balance in its own currency, the exchange rate used, and the {b.reporting} value (balance x rate).")
    acc = D.account_balances(b, on)
    if entity:
        acc = acc[acc["entity_id"] == entity]
    ccys = st.multiselect("Show currencies", sorted(acc["currency"].unique()), default=sorted(acc["currency"].unique()))
    acc = acc[acc["currency"].isin(ccys)]
    problems = acc[acc["fx_status"].isin(["FALLBACK", "MISSING"])]
    if len(problems):
        st.warning(f"{len(problems)} account(s) use a fallback or missing rate on this date (FALLBACK = the previous rate was used; MISSING = not converted).")
    table(acc.drop(columns=["entity_name", "fx_rate_id"]))
    st.subheader("Currency exposure")
    shock = st.slider("What if every non-USD currency moved by (%)?", -30, 30, -10, help="Simple arithmetic: value x move. Not a forecast.")
    expo = D.currency_exposure(b, on, shock)
    left, right = st.columns([3, 2])
    with left:
        chart(C.simple_bar(expo, "currency", "usd_value", "Currency", f"Value ({b.reporting})"))
    right.caption("The bars show how much of the group's cash sits in each currency, in USD. The table also shows what the move above would do to the USD value.")
    table(expo.assign(share_of_total=expo["share_of_total"] * 100).rename(columns={"usd_impact_of_shock": "usd_impact_of_move"}), pct=("share_of_total",))
    st.caption("Cash by entity and currency (USD value)")
    table(D.exposure_matrix(b, on))
    st.subheader("Exchange rates")
    hist = D.fx_history(b)
    pick = st.selectbox("Currency", [c for c in hist.columns if c != "rate_date"])
    chart(alt.Chart(hist[["rate_date", pick]].dropna(), width="container").mark_line().encode(
        x=alt.X("rate_date:T", title="Date", axis=alt.Axis(format="%d %b %Y", labelAngle=0, tickCount=6)),
        y=alt.Y(f"{pick}:Q", scale=alt.Scale(zero=False), title=f"USD per 1 {pick}"),
        tooltip=[alt.Tooltip("rate_date:T", title="Date", format="%a %d %b %Y"), alt.Tooltip(f"{pick}:Q", title=f"USD per 1 {pick}", format=".4f")]))
    gaps = D.fx_gaps(b)
    mine = gaps[gaps["currency"] == pick]
    st.caption(f"{len(gaps)} business-day rates are missing in this dataset in total; {len(mine)} for {pick}. Each shows the decision the rules apply "
               "(use the previous rate for up to 3 missing days, otherwise block the conversion).")
    table(mine)
    how_to_read("The rate is how many USD one unit of the currency buys, so a higher line means the currency got stronger.",
                "FALLBACK means the previous day's rate was used because a fixing was missing; MISSING means no usable rate, so the USD value is left empty - never guessed.")


def tab_entities(b: D.Bundle, on, entity) -> None:
    st.markdown(f"{ACTUAL} The master data and the transactions behind the numbers: companies, bank accounts, bank transactions (the ledger), customer invoices and supplier bills.")
    sections = ["Companies & bank accounts", "Bank transactions (ledger)", "Customer invoices & supplier bills"]
    wanted = st.query_params.get("section")                  # deep link: ?tab=Entities %26 transactions&section=Bank transactions (ledger)
    section = st.radio("Show", sections, index=sections.index(wanted) if wanted in sections else 0, horizontal=True)
    if section == "Companies & bank accounts":
        st.write("One holding company owns the operating companies. Each company holds bank accounts in one or more currencies; accounts can be opened, "
                 "frozen by compliance, unfrozen and closed, and that history is kept.")
        table(X.entity_master(b))
        accounts = X.account_master(b, entity)
        st.subheader("Bank accounts" + (f" - {b.entity_names[entity]}" if entity else ""))
        table(accounts)
        pick = st.selectbox("Show the history of one account", accounts["account_id"].tolist())
        table(X.account_events(b, pick))
    elif section == "Bank transactions (ledger)":
        accounts = X.account_master(b, entity)
        options = accounts["account_id"].tolist()
        info = accounts.set_index("account_id")
        default = next((i for i, a in enumerate(options) if info.at[a, "account_type"] == "OPERATING"), 0)
        account = st.selectbox("Bank account", options, index=default, format_func=lambda a: f"{a} · {info.at[a, 'currency']} · {info.at[a, 'account_type'].lower()}")
        last = pd.Timestamp(on)
        picked = st.date_input("Date range", value=(last - pd.Timedelta(days=30), last), min_value=b.ds["ledger_entry"]["posting_date"].min(), max_value=last)
        start, end = (picked[0], picked[-1]) if isinstance(picked, (tuple, list)) and picked else (last - pd.Timedelta(days=30), last)
        types = st.multiselect("Type of entry", sorted(b.ds["ledger_entry"]["entry_type"].unique()), format_func=lambda v: T.plain_value("entry_type", v))
        view = X.ledger_view(b, [account], start, end, types)
        ccy = info.at[account, "currency"]
        cols = st.columns(3)
        cols[0].metric("Entries", f"{len(view):,}")
        cols[1].metric(f"Money in ({ccy})", f"{view['money_in'].sum():,.2f}")
        cols[2].metric(f"Money out ({ccy})", f"{view['money_out'].sum():,.2f}")
        table(X.ledger_totals(view), labels={"entries": "Entries"})
        table(view.drop(columns=["currency"]).head(2000))
        if len(view) > 2000:
            st.caption(f"Showing the first 2,000 of {len(view):,} entries; download for all of them.")
        chk = X.ledger_account_check(b, account, end)
        st.subheader("Check: do the transactions add up to the balance?")
        c = st.columns(4)
        c[0].metric(f"Opening balance ({ccy})", f"{chk['opening']:,.2f}", help=f"As at {chk['opening_balance_date']:%Y-%m-%d}")
        c[1].metric("+ Money in", f"{chk['inflows']:,.2f}")
        c[2].metric("- Money out", f"{chk['outflows']:,.2f}")
        c[3].metric("= Closing balance", f"{chk['closing_calculated']:,.2f}")
        (st.success if chk["matches"] else st.error)(
            f"Opening balance + all {chk['entries']:,} entries up to {pd.Timestamp(end):%Y-%m-%d} = {chk['closing_calculated']:,.2f}; the stored daily balance is "
            f"{chk['closing_recorded']:,.2f}. " + ("They agree." if chk["matches"] else "They do NOT agree."))
        download("Ledger entries", view, f"ledger_{account}")
    else:
        r, p = X.receivable_list(b), X.payable_list(b)
        if entity:
            r, p = r[r["entity_id"] == entity], p[p["entity_id"] == entity]
        cols = st.columns(4)
        cols[0].metric("Customer invoices", f"{len(r):,}")
        cols[1].metric("Unpaid invoices", f"{int(r['status'].isin(X.OPEN_STATUSES).sum()):,}", help="Open, partly paid or overdue")
        cols[2].metric("Supplier bills", f"{len(p):,}")
        cols[3].metric("Large one-off payments", f"{int(p['is_one_off'].sum()):,}", help="Acquisition, capex, tax, debt and legal settlements")
        st.subheader("Delayed receivables: how late do customers pay?")
        st.caption("Payment behaviour follows the customer's risk tier (A best, D worst). This is the documented rule behind the delayed-receipt scenario.")
        late = X.lateness_by_tier(b)
        left, right = st.columns([2, 3])
        with left:
            chart(C.simple_bar(late, "risk_tier", "median_days_late", "Customer risk tier (A best, D worst)", "Typical days late", fmt=",.1f"))
        with right:
            table(late.assign(share_paid_over_7_days_late=late["share_paid_over_7_days_late"] * 100), pct=("share_paid_over_7_days_late",))
        st.subheader("Customer invoices (receivables)")
        status = st.multiselect("Invoice status", sorted(r["status"].unique()), format_func=lambda v: T.plain_value("status", v))
        table((r if not status else r[r["status"].isin(status)]).head(1000))
        st.subheader("Supplier bills (payables)")
        table(p.head(1000))
        st.subheader("Large one-off payments")
        table(X.one_off_payments(b) if not entity else X.one_off_payments(b).query("entity_id == @entity"))
        download("Invoices", r, "receivables")


def tab_forecast(b: D.Bundle, run_id: str, scenario: str, entity) -> None:
    ds = b.ds
    run_header(ds, run_id)
    series = D.forecast_series(ds, run_id, scenario, entity)
    cur = D.scenario_curves(ds, run_id, entity)
    label = b.entity_names[entity] if entity else "whole group (buffers added up)"
    st.subheader(f"Projected available cash, day by day - {sname(scenario)} - {label}")
    chart(C.line_chart(series.rename(columns={"closing_available_usd": "Projected available cash", "min_buffer_usd": "Minimum buffer"}),
                       "position_date", ["Projected available cash", "Minimum buffer"], f"Cash ({b.reporting})"))
    below = int((series["headroom_usd"] < 0).sum())
    worst = int(series["entities_below_buffer"].max())
    if below:
        st.error(f"{below} of {len(series)} projected days are below the minimum buffer.")
    elif worst:
        st.warning(f"The {'group total' if not entity else 'entity'} stays above {'the buffers added up' if not entity else 'its buffer'}, but up to {worst} "
                   f"entit{'y falls' if worst == 1 else 'ies fall'} below {'its' if worst == 1 else 'their'} own buffer (listed below). A group total can hide an entity shortfall.")
    else:
        st.success("No projected day is below the minimum buffer.")
    st.subheader("The 13 weeks week by week")
    table(D.weekly_view(series))
    st.subheader(f"Base, delayed-receipt and stress compared {SCENARIO}")
    curves = cur.rename(columns={**SHOW["scenarios"], "minimum buffer": "Minimum buffer"})
    chart(C.line_chart(curves, "position_date", [c for c in curves.columns if c != "position_date"], f"Available cash ({b.reporting})"))
    table(D.scenario_comparison(ds, run_id))
    st.caption("The three scenarios differ only by the documented assumptions below, applied one after another to the same data. Each assumption's effect is "
               "measured, and the effects add up exactly to the difference from the base case.")
    assumptions = D.assumption_table(ds, run_id)
    if scenario in set(assumptions["scenario_id"]):
        table(assumptions[assumptions["scenario_id"] == scenario])
    else:
        st.caption(f"{sname(scenario)} has no assumptions: it uses the latest known dates and amounts with exchange rates held at the cutoff rate.")
    st.subheader(f"Companies that fall below their buffer - {sname(scenario)}")
    breaches = D.entity_breaches(ds, run_id, scenario)
    table(breaches)
    if entity and not breaches[breaches["entity_id"] == entity].empty:
        first = pd.Timestamp(breaches.loc[breaches["entity_id"] == entity, "first_breach"].iloc[0])
        with st.expander(f"Why does {b.entity_names[entity]} fall below its buffer on {first:%Y-%m-%d}?", expanded=True):
            items = get_items(str(b.path), D.dataset_signature(b.path), run_id, scenario)
            window = items[(items["entity_id"] == entity) & items["in_horizon"] & (items["date"] <= first)]
            st.write(f"It starts with {usd(series['opening_usd'].iloc[0])} of available cash; the receipts and payments up to that day net to "
                     f"{usd(window['signed_usd'].sum())}. The biggest ones:")
            table(window.reindex(window["usd"].sort_values(ascending=False).index).head(10)[
                ["cf_id", "direction", "flow_category", "counterparty_id", "date", "shifted_days", "usd"]])
    how_to_read("The projection starts from the latest bank balances and adds each expected receipt and subtracts each expected payment on its date.",
                "**Delayed receipt** pushes customer payments later by their risk tier; **Stress** adds collection losses, earlier supplier payments, weaker operating receipts and a stronger USD.",
                "A company is *below buffer* when its projected available cash is lower than the minimum it must keep. The **funding gap** adds up the largest shortfalls.")
    download("Daily projection", series, f"forecast_{run_id}_{scenario}")


def tab_drivers(b: D.Bundle, run_id: str, scenario: str, entity) -> None:
    ds = b.ds
    run_header(ds, run_id)
    items = get_items(str(b.path), D.dataset_signature(b.path), run_id, scenario)
    st.subheader(f"What drives cash over the 13 weeks - {sname(scenario)}")
    drivers = D.driver_summary(items, entity)
    if len(drivers):
        chart(C.bar_chart(drivers.rename(columns=T.FLOW_LABEL), "week_no", [T.FLOW_LABEL.get(c, c) for c in drivers.columns if c != "week_no"],
                          f"Net cash ({b.reporting})", "Week", x_label="Week"))
    st.caption("Net cash per week by type of flow (receipts above the line, payments below). Amounts are in USD at the scenario's exchange rates.")
    c1, c2, c3 = st.columns(3)
    direction = c1.selectbox("Direction", ["All", "INFLOW", "OUTFLOW"], format_func=lambda x: {"All": "All", "INFLOW": "Receipts (money in)", "OUTFLOW": "Payments (money out)"}[x])
    moved = c2.checkbox("Only items this scenario moved in time", value=False)
    cats = c3.multiselect("Type of flow", sorted(items["flow_category"].unique()), format_func=lambda x: T.FLOW_LABEL.get(x, x))
    view = items[items["in_horizon"]]
    if entity:
        view = view[view["entity_id"] == entity]
    if direction != "All":
        view = view[view["direction"] == direction]
    if moved:
        view = view[view["shifted_days"].fillna(0) != 0]
    if cats:
        view = view[view["flow_category"].isin(cats)]
    st.write(f"{len(view):,} items. A delayed receipt keeps its cash: it simply lands on the later date (and drops out of the window if it moves past 13 weeks).")
    shown = view.sort_values(["date", "cf_id"]).drop(columns=["entity_name", "live", "in_horizon", "week_no"]).head(1000)
    shown = shown.assign(treatment=shown["treatment"].map(lambda t: T.TREATMENT_TEXT.get(t, t)))
    table(shown)
    download("Cash-flow items", view, f"items_{run_id}_{scenario}")

    st.subheader("Why did the forecast change?")
    runs = D.run_catalog(ds)
    ids = runs["run_id"].tolist()
    pos = ids.index(run_id)
    default = ids[pos - 1] if pos > 0 else ids[pos]
    other = st.selectbox("Compare the selected run with an earlier one", ids, index=ids.index(default), format_func=lambda r: runs.set_index("run_id").at[r, "label"])
    if other == run_id:
        st.info("Pick a different run to compare.")
        return
    diff = get_run_diff(str(b.path), D.dataset_signature(b.path), other, run_id)
    s = diff["summary"]
    cols = st.columns(4)
    cols[0].metric("Cash at the start", usd(s["opening_available_b_usd"]), usd(s["opening_available_b_usd"] - s["opening_available_a_usd"]), help="Change vs the earlier run")
    cols[1].metric("Lowest projected cash (base)", usd(s["lowest_available_b_usd"]), usd(s["lowest_available_b_usd"] - s["lowest_available_a_usd"]))
    cols[2].metric("Items added / removed", f"{s['items_added']} / {s['items_removed']}")
    cols[3].metric("Items changed", s["items_changed"])
    st.caption(f"{other} → {run_id}. The starting cash moves with new bank statements and exchange rates; items change through recorded events (payments, "
               "delays, holds), newly known items and items entering or leaving the 13-week window.")
    kinds = ["All"] + sorted(diff["items"]["change"].unique())
    kind = st.selectbox("Type of change", kinds)
    items_diff = diff["items"] if kind == "All" else diff["items"][diff["items"]["change"] == kind]
    if entity:
        items_diff = items_diff[items_diff["entity_id"] == entity]
    table(items_diff.drop(columns=["change_type", "reason"]).head(200))
    st.caption("Exchange rates used by the two runs")
    table(diff["fx"], labels={"currency": "Currency"})
    how_to_read("The chart adds up each week's receipts and payments by type; the table lists the individual items, with the **date shifted by the scenario** if any.",
                "**How it was handled** says whether a run used an item as recorded, moved an overdue one, dropped a duplicate or converted a currency.",
                "The comparison explains *why* the forecast differs from an earlier version: which items were added, paid, delayed or removed, and how rates moved.")


def tab_exceptions(b: D.Bundle) -> None:
    st.markdown(f"{ACTUAL} Problems CashPilot's rules found in the data and in the forecasts, each with the rule, the decision taken and the evidence. The detectors never read the ground truth.")
    exc = D.exceptions_table(b)
    names = {k: T.EXCEPTION_NAME.get(k, k) for k in exc["exception_type"].unique()}
    c1, c2, c3 = st.columns(3)
    types = c1.multiselect("Problem", sorted(names), format_func=lambda x: names[x])
    sev = c2.multiselect("Severity", ["CRITICAL", "HIGH", "MEDIUM", "LOW"], format_func=str.capitalize)
    status = c3.multiselect("Status", sorted(exc["status_at_end"].unique()), format_func=str.capitalize)
    view = exc
    if types:
        view = view[view["exception_type"].isin(types)]
    if sev:
        view = view[view["severity"].isin(sev)]
    if status:
        view = view[view["status_at_end"].isin(status)]
    st.write(f"{len(view)} of {len(exc)} exceptions")
    shown = view.assign(exception_type=view["exception_type"].map(names)).drop(columns=["details", "entity_name", "category", "record_table"])
    table(shown, labels={"exception_type": "Problem"})
    download("Exceptions", view, "exceptions")
    if view.empty:
        return
    by_id = view.set_index("exception_id")
    pick = st.selectbox("Trace an exception", view["exception_id"].tolist(),
                        format_func=lambda i: f"{i} · {names[by_id.at[i, 'exception_type']]} · {by_id.at[i, 'record_id']}")
    t = D.exception_trace(b, pick)
    e = t["exception"]
    st.markdown(f"### {names[e['exception_type']]} · {e['severity'].lower()} severity · {e['status_at_end'].lower()}")
    st.write(f"**Why it was flagged:** {e['details']}")
    st.write(f"**Rule {e['rule_id']}:** {t['rule_text']}")
    st.write(f"**Decision - {T.plain_value('decision', e['decision'])}:** {t['decision_text']}")
    ids = {k: e[k] for k in ("record_table", "record_id", "related_record_id", "entity_id", "account_id", "run_id") if pd.notna(e[k])}
    st.write("**Records involved:** " + " · ".join(f"{T.LABELS.get(k, k)}: {T.plain_value(k, v) if k == 'record_table' else v}" for k, v in ids.items()))
    st.write("**What happened next** (history is append-only)")
    table(t["events"])
    for title, frame in t["evidence"]:
        st.write(f"**{title}**")
        table(frame)
    st.subheader("Reconciliation: bank statements vs the ledger")
    rec = D.reconciliation_overview(b)
    cols = st.columns(4)
    cols[0].metric("Bank statement days", f"{rec['statements']:,}")
    cols[1].metric("Breaks raised", rec["breaks"], help=f"{rec['breaks_high']} above the materiality threshold")
    cols[2].metric("Account-days with an open difference", f"{rec['account_days_with_open_difference']:,}")
    cols[3].metric("Accounts affected", len(rec["accounts"]))
    table(rec["accounts"])
    st.caption("After a break, bank and book balances stay apart until the item is booked; the difference is kept in the daily positions as bank-minus-book.")
    how_to_read("**Severity** says how serious the rule judges it; **status** shows where it is in the workflow (raised, assigned, escalated, resolved or waived).",
                "The evidence shows the records behind the problem - for example the bank movement next to the booked movement, or the duplicate beside its original.")


def tab_accuracy(b: D.Bundle, scenario: str, entity) -> None:
    ds = b.ds
    st.markdown(f"{EVAL} How each forecast version compared with what actually happened. A week is compared only once it has fully passed.")
    runs = D.run_catalog(ds).set_index("run_id")
    ids = D.runs_with_actuals(ds)
    if not ids:
        st.info("No forecast has a fully elapsed week yet.")
        return
    run_id = st.selectbox("Forecast version to evaluate (past versions only)", ids, index=ids.index(D.default_accuracy_run(ds)),
                          format_func=lambda r: runs.at[r, "label"],
                          help="The live run looks forward, so it has nothing to compare yet. Pick any past version.")
    sc = scenario if scenario in D.run_scenarios(ds, run_id) else D.run_scenarios(ds, run_id)[0]
    run_header(ds, run_id)
    fva = D.forecast_vs_actual(ds, run_id, sc, entity)
    st.subheader(f"Week by week: forecast vs actual net cash - {sname(sc)}")
    table(fva)
    drivers = [c for c in fva.columns if c.endswith("_usd") and c not in ("forecast_net_usd", "actual_net_usd", "variance_usd", "residual_usd")]
    chart(C.bar_chart(fva[["week_no", *drivers]].rename(columns={d: T.LABELS[d].replace(" (USD)", "") for d in drivers}), "week_no",
                      [T.LABELS[d].replace(" (USD)", "") for d in drivers], f"Actual minus forecast ({b.reporting})", "Week", x_label="Week"))
    st.caption(f"The drivers add up exactly to actual minus forecast; unexplained remainder: {fva['residual_usd'].abs().sum():,.2f}.")
    c1, c2 = st.columns(2)
    week = c1.selectbox("Drill into week", fva["week_no"].tolist())
    ents = [entity] if entity else sorted(ds["forecast_vs_actual"].query("run_id == @run_id")["entity_id"].unique())
    who = c2.selectbox("Company", ents, format_func=lambda x: f"{x} · {b.entity_names[x]}")
    br = variance_breakdown(ds, run_id, who, int(week), scenario_prefix=sc, top=5)
    if br:
        st.write(f"Forecast {br['forecast_usd'] / 100:,.2f} · actual {br['actual_usd'] / 100:,.2f} · difference **{br['variance_usd'] / 100:,.2f}** (unexplained {br['residual_usd'] / 100:,.2f})")
        if not br["drivers"]:
            st.caption("Item-level detail is stored for the base scenario only; the weekly totals above exist for every scenario.")
        for d in br["drivers"]:
            with st.expander(f"{T.DRIVER_LABEL[d['driver']]} · {d['total_usd'] / 100:,.2f} · {d['records']} record(s)"):
                st.caption(T.DRIVER_TEXT[d["driver"]])
                table(pd.DataFrame(d["top"]).assign(amount_usd=lambda x: x["amount_usd"] / 100.0), labels={"cf_id": "Forecast item", "ledger_entry_id": "Bank posting"})
    download("Forecast vs actual", fva, f"fva_{run_id}_{sc}")

    ev = get_evaluation(str(b.path), D.dataset_signature(b.path))
    st.subheader("How accurate are the approved forecasts overall?")
    fa = ev["forecast_accuracy"]["approved_versions"]
    st.caption(f"Across {fa['runs']} approved forecast versions. Errors are shown as percentages; lower is better.")
    flows = pd.DataFrame(fa["by_horizon"]).T.reset_index().rename(columns={"index": "horizon"})
    flows = flows.assign(wape=flows["wape"] * 100, bias=flows["bias"] * 100)
    balance = pd.DataFrame(ev["balance_accuracy"]).T.reset_index().rename(columns={"index": "horizon"})
    balance = balance.assign(mape=balance["mape"].astype(float) * 100, bias=balance["bias"].astype(float) * 100)
    left, right = st.columns(2)
    with left:
        st.write("**Weekly net cash flow per company** (hard: small differences of big numbers)")
        table(flows, labels={"horizon": "How far ahead", "wape": "Typical error (WAPE)", "bias": "Bias", "entity_weeks": "Company-weeks"}, pct=("wape", "bias"))
    with right:
        st.write("**Group cash balance** at each week's end")
        table(balance, labels={"horizon": "How far ahead", "mape": "Typical error (MAPE)", "bias": "Bias", "observations": "Weeks compared",
                               "excluded_incomplete_fx": "Skipped (missing FX)"}, pct=("mape", "bias"))
    st.subheader("What explains the differences?")
    shares = ev["variance_drivers"]["share_of_absolute_variance"]
    net = ev["variance_drivers"]["net_by_driver_usd"]
    expl = pd.DataFrame({"driver": [T.DRIVER_LABEL[k.upper()] for k in shares], "share": [v * 100 for v in shares.values()],
                         "net_usd": [net[k] for k in shares], "meaning": [T.DRIVER_TEXT[k.upper()] for k in shares]}).sort_values("share", ascending=False)
    chart(C.simple_bar(expl, "driver", "share", "What explains it", "Share of the total difference (%)", fmt=",.1f", sort="-y"))
    table(expl, labels={"driver": "Driver", "share": "Share of the difference", "net_usd": "Net effect (USD)", "meaning": "What it means"}, pct=("share",))
    with st.expander(f"Reviewer view {TRUTH} - how well were the planted problems detected?"):
        st.caption("The ground truth is the answer key of deliberately injected problems. It is kept apart from the data and read only here, after detection, to score it.")
        det = ev.get("detection")
        if det:
            table(pd.DataFrame(det["by_issue"]).assign(precision=lambda d: d["precision"] * 100, recall=lambda d: d["recall"] * 100, f1=lambda d: d["f1"] * 100,
                                                       decision_accuracy=lambda d: d["decision_accuracy"] * 100),
                  labels={"issue_type": "Problem", "labelled": "Planted", "detected": "Flagged", "tp": "Correct", "fp": "False alarms", "fn": "Missed",
                          "precision": "Precision", "recall": "Recall", "f1": "F1", "decision_accuracy": "Right decision"},
                  pct=("precision", "recall", "f1", "decision_accuracy"))
            table(pd.DataFrame(det["by_sub_type"]).assign(recall=lambda d: d["recall"] * 100), labels={"sub_type": "Variant", "recall": "Recall"}, pct=("recall",))
            st.write(f"Legitimate look-alikes planted as traps: {det['negative_controls']}; wrongly flagged: **{det['negative_controls_flagged']}**.")
        else:
            st.info("No ground truth in this dataset folder.")
    how_to_read("**Difference** = actual minus forecast net cash. The named drivers explain all of it, so the unexplained part is zero.",
                "Weekly net flows look poor (typical error above 50%) because they are small differences of large gross flows; the group cash balance, which treasury decisions depend on, is forecast far more closely.",
                "The biggest driver is usually business that did not exist when the forecast was made (new invoices), followed by customers paying in a different week.")


def tab_audit(b: D.Bundle, run_id: str) -> None:
    ds = b.ds
    path = b.path
    run_header(ds, run_id)
    trail = D.audit_trail(ds, run_id)
    r = trail["run"]
    st.write(f"Version {r['version']} of the forecast as of {r['cutoff_date']:%Y-%m-%d}, created by {SHOW['users'].get(r['created_by'], r['created_by'])}. Replaces: "
             f"{r['supersedes_run_id'] if pd.notna(r['supersedes_run_id']) else 'nothing (first version)'}.")
    st.caption("The two fingerprints below identify exactly which inputs were used and what was produced; recomputing them is how reproducibility is proven.")
    st.code(f"inputs   {r['input_hash']}\nresults  {r['result_hash']}", language="text")
    st.write("**Life of this forecast** (append-only: nothing is overwritten)")
    table(trail["events"])
    st.write("**Who tried to do what to it** (allowed and refused attempts)")
    table(trail["audit"], empty="No allowed or refused actions are recorded against this forecast version.")
    st.write("**Which forecast items were used, and how each was handled**")
    lineage = trail["lineage"].assign(meaning=lambda d: d["treatment"].map(lambda t: T.TREATMENT_TEXT.get(t, t)))
    table(lineage, labels={"treatment": "Handling", "meaning": "What it means"})
    if st.button("Verify reproducibility", help="Re-run this version from the data known at its cutoff and compare the fingerprints"):
        with st.spinner("Re-running…"):
            v = D.verify_reproducibility(b, run_id)
        if v["reproduced"]:
            st.success("Reproduced: re-running from the data known at the cutoff gives identical input and result fingerprints.")
        else:
            st.error("Not reproducible as-of its cutoff: this run used inputs recorded after its claimed knowledge cutoff (rule R-LEAK-001).")
        st.caption("Fingerprints of the original run and of the re-run")
        table(pd.DataFrame({"Fingerprint": ["Inputs", "Results"], "Stored": [v["stored_input_hash"], v["stored_result_hash"]],
                            "Re-run": [v["recomputed_input_hash"], v["recomputed_result_hash"]], "Identical": ["Yes" if v["input_hash_matches"] else "No", "Yes" if v["result_hash_matches"] else "No"]}))
    st.subheader("Dataset and validation")
    val = D.validation_overview(path)
    if val:
        cols = st.columns(4)
        cols[0].metric("Validation", val["overall"])
        cols[1].metric("Checks run", val["checks"])
        cols[2].metric("Passed / expected / failed", " / ".join(str(val["by_status"].get(k, 0)) for k in ("PASS", "EXPECTED", "FAIL")),
                       help="EXPECTED = the check found only deliberately planted problems")
        cols[3].metric("Problems in the clean data", val.get("baseline", {}).get("violations", "n/a"), help="Before any problem was planted")
    manifest_path = Path(path) / "manifest.json"
    if manifest_path.is_file():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        st.write(f"Profile **{m['profile']}**, seed **{m['seed']}**. Recreate exactly this dataset with:")
        st.code(m["command"], language="bash")
        st.caption(f"Provenance: {m['provenance']}")
    files = D.manifest_files(path)
    with st.expander(f"Files and checksums ({len(files)})"):
        table(files)
    st.subheader("Export")
    runs = D.run_catalog(ds)
    download("List of forecast runs", runs.drop(columns=["label"]), "forecast_runs")
    st.caption("Every table is also available in full as CSV, JSON and SQL in the dataset folder (`csv/`, `json/`, `sql/`).")
    how_to_read("A forecast is **reproducible** when re-running it from the data known at its cutoff gives the same fingerprints. A forecast that peeked at later data fails this test on purpose.",
                "The audit tables record every action, including refusals, so you can see who did what and when.")


# --------------------------------------------------------------------- main

def main() -> None:
    st.set_page_config(page_title="CashPilot", layout="wide", menu_items={"About": "CashPilot - multi-entity cash consolidation and 13-week liquidity forecasting on synthetic data. Read-only."})
    st.title("CashPilot")
    st.caption("Multi-entity cash consolidation and 13-week liquidity forecasting · synthetic data · read-only")

    default = os.environ.get("CASHPILOT_DATA", "data/starter")
    options = [str(p) for p in D.discover_datasets(Path.cwd())]
    if default not in options and Path(default, "generation_config.json").is_file():
        options.insert(0, default)
    if not options:
        st.error("No dataset found. Create one with `cashpilot all --profile starter` and restart.")
        st.stop()
    path = st.sidebar.selectbox("Dataset", options, index=options.index(default) if default in options else 0, format_func=T.dataset_name,
                                help="Which generated dataset to look at. The starter one is small and quick; the full one is the size the brief asks for.")
    b = get_bundle(path, D.dataset_signature(path))
    missing = [t for t in REQUIRED_TABLES if t not in b.ds.tables]
    if missing:
        st.error(f"This folder has not been processed yet (missing {', '.join(missing)}). Run `cashpilot all` or `cashpilot run --data {path}`.")
        st.stop()

    ds = b.ds
    users = ds["app_user"].set_index("user_id")["display_name"]
    SHOW["users"] = {u: f"{n} ({u})" for u, n in users.items()}
    SHOW["entities"] = dict(b.entity_names)
    sc = ds["liquidity_scenario"].set_index("scenario_id")
    SHOW["scenarios"] = {s: f"{r['scenario_name']} · v{r['version']}" for s, r in sc.iterrows()}
    st.sidebar.markdown(f"Reporting currency **{b.reporting}** · built from seed **{b.cfg.seed}** ({b.cfg.profile} profile)")
    names = {e: f"{e} · {n}" for e, n in b.entity_names.items()}
    entity = st.sidebar.selectbox("Company", [None, *names], format_func=lambda e: GROUP if e is None else names[e],
                                  help="Focus the tabs on one company, or look at the whole group. Tabs that list every company (for example Exceptions) always show all of them.")
    on = st.sidebar.date_input("Actuals as of", value=D.default_date(ds), min_value=ds["entity_cash_position"]["position_date"].min(),
                               max_value=ds["entity_cash_position"]["position_date"].max(), help="The day whose bank balances are shown. Used by: Cash overview, Accounts & currencies, and the ledger check.")
    runs = D.run_catalog(ds)
    labels = runs.set_index("run_id")["label"].to_dict()
    run_ids = runs["run_id"].tolist()[::-1]
    run_id = st.sidebar.selectbox("Forecast run", run_ids, index=run_ids.index(D.default_run(ds)), format_func=lambda r: labels[r],
                                  help="One 13-week projection made as of a date. Newer versions replace older ones; the live run is the current forecast. Used by: Forecast, Cash-flow drivers, Audit & exports.")
    scenario = st.sidebar.selectbox("Scenario", D.run_scenarios(ds, run_id), format_func=sname,
                                    help="Base = no assumptions; Delayed receipt = customers pay later; Stress = delays, losses, earlier supplier payments, stronger USD. Used by: Forecast, Cash-flow drivers, Actual vs forecast.")
    st.sidebar.caption(sc.at[scenario, "description"])
    val = D.validation_overview(path)
    if val:
        st.sidebar.markdown(f"Validation **{val['overall']}** · {val['checks']} checks")
    st.sidebar.caption("Actual data, forecast outputs, scenario assumptions and ground-truth evaluation are labelled separately throughout. New here? Open **Start here**.")

    wanted = st.query_params.get("tab")                    # deep link: ?tab=Forecast
    tabs = st.tabs(TAB_NAMES, default=wanted if wanted in TAB_NAMES else None)
    with tabs[0]:
        tab_start(b)
    with tabs[1]:
        tab_overview(b, on, entity)
    with tabs[2]:
        tab_accounts(b, on, entity)
    with tabs[3]:
        tab_entities(b, on, entity)
    with tabs[4]:
        tab_forecast(b, run_id, scenario, entity)
    with tabs[5]:
        tab_drivers(b, run_id, scenario, entity)
    with tabs[6]:
        tab_exceptions(b)
    with tabs[7]:
        tab_accuracy(b, scenario, entity)
    with tabs[8]:
        tab_audit(b, run_id)


main()
