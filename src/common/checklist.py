"""
Renders a {key: True|False|None} results dict (Trend Template, CANSLIM, ...)
as a readable list instead of raw st.json — colored status dot + label, no
emoji. One component so every page that shows this shape of data looks the
same.
"""
from __future__ import annotations

import streamlit as st

# Human-readable labels for the Minervini Trend Template's 8 checks
# (src/trading/trend_template.py CHECK_NAMES).
TREND_TEMPLATE_LABELS: dict[str, str] = {
    "price_above_150_200": "Price above SMA 150 and SMA 200",
    "sma150_above_sma200": "SMA 150 above SMA 200",
    "sma200_trending_up": "SMA 200 trending up (≥1 month)",
    "sma_stack_50_150_200": "SMA stack: 50 > 150 > 200",
    "price_above_50": "Price above SMA 50",
    "above_52wk_low_min_pct": "≥30% above 52-week low",
    "within_52wk_high_max_pct": "Within 25% of 52-week high",
    "rs_rating_min": "RS Rating ≥ 70",
}


def _status_class(value) -> str:
    if value is True:
        return "pass"
    if value is False:
        return "fail"
    return "na"


def render_checklist(results: dict, labels: dict | None = None, pending_keys: set | None = None) -> None:
    """results: {key: True|False|None}. labels: optional {key: display text},
    falls back to a title-cased key. pending_keys: keys to render as "pending"
    (waiting on external data) instead of "n/a" (structurally not applicable)."""
    labels = labels or {}
    pending_keys = pending_keys or set()
    lines = []
    for key, value in results.items():
        label = labels.get(key, key.replace("_", " ").title())
        status = "pending" if value is None and key in pending_keys else _status_class(value)
        lines.append(
            f"<div class='status-line'><span class='status-dot {status}'></span>"
            f"<span>{label}</span></div>"
        )
    st.markdown(
        "<div style='display:flex;flex-direction:column;gap:0.3rem;'>" + "".join(lines) + "</div>",
        unsafe_allow_html=True,
    )


def render_trend_template_checklist(results: dict) -> None:
    render_checklist(results, TREND_TEMPLATE_LABELS)
