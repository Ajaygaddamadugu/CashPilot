"""Charts for the dashboard, built so that nothing technical shows: titled axes, readable dates, formatted numbers in the
tooltip, and a legend. (Streamlit's own quick charts show column names such as ``position_date``, ``value`` and ``color`` on hover.)
Streamlit-free, so it is tested."""

from __future__ import annotations

import altair as alt
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
