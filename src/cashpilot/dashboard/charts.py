"""Charts for the dashboard, built so that nothing technical shows: titled axes, readable dates, formatted numbers in the
tooltip, and a legend. (Streamlit's own quick charts show column names such as ``position_date``, ``value`` and ``color`` on hover.)
Streamlit-free, so it is tested."""

from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd

AXIS_MONEY = "~s"                  # 40M, 2.5M, -300k
TOOLTIP_MONEY = ",.0f"             # 40,265,073
WIDTH = "container"
PALETTE = ["#1f77b4", "#7fb8e6", "#e07b39", "#2a9d8f", "#9b5de5", "#d6a000", "#e63946", "#8c6d5a"]
BUFFER_GREY = "#555555"             # the minimum buffer is a reference line, so it never takes a series colour


def _colour(series: list[str], dashed: tuple[str, ...]) -> alt.Color:
    others = [s for s in series if s not in dashed]
    domain = others + [s for s in series if s in dashed]
    return alt.Color("_series:N", title=None, legend=alt.Legend(orient="bottom"),
                     scale=alt.Scale(domain=domain, range=[PALETTE[i % len(PALETTE)] for i in range(len(others))] + [BUFFER_GREY] * (len(domain) - len(others))))


def _long(df: pd.DataFrame, x: str, columns: list[str]) -> pd.DataFrame:
    return df[[x, *columns]].melt(x, var_name="_series", value_name="_amount")


def line_chart(df: pd.DataFrame, x: str, columns: list[str], y_title: str, x_title: str = "Date", dashed: tuple[str, ...] = ("Minimum buffer",)) -> alt.Chart:
    """Several lines over time. ``columns`` are the (already friendly) column names to draw; ``dashed`` lines are drawn dashed (the buffer)."""
    long = _long(df, x, columns)
    dash = alt.condition(alt.FieldOneOfPredicate("_series", list(dashed)), alt.value([6, 4]), alt.value([1, 0]))
    return (alt.Chart(long, width=WIDTH).mark_line()
            .encode(x=alt.X(f"{x}:T", title=x_title, axis=alt.Axis(format="%d %b %Y", labelAngle=0, tickCount=6)),
                    y=alt.Y("_amount:Q", title=y_title, axis=alt.Axis(format=AXIS_MONEY)),
                    color=_colour(columns, dashed),
                    strokeDash=dash,
                    tooltip=[alt.Tooltip(f"{x}:T", title=x_title, format="%a %d %b %Y"), alt.Tooltip("_series:N", title="Line"),
                             alt.Tooltip("_amount:Q", title=y_title, format=TOOLTIP_MONEY)]))


