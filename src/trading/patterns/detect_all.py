"""
Runs every supplementary pattern detector against one ticker's price history
and pairs each result with its backtest reference stats (see
backtest_reference.py). Used both by the bulk scan table (a compact
"Patterns" column via detected_pattern_short_labels) and the stock-detail
drill-down (the full per-pattern breakdown via detect_all_patterns) — in
neither place do these patterns filter or reorder anything; they're
supplementary context alongside the Trend Template/VCP ranking. See
backtest_reference.py for why (none of the 5 cleared the original 60-70%
win-rate bar).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.trading.patterns.ascending_base import detect_ascending_base
from src.trading.patterns.backtest_reference import BACKTEST_REFERENCE
from src.trading.patterns.cup_with_handle import detect_cup_with_handle
from src.trading.patterns.double_bottom import detect_double_bottom
from src.trading.patterns.flat_base import detect_flat_base
from src.trading.patterns.high_tight_flag import detect_high_tight_flag

SUPPLEMENTARY_PATTERNS = {
    "cup_with_handle": detect_cup_with_handle,
    "double_bottom": detect_double_bottom,
    "ascending_base": detect_ascending_base,
    "flat_base": detect_flat_base,
    "high_tight_flag": detect_high_tight_flag,
}

PATTERN_LABELS = {
    "cup_with_handle": "Cup with Handle",
    "double_bottom": "Double Bottom",
    "ascending_base": "Ascending Base",
    "flat_base": "Flat Base",
    "high_tight_flag": "High Tight Flag",
}

# Short labels for the compact "Patterns" column on the bulk scan table.
PATTERN_SHORT_LABELS = {
    "cup_with_handle": "Cup",
    "double_bottom": "Dbl Bottom",
    "ascending_base": "Ascending",
    "flat_base": "Flat Base",
    "high_tight_flag": "HTF",
}


def detect_all_patterns(df: pd.DataFrame, trading_cfg: dict, timeframe: str = "day") -> dict:
    """Returns {pattern_name: {**detector_result, "backtest_reference": {...}}}
    for every pattern in SUPPLEMENTARY_PATTERNS. `trading_cfg` is the full
    `cfg["trading"]` dict — this pulls each pattern's day/week config the
    same way report.py's _resolve_timeframe_cfg does."""
    trading_cfg = trading_cfg or {}
    if timeframe == "week":
        patterns_root = trading_cfg.get("weekly", {}).get("patterns", {})
    else:
        patterns_root = trading_cfg.get("patterns", {})

    out = {}
    for name, fn in SUPPLEMENTARY_PATTERNS.items():
        pattern_cfg = patterns_root.get(name, {})
        result = fn(df, pattern_cfg)
        result["backtest_reference"] = BACKTEST_REFERENCE.get(name)
        out[name] = result
    return out


def detected_pattern_short_labels(df: pd.DataFrame, trading_cfg: dict, timeframe: str = "day") -> str:
    """Compact "Cup, Flat Base"-style string of every pattern currently
    detected (found=True, regardless of breakout state) — for the bulk scan
    table's "Patterns" column. Returns "-" when nothing is detected.

    Patterns that expose `final_leg_ready` (all 5: cup_with_handle,
    double_bottom, ascending_base, flat_base, high_tight_flag — see each
    detector's own final-leg rule in its module docstring) get a " (tight)"
    suffix when that final leg — the handle, the post-low2 climb, the last
    staircase leg, the base's tail end, or the flag itself — is both tight
    (<=~9-10% range) and volume-dried-up, i.e. it looks like the actual last
    squeeze before breakout rather than a base still working through it. This
    is still purely descriptive: it does NOT filter or reorder anything, same
    as every other pattern signal here (see module docstring)."""
    results = detect_all_patterns(df, trading_cfg, timeframe)
    labels = []
    for name, r in results.items():
        if not r.get("found"):
            continue
        label = PATTERN_SHORT_LABELS[name]
        if r.get("final_leg_ready") is True:
            label += " (tight)"
        labels.append(label)
    return ", ".join(labels) if labels else "-"
