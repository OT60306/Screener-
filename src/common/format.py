"""
Shared display formatting: numbers capped at 2 decimal places, and themed
replacements for st.json (which renders as an unstyled white box outside the
app's CSS control). Used across all 3 pages so number formatting and "readable
data block" styling stay consistent.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import streamlit as st


def fmt(value: Any, decimals: int = 2, suffix: str = "", none_text: str = "n/a") -> str:
    """Formats a number to at most `decimals` places. Never raises — passes
    through non-numeric values, falls back to none_text for None/NaN."""
    if value is None:
        return none_text
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if pd.isna(f):
        return none_text
    return f"{f:.{decimals}f}{suffix}"


def fmt_pct(value: Any, decimals: int = 2, none_text: str = "n/a") -> str:
    return fmt(value, decimals, "%", none_text)


def fmt_money(value: Any, decimals: int = 2, none_text: str = "n/a") -> str:
    if value is None:
        return none_text
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "-" if f < 0 else ""
    f = abs(f)
    for suffix, threshold in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if f >= threshold:
            return f"{sign}${f / threshold:.{decimals}f}{suffix}"
    return f"{sign}${f:.{decimals}f}"


def fmt_mixed(value: Any, decimals: int = 2, none_text: str = "n/a") -> str:
    """Formats a value that may be bool, number, or text — as pulled from a
    results dict like CANSLIM's (some fields are pass/fail, some are %
    figures). bool is checked before number since bool is an int subclass."""
    if value is None:
        return none_text
    if isinstance(value, bool):
        return "Pass" if value else "Fail"
    if isinstance(value, (int, float)):
        return fmt(value, decimals, none_text=none_text)
    return str(value)


def render_kv_rows(rows: list[tuple[str, str]]) -> None:
    """Renders {label: value} pairs as a readable, theme-matched list — a
    drop-in replacement for st.json's flat dict case."""
    html = ["<div class='kv-block'>"]
    for label, value in rows:
        html.append(
            f"<div class='kv-row'><span class='kv-label'>{label}</span>"
            f"<span class='kv-value'>{value}</span></div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_series_table(
    periods: list[str],
    series: dict[str, list],
    decimals: int = 2,
    suffix: str = "",
    formatters: Optional[dict[str, Any]] = None,
) -> None:
    """series: {row_label: [values by period, most-recent-first]}. Renders as
    a themed table instead of a raw JSON dict-of-lists. `formatters`: optional
    {row_label: callable(value) -> str} to override the default `fmt` for
    specific rows (e.g. money-scale FCF vs. percentage margins)."""
    formatters = formatters or {}
    data = {}
    for label, values in series.items():
        if not values:
            continue
        padded = list(values) + [None] * (len(periods) - len(values))
        row_fmt = formatters.get(label, lambda v: fmt(v, decimals, suffix))
        data[label] = [row_fmt(v) for v in padded[: len(periods)]]
    if not data:
        st.caption("No data available.")
        return
    df = pd.DataFrame(data, index=periods).T
    df.index.name = "Metric"
    st.dataframe(df, width="stretch")


def status_badge_html(status: Optional[bool], pass_text: str = "PASS", fail_text: str = "FAIL", na_text: str = "N/A") -> str:
    """Returns a colored <span> (not rendered itself) — for embedding a
    Pass/Fail badge inline with other text in a single st.markdown call,
    e.g. right in front of a section heading. Note: st.metric's `delta`
    param does NOT reliably color "Pass"/"Fail" text — Streamlit's automatic
    delta coloring only recognizes a leading "-" as negative, so arbitrary
    text like "Fail" renders with the same color as "Pass". Use this instead
    of delta text whenever the value is a status word, not a real delta.

    Uses the status-good/status-bad/status-na classes from theme.py rather
    than an inline color style: a class selector reliably beats the app-wide
    `span { color: ... !important }` rule on specificity, which a plain
    inline color is not guaranteed to do."""
    if status is True:
        return f"<span class='status-good' style='font-weight:800;'>{pass_text}</span>"
    if status is False:
        return f"<span class='status-bad' style='font-weight:800;'>{fail_text}</span>"
    return f"<span class='status-na' style='font-weight:800;'>{na_text}</span>"


def stage_header(text: str, status: Optional[bool]) -> None:
    """Renders a section heading with a Pass/Fail/N-A badge directly in
    front of it, on the same line."""
    st.markdown(f"{status_badge_html(status)} &nbsp; **{text}**", unsafe_allow_html=True)


def verdict_badge(text: str, kind: str = "neutral") -> None:
    """kind: 'good' (green) | 'bad' (red) | 'neutral' (yellow) — colored text
    badge, no emoji."""
    color = {"good": "#8FD19E", "bad": "#E38B8B", "neutral": "#E9C46A"}.get(kind, "#E9C46A")
    st.markdown(
        f"<div class='verdict-badge' style='border-color:{color};color:{color};'>{text}</div>",
        unsafe_allow_html=True,
    )