def bar_chart(df: pd.DataFrame, x: str, columns: list[str], y_title: str, x_title: str, x_label: str = "") -> alt.Chart:
    """Stacked bars per category (for example per week), one colour per column. ``x_label`` prefixes the tooltip value, e.g. 'Week'."""
    long = _long(df, x, columns)
    long["_label"] = (x_label + " " if x_label else "") + long[x].astype(str)
    return (alt.Chart(long, width=WIDTH).mark_bar()
            .encode(x=alt.X(f"{x}:O", title=x_title, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("_amount:Q", title=y_title, axis=alt.Axis(format=AXIS_MONEY)),
                    color=alt.Color("_series:N", title=None, legend=alt.Legend(orient="bottom")),
                    tooltip=[alt.Tooltip("_label:N", title=x_title), alt.Tooltip("_series:N", title="Type"),
                             alt.Tooltip("_amount:Q", title=y_title, format=TOOLTIP_MONEY)]))


def simple_bar(df: pd.DataFrame, x: str, y: str, x_title: str, y_title: str, fmt: str = TOOLTIP_MONEY, sort: str | None = None) -> alt.Chart:
    """One bar per category. ``sort='-y'`` orders the bars from the largest down."""
    axis_fmt = AXIS_MONEY if fmt == TOOLTIP_MONEY else fmt
    return (alt.Chart(df, width=WIDTH).mark_bar()
            .encode(x=alt.X(f"{x}:N", title=x_title, sort=sort, axis=alt.Axis(labelAngle=0, labelLimit=160)),
                    y=alt.Y(f"{y}:Q", title=y_title, axis=alt.Axis(format=axis_fmt)),
                    tooltip=[alt.Tooltip(f"{x}:N", title=x_title), alt.Tooltip(f"{y}:Q", title=y_title, format=fmt)]))


RED, GREEN, BLUE, GREY = "#d62728", "#2a9d8f", "#1f77b4", "#8a8f98"


def shortfall_chart(df: pd.DataFrame, x: str, cash: str, buffer: str, y_title: str, x_title: str = "Date") -> alt.LayerChart:
    """Projected cash against the minimum buffer; the days where cash is below the buffer are shaded red between the two lines."""
    wide = df[[x, cash, buffer]].rename(columns={cash: "cash", buffer: "buffer"})
    gap = (alt.Chart(wide, width=WIDTH).mark_area(color=RED, opacity=0.3)
           .encode(x=alt.X(f"{x}:T"), y=alt.Y("buffer:Q"), y2="cash:Q").transform_filter("datum.cash < datum.buffer"))
    return alt.layer(gap, line_chart(df, x, [cash, buffer], y_title, x_title, dashed=(buffer,)))


def weekly_cash_chart(weeks: pd.DataFrame, y_title: str) -> alt.LayerChart:
    """One bar per forecast week: available cash at the week's end (red when a day in that week was below the buffer) and the buffer as a line."""
    w = weeks.assign(state=lambda d: np.where(d["days_below_buffer"] > 0, "Below the buffer on some days", "Above the buffer all week"),
                     label=lambda d: "Week " + d["week_no"].astype(str))
    bars = (alt.Chart(w, width=WIDTH).mark_bar()
            .encode(x=alt.X("week_no:O", title="Week", axis=alt.Axis(labelAngle=0)), y=alt.Y("closing_available_usd:Q", title=y_title, axis=alt.Axis(format=AXIS_MONEY)),
                    color=alt.Color("state:N", title=None, legend=alt.Legend(orient="bottom"),
                                    scale=alt.Scale(domain=["Above the buffer all week", "Below the buffer on some days"], range=[BLUE, RED])),
                    tooltip=[alt.Tooltip("label:N", title="Week"), alt.Tooltip("week_start:T", title="Starts", format="%d %b %Y"),
                             alt.Tooltip("closing_available_usd:Q", title="Available cash at week end", format=TOOLTIP_MONEY),
                             alt.Tooltip("lowest_available_usd:Q", title="Lowest during the week", format=TOOLTIP_MONEY),
                             alt.Tooltip("min_buffer_usd:Q", title="Minimum buffer", format=TOOLTIP_MONEY),
                             alt.Tooltip("days_below_buffer:Q", title="Days below the buffer")]))
    rule = (alt.Chart(w, width=WIDTH).mark_line(color=BUFFER_GREY, strokeDash=[6, 4], point=True)
            .encode(x=alt.X("week_no:O"), y=alt.Y("min_buffer_usd:Q"), tooltip=[alt.Tooltip("label:N", title="Week"), alt.Tooltip("min_buffer_usd:Q", title="Minimum buffer", format=TOOLTIP_MONEY)]))
    return alt.layer(bars, rule)


def _short(x: float, signed: bool) -> str:
    a = abs(x)
    body = f"{a / 1e6:.1f}M" if a >= 1e6 else (f"{a / 1e3:.0f}k" if a >= 1e3 else f"{a:.0f}")
    return (("+" if x >= 0 else "-") if signed else ("-" if x < 0 else "")) + body


def waterfall(steps: pd.DataFrame, y_title: str) -> alt.LayerChart:
    """Opening cash, then each type of flow as a floating bar (green up, red down), then closing cash. ``steps``: step, amount, start, end, kind."""
    steps = steps.assign(label=[_short(a, k in ("Increase", "Decrease")) for a, k in zip(steps["amount"], steps["kind"])])    # +22.6M for a change, 36.0M for a level
    order = steps["step"].tolist()
    colours = alt.Scale(domain=["Cash at start", "Increase", "Decrease", "Cash at end"], range=[BLUE, GREEN, RED, BLUE])
    base = alt.Chart(steps, width=WIDTH, height=360).encode(x=alt.X("step:N", sort=order, title=None, axis=alt.Axis(labelAngle=-30, labelLimit=190, labelOverlap=False)))
    bars = base.mark_bar().encode(
        y=alt.Y("start:Q", title=y_title, scale=alt.Scale(zero=False), axis=alt.Axis(format=AXIS_MONEY)), y2="end:Q",
        color=alt.Color("kind:N", title=None, scale=colours, legend=alt.Legend(orient="bottom")),
        tooltip=[alt.Tooltip("step:N", title="Step"), alt.Tooltip("amount:Q", title="Amount", format=",.0f"), alt.Tooltip("end:Q", title="Cash after this step", format=",.0f")])
    labels = base.mark_text(dy=-6, fontSize=11).encode(y="end:Q", text="label:N")
    return alt.layer(bars, labels)


def grouped_bar(df: pd.DataFrame, x: str, columns: list[str], y_title: str, x_title: str) -> alt.Chart:
    """Side-by-side bars per week, one per column (for example forecast next to actual)."""
    long = _long(df, x, columns)
    return (alt.Chart(long, width=WIDTH).mark_bar()
            .encode(x=alt.X(f"{x}:O", title=x_title, axis=alt.Axis(labelAngle=0)), xOffset=alt.XOffset("_series:N"),
                    y=alt.Y("_amount:Q", title=y_title, axis=alt.Axis(format=AXIS_MONEY)),
                    color=alt.Color("_series:N", title=None, legend=alt.Legend(orient="bottom"), scale=alt.Scale(domain=columns, range=[GREY, BLUE][:len(columns)])),
                    tooltip=[alt.Tooltip(f"{x}:O", title=x_title), alt.Tooltip("_series:N", title="Which"), alt.Tooltip("_amount:Q", title=y_title, format=TOOLTIP_MONEY)]))


def exposure_chart(expo: pd.DataFrame, y_title: str) -> alt.LayerChart:
    """Cash by currency in the reporting currency, with the value written on each bar. ``expo``: currency, usd_value, share (%), local_total."""
    base = alt.Chart(expo, width=WIDTH).encode(x=alt.X("currency:N", sort="-y", title="Currency", axis=alt.Axis(labelAngle=0)))
    bars = base.mark_bar(color=BLUE).encode(
        y=alt.Y("usd_value:Q", title=y_title, axis=alt.Axis(format=AXIS_MONEY)),
        tooltip=[alt.Tooltip("currency:N", title="Currency"), alt.Tooltip("local_total:Q", title="Balance in that currency", format=",.0f"),
                 alt.Tooltip("usd_value:Q", title=y_title, format=TOOLTIP_MONEY), alt.Tooltip("share:Q", title="Share of group cash (%)", format=".1f")])
    text = base.mark_text(dy=-6, fontSize=11).encode(y="usd_value:Q", text=alt.Text("usd_value:Q", format=",.2s"))
    return alt.layer(bars, text)
