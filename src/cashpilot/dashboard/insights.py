"""Input -> calculation -> result explanations built from the selected dataset's own numbers.

Nothing here computes new financial figures: every value is read from an existing engine result (positions, forecast series, scenario
items, forecast-vs-actual, account balances) and the explanation shows how those figures relate. Streamlit-free, so it is tested
against the engine (for example: opening cash + receipts - payments = the projected cash the forecast stored).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashpilot.dashboard import data as D
from cashpilot.dashboard import text as T

TOLERANCE = 0.01          # one cent: money is stored in minor units


def money(x: float, ccy: str = "", dp: int = 0) -> str:
    """36,033,425 USD (negative amounts keep their sign)."""
    return f"{x:,.{dp}f}" + (f" {ccy}" if ccy else "")


def _insight(title: str, inputs: list[tuple[str, str]], calculation: list[str], result: str, level: str = "info") -> dict:
    return {"title": title, "inputs": inputs, "calculation": calculation, "result": result, "level": level}


# ----------------------------------------------------------------------------------------------- cash overview

def liquidity_status(g: dict, reporting: str) -> dict:
    """A plain verdict on today's buffers. It uses only the documented rule: an entity is below buffer when its available cash is less than its minimum buffer."""
    n, total = g["entities_below_buffer"], g["entities"]
    if g.get("entities_incomplete_fx"):
        return {"level": "warning", "headline": "Cannot be fully assessed",
                "text": f"{g['entities_incomplete_fx']} of {total} companies have a balance that could not be converted because an exchange rate is missing, "
                        "so their totals are incomplete. They are flagged, never estimated."}
    if n:
        return {"level": "error", "headline": f"{n} of {total} companies are below their minimum buffer",
                "text": "These companies hold less available cash than they must keep. See the table below for the shortfall of each."}
    return {"level": "success", "headline": "Every company is above its minimum buffer",
            "text": f"All {total} companies hold more available cash than the minimum buffer they must keep. The group has {money(g['headroom_usd'], reporting)} "
                    "of headroom in total; the Forecast tab shows whether that holds over the next 13 weeks."}


def headroom_insight(g: dict, reporting: str) -> dict:
    """Total cash - restricted = available; available - minimum buffers = headroom (the figures on the cards)."""
    return _insight(
        "How headroom is worked out",
        [("Total cash", money(g["total_usd"], reporting)), ("Restricted cash (cannot be used)", money(g["restricted_usd"], reporting)),
         ("Minimum buffers of all companies", money(g["min_buffer_usd"], reporting))],
        [f"Available cash = {money(g['total_usd'])} - {money(g['restricted_usd'])} = {money(g['available_usd'])}",
         f"Headroom = {money(g['available_usd'])} - {money(g['min_buffer_usd'])} = {money(g['headroom_usd'])}"],
        f"Headroom over buffers: {money(g['headroom_usd'], reporting)}", "success" if g["headroom_usd"] >= 0 else "error")


# ----------------------------------------------------------------------------------------------- forecast

def forecast_headline(series: pd.DataFrame) -> dict:
    """The lowest point of a projection and how many days sit below the buffer (from the stored daily projection)."""
    low = series.loc[series["closing_available_usd"].idxmin()]
    return {"lowest_usd": float(low["closing_available_usd"]), "lowest_on": pd.Timestamp(low["position_date"]), "buffer_then_usd": float(low["min_buffer_usd"]),
            "days_below": int((series["headroom_usd"] < 0).sum()), "days": len(series), "max_entities_below": int(series["entities_below_buffer"].max())}


def breach_story(ds, items: pd.DataFrame, run_id: str, scenario_id: str, entity_id: str, first_breach, reporting: str) -> dict:
    """Why an entity first falls below its buffer: opening cash plus every receipt and payment due up to that day, from the scenario's own items."""
    series = D.forecast_series(ds, run_id, scenario_id, entity_id)
    day = pd.Timestamp(first_breach)
    on_day = series[series["position_date"] == day].iloc[0]
    window = items[(items["entity_id"] == entity_id) & items["in_horizon"] & (items["date"] <= day)]
    receipts = float(window.loc[window["signed_usd"] > 0, "signed_usd"].sum())
    payments = float(-window.loc[window["signed_usd"] < 0, "signed_usd"].sum())
    opening, projected, buffer = float(series["opening_usd"].iloc[0]), float(on_day["closing_available_usd"]), float(on_day["min_buffer_usd"])
    gap = projected - buffer
    biggest = window.reindex(window["signed_usd"].abs().sort_values(ascending=False).index).head(8)
    insight = _insight(
        f"Why {day:%Y-%m-%d} is the first day below the buffer",
        [("Available cash at the start of the forecast", money(opening, reporting)), (f"Receipts due up to {day:%Y-%m-%d}", money(receipts, reporting)),
         (f"Payments due up to {day:%Y-%m-%d}", money(payments, reporting)), ("Minimum buffer", money(buffer, reporting))],
        [f"Projected cash = {money(opening)} + {money(receipts)} - {money(payments)} = {money(opening + receipts - payments)}",
         f"Headroom = {money(projected)} - {money(buffer)} = {money(gap)}"],
        (f"Shortfall of {money(-gap, reporting)} on {day:%Y-%m-%d}" if gap < 0 else f"Headroom of {money(gap, reporting)} on {day:%Y-%m-%d}"),
        "error" if gap < 0 else "success")
    return {"insight": insight, "series": series, "biggest": biggest, "opening": opening, "receipts": receipts, "payments": payments, "projected": projected,
            "buffer": buffer, "gap": gap, "reconciles": abs(opening + receipts - payments - projected) <= TOLERANCE}


