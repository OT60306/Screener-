"""
Ascending Base detection — a staircase-up structure of ~3 pullbacks, each
bottoming at a HIGHER low than the one before (and generally each high also
at or above the prior high), rather than a single U-shaped cup. Explicitly
named and diagrammed in the source PDF: Monogram Industries ("Buy: Ascending
base (has 3 pullbacks)"), Redman Industries ("Ascending base - pulls back 3
times, each low point higher than the previous"), Skyline Corp's chart shows
the same staircase shape without the label.

Structurally this is the same swing-legs walk as vcp.py's
detect_contractions, but with the opposite intent: VCP wants progressively
TIGHTER waves (volatility contracting into a breakout); an ascending base
wants a STAIRCASE of higher lows and higher highs (an uptrend advancing in
discrete legs, correcting 10-25% each time) — depths do NOT need to shrink.

Rules encoded:
1. Each leg's low must be a Higher Low than the previous leg's low (strict —
   a Lower Low breaks the staircase and resets the count, same convention as
   VCP's detect_contractions).
2. Each leg's high must be at or above the previous leg's high (within a
   small tolerance) — a base staircase-ing UP, not sideways or down.
3. Each leg's pullback depth within [min_depth_pct, max_depth_pct] (O'Neil's
   examples run deeper than VCP's tightening waves — commonly 10-25%).
4. At least `min_legs` legs (the PDF's examples are specifically 3-pullback
   staircases) to call it ascending rather than a single pullback.
5. Pivot = the most recent leg's high; breakout requires a volume-confirmed
   close at or above it.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.trading import indicators as ind


def detect_ascending_base(df: pd.DataFrame, cfg: Optional[dict] = None) -> dict:
    """Same no-look-ahead convention as the other detectors here: pass `df`
    truncated to the bar being evaluated."""
    cfg = cfg or {}
    lookback_bars = cfg.get("lookback_bars", 200)
    zigzag_pct = cfg.get("zigzag_pct_threshold", 10.0)
    min_depth = cfg.get("min_leg_depth_pct", 8.0)
    max_depth = cfg.get("max_leg_depth_pct", 25.0)
    higher_low_buffer_pct = cfg.get("higher_low_buffer_pct", 0.5)
    higher_high_tolerance_pct = cfg.get("higher_high_tolerance_pct", 3.0)
    min_legs = cfg.get("min_legs", 3)
    vdu_ma_window = cfg.get("vdu_ma_window", 50)
    breakout_vol_multiple = cfg.get("breakout_volume_multiple", 1.4)

    not_found = {"found": False}
    if df is None or df.empty or len(df) < 20:
        return not_found

    window_df = df.tail(lookback_bars)
    offset = len(df) - len(window_df)
    swings = ind.find_swings(window_df, zigzag_pct)
    if len(swings) < 2:
        return not_found

    all_legs = []
    for i in range(len(swings) - 1):
        a, b = swings[i], swings[i + 1]
        if a["type"] == "high" and b["type"] == "low" and a["price"] > 0:
            depth_pct = (a["price"] - b["price"]) / a["price"] * 100
            all_legs.append({
                "high": a["price"], "high_idx": a["idx"],
                "low": b["price"], "low_idx": b["idx"], "depth_pct": depth_pct,
            })
    if not all_legs:
        return not_found

    # Walk forward, only keeping legs within the plausible depth band and
    # resetting the staircase on a Lower Low or a high that fails to keep pace.
    staircase: list[dict] = []
    for leg in all_legs:
        if not (min_depth <= leg["depth_pct"] <= max_depth):
            staircase = []
            continue
        if not staircase:
            staircase = [leg]
            continue
        prev = staircase[-1]
        is_higher_low = leg["low"] > prev["low"] * (1 + higher_low_buffer_pct / 100)
        is_high_keeping_pace = leg["high"] >= prev["high"] * (1 - higher_high_tolerance_pct / 100)
        if is_higher_low and is_high_keeping_pace:
            staircase.append(leg)
        else:
            staircase = [leg]

    if len(staircase) < min_legs:
        return not_found

    last_leg = staircase[-1]
    first_leg = staircase[0]
    pivot_price = last_leg["high"]
    latest_close = float(df["Close"].iloc[-1])
    last_vol = float(df["Volume"].iloc[-1])
    avg_vol = df["Volume"].tail(vdu_ma_window).mean() if len(df) >= vdu_ma_window else None
    breakout = bool(latest_close >= pivot_price)
    breakout_volume_confirmed = (
        bool(avg_vol and avg_vol > 0 and last_vol > avg_vol * breakout_vol_multiple) if breakout else None
    )

    avg_leg_depth = sum(l["depth_pct"] for l in staircase) / len(staircase)
    total_rise_pct = (last_leg["high"] - first_leg["low"]) / first_leg["low"] * 100 if first_leg["low"] > 0 else None

    return {
        "found": True,
        "pattern_name": "ascending_base",
        "primary_depth_pct": round(avg_leg_depth, 2),
        "base": {
            "leg_count": len(staircase),
            "legs": [
                {
                    "high": round(l["high"], 2), "high_date": ind.date_str(df.index[l["high_idx"] + offset]),
                    "low": round(l["low"], 2), "low_date": ind.date_str(df.index[l["low_idx"] + offset]),
                    "depth_pct": round(l["depth_pct"], 2),
                }
                for l in staircase
            ],
            "total_rise_pct": round(total_rise_pct, 2) if total_rise_pct is not None else None,
        },
        "pivot_price": round(pivot_price, 2),
        "breakout": breakout,
        "breakout_volume_confirmed": breakout_volume_confirmed,
        "quality_flags": [],
    }