# ----------------------------------------------------------------------------------------------- cash-flow drivers

def cash_bridge(items: pd.DataFrame, series: pd.DataFrame, entity_id: str | None = None) -> pd.DataFrame:
    """Waterfall steps: opening available cash, the net of each type of flow over the horizon, closing available cash."""
    i = items[items["in_horizon"]]
    if entity_id:
        i = i[i["entity_id"] == entity_id]
    by_type = i.groupby("flow_category")["signed_usd"].sum()
    by_type = by_type[by_type.abs() > 0].sort_values(ascending=False)
    opening, closing = float(series["opening_usd"].iloc[0]), float(series["closing_available_usd"].iloc[-1])
    rows, level = [{"step": "Cash at the start", "code": "", "amount": opening, "start": 0.0, "end": opening, "kind": "Cash at start"}], opening
    for code, amount in by_type.items():
        rows.append({"step": T.FLOW_LABEL.get(code, code), "code": code, "amount": float(amount), "start": level, "end": level + float(amount),
                     "kind": "Increase" if amount > 0 else "Decrease"})
        level += float(amount)
    rows.append({"step": "Cash after 13 weeks", "code": "", "amount": closing, "start": 0.0, "end": closing, "kind": "Cash at end"})
    out = pd.DataFrame(rows)
    out.attrs["reconciles"] = abs(level - closing) <= TOLERANCE
    return out


def bridge_insight(bridge: pd.DataFrame, reporting: str) -> dict:
    steps = bridge[bridge["kind"].isin(["Increase", "Decrease"])]
    opening, closing = float(bridge["amount"].iloc[0]), float(bridge["amount"].iloc[-1])
    ins, outs = float(steps.loc[steps["amount"] > 0, "amount"].sum()), float(-steps.loc[steps["amount"] < 0, "amount"].sum())
    return _insight(
        "How cash moves over the 13 weeks",
        [("Available cash at the start", money(opening, reporting)), ("Net increases (receipts and other inflows)", money(ins, reporting)),
         ("Net decreases (payments and other outflows)", money(outs, reporting))],
        [f"Cash after 13 weeks = {money(opening)} + {money(ins)} - {money(outs)} = {money(opening + ins - outs)}"],
        f"Projected available cash after 13 weeks: {money(closing, reporting)} ({'+' if closing - opening >= 0 else '-'}{money(abs(closing - opening))})")


# ----------------------------------------------------------------------------------------------- accounts and currencies

def account_conversion(row: pd.Series, shock_pct: float, reporting: str) -> dict:
    """One account: balance in its own currency x rate = value in the reporting currency, and what an FX move would do to it."""
    ccy, local = row["currency"], float(row["local_balance"])
    if ccy == reporting:
        return _insight("How this balance is valued", [("Balance", money(local, ccy, 2)), ("Currency", f"{ccy} is the reporting currency")],
                        ["No conversion is needed."], f"Value: {money(local, reporting, 2)}. An FX move does not change it.")
    rate, usd = row["rate_usd_per_unit"], row["balance_usd"]
    if pd.isna(rate) or pd.isna(usd):
        return _insight("How this balance is valued", [("Balance", money(local, ccy, 2)), ("Exchange rate", "none usable on this date")],
                        ["There is no usable rate, so the balance is not converted (never guessed)."], "Value: not available", "warning")
    usd, rate = float(usd), float(rate)
    change = usd * shock_pct / 100.0
    stale = {"FALLBACK": " (the previous day's rate: today's was missing)", "OK": ""}.get(row["fx_status"], "")
    return _insight(
        "How this balance is valued",
        [("Balance in its own currency", money(local, ccy, 2)), (f"Rate on {pd.Timestamp(row['rate_date']):%Y-%m-%d}{stale}", f"{rate:,.4f} {reporting} per 1 {ccy}")],
        [f"Value = {money(local, '', 2)} x {rate:,.4f} = {money(usd, reporting, 2)}",
         f"If {ccy} moved {shock_pct:+.0f}%: the rate becomes {rate * (1 + shock_pct / 100):,.4f} and the value changes by {money(usd * shock_pct / 100, '', 2)}"],
        f"Value now: {money(usd, reporting, 2)}. After a {shock_pct:+.0f}% move: {money(usd + change, reporting, 2)}")


def fx_move_insight(expo: pd.DataFrame, shock_pct: float, reporting: str, applied_to: list[str]) -> dict:
    """The group-level effect of the FX move chosen on the page (plain arithmetic: value x move, labelled as such)."""
    outside = float(expo.loc[expo["currency"].isin(applied_to), "usd_value"].sum())
    effect = float(expo["usd_impact_of_shock"].sum())
    total = float(expo["usd_value"].sum())
    names = ", ".join(applied_to) if applied_to else "none"
    return _insight(
        "What an exchange-rate move would do",
        [("Cash held in the affected currencies", f"{money(outside, reporting)} ({names})"), ("Assumed move against " + reporting, f"{shock_pct:+.0f}%"),
         ("Group cash today", money(total, reporting))],
        [f"Effect = {money(outside)} x {shock_pct:+.0f}% = {money(effect)}", f"Group cash after the move = {money(total)} + ({money(effect)}) = {money(total + effect)}"],
        f"The move changes group cash by {money(effect, reporting)} ({(effect / total * 100 if total else 0):+.1f}%). This is plain arithmetic, not a forecast.",
        "warning" if effect < 0 else "info")


# ----------------------------------------------------------------------------------------------- actual vs forecast

OTHER_DRIVERS = ["new_after_cutoff_usd", "unforecasted_usd", "not_realized_usd", "run_rate_usd", "data_quality_usd", "residual_usd"]


def variance_insight(row: pd.Series, reporting: str) -> dict:
    """One week: actual - forecast = timing + amount + FX + everything else (the stored variance attribution, which sums exactly)."""
    other = float(sum(row[c] for c in OTHER_DRIVERS))
    forecast, actual, variance = float(row["forecast_net_usd"]), float(row["actual_net_usd"]), float(row["variance_usd"])
    timing, amount, fx = float(row["timing_usd"]), float(row["amount_usd"]), float(row["fx_usd"])
    return _insight(
        f"Week {int(row['week_no'])}: why actual differs from forecast",
        [("Forecast net cash", money(forecast, reporting)), ("Actual net cash", money(actual, reporting))],
        [f"Difference = {money(actual)} - ({money(forecast)}) = {money(variance)}",
         f"Explained by: timing {money(timing)} + amount {money(amount)} + FX {money(fx)} + all other {money(other)} = {money(timing + amount + fx + other)}"],
        f"Actual was {money(abs(variance), reporting)} {'above' if variance >= 0 else 'below'} the forecast; unexplained remainder: {money(float(row['residual_usd']), reporting, 2)}",
        "info")


def variance_totals(fva: pd.DataFrame) -> dict:
    """Timing, amount, FX and 'everything else' summed over the weeks shown (for the summary cards)."""
    other = float(fva[OTHER_DRIVERS].sum().sum())
    return {"variance": float(fva["variance_usd"].sum()), "timing": float(fva["timing_usd"].sum()), "amount": float(fva["amount_usd"].sum()),
            "fx": float(fva["fx_usd"].sum()), "other": other}


# ----------------------------------------------------------------------------------------------- exceptions

SEVERITY_ICON = {"CRITICAL": "🔴", "HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟡"}
STATUS_ICON = {"RESOLVED": "✅", "WAIVED": "☑️"}


def exception_list(exc: pd.DataFrame) -> pd.DataFrame:
    """The plain exception list: severity, problem, who it affects, which record, and where it stands (IDs and rules stay in the technical table)."""
    names = exc["exception_type"].map(lambda k: T.EXCEPTION_NAME.get(k, k))
    affected = exc["record_table"].map(lambda k: T.plain_value("record_table", k)) + ": " + exc["record_id"].astype(str)
    return pd.DataFrame({
        "Severity": [f"{SEVERITY_ICON.get(s, '⚪')} {s.capitalize()}" for s in exc["severity"]], "Problem": names.to_numpy(),
        "Company": exc["entity_name"].fillna("").to_numpy(), "Affected record": affected.to_numpy(),
        "Status": [f"{STATUS_ICON.get(s, '⏳')} {s.capitalize()}" for s in exc["status_at_end"]], "impact_usd": exc["impact_usd"].to_numpy()})
