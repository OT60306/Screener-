"""
Flat Base detection — O'Neil's tight, shallow sideways consolidation, often
forming as a "base on base" on top of a prior base (Southwestern Energy's
"perfect 13-week cup with handle" followed immediately by a 7-week flat base
in the source PDF; Oracle's "6-week flat base also becomes a base-on-base";
Ascend Communications' "6-week cup" followed by "four weeks of tight
accumulation"). Simpler geometry than Cup-with-Handle — no U-shape required,
just tightness — so this is a plain rolling high/low range check rather than
a ZigZag walk.

Rules encoded:
1. Prior uptrend >= `prior_uptrend_min_pct` before the base starts (same
   rationale as Cup-with-Handle — a base only matters coming out of a real
   advance, not as a random sideways drift).
2. The base's full range (high to low across its whole duration) corrects no
   more than `max_depth_pct` (O'Neil's examples run notably shallower than a
   cup — commonly under 15%, several PDF examples cite corrections of just a
   few percent, e.g. Southwestern Energy's flat base "corrects 10%").
3. Duration >= `min_duration_bars` (O'Neil's rule of thumb is "5 weeks or
   more" — a 3-week sideways move is explicitly called out as "not a base"
   on the Apple and Netflix charts in the PDF) and <= `max_duration_bars`.
4. Pivot = the base's high; breakout requires a volume-confirmed close at or
   above it, same convention as every other detector here.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.trading import indicators as ind


def _prior_uptrend_pct(df: pd.DataFrame, base_start_idx: int, lookback_bars: int) -> Optional[float]:
    start = max(0, base_start_idx - lookback_bars)
    if start >= base_start_idx:
        return None
    window = df.iloc[start:base_start_idx]
    if window.empty:
        return None
    prior_low = float(window["Low"].min())
    base_start_price = float(df["High"].iloc[base_start_idx])
    if prior_low <= 0:
        return None
    return (base_start_price - prior_low) / prior_low * 100


def detect_flat_base(df: pd.DataFrame, cfg: Optional[dict] = None) -> dict:
    """Scans backward from the last bar in `df` for the most recent valid
    flat base ending at (or still forming through) that bar — same
    no-look-ahead convention as detect_cup_with_handle: callers doing a
    walk-forward backtest must truncate `df` to the bar being evaluated."""
    cfg = cfg or {}
    lookback_bars = cfg.get("lookback_bars", 130)
    zigzag_pct = cfg.get("zigzag_pct_threshold", 8.0)
    max_depth = cfg.get("max_depth_pct", 15.0)
    ideal_max_depth = cfg.get("ideal_max_depth_pct", 10.0)
    min_duration = cfg.get("min_duration_bars", 5)
    max_duration = cfg.get("max_duration_bars", 40)
    prior_uptrend_min = cfg.get("prior_uptrend_min_pct", 20.0)
    prior_uptrend_lookback = cfg.get("prior_uptrend_lookback_bars", 60)
    vdu_ma_window = cfg.get("vdu_ma_window", 50)
    vdu_max_ratio_pct = cfg.get("vdu_max_ratio_pct", 70.0)
    breakout_vol_multiple = cfg.get("breakout_volume_multiple", 1.4)

    not_found = {"found": False}
    if df is None or df.empty or len(df) < min_duration + 5:
        return not_found

    window_df = df.tail(lookback_bars)
    offset = len(df) - len(window_df)
    swings = ind.find_swings(window_df, zigzag_pct)
    highs = [s for s in swings if s["type"] == "high"]
    if not highs:
        return not_found

    n = len(df)
    best = None
    for h in reversed(highs):  # newest-first — most recent qualifying base wins
        start_idx = h["idx"] + offset
        # The base itself is defined by bars UP TO BUT NOT INCLUDING the
        # current/last bar — that last bar is the candidate breakout bar, so
        # its own high must never be allowed to inflate the very pivot it's
        # supposed to be clearing (that would make a breakout close>=pivot
        # nearly impossible, since a bar's close rarely equals its own high).
        if start_idx >= n - 1:
            continue
        duration = (n - 2) - start_idx
        if not (min_duration <= duration <= max_duration):
            continue
        segment = df.iloc[start_idx: n - 1]
        base_high = float(segment["High"].max())
        base_low = float(segment["Low"].min())
        if base_high <= 0:
            continue
        depth_pct = (base_high - base_low) / base_high * 100
        if depth_pct > max_depth:
            continue
        prior_pct = _prior_uptrend_pct(df, start_idx, prior_uptrend_lookback)
        if prior_pct is not None and prior_pct < prior_uptrend_min:
            continue
        best = {
            "start_idx": start_idx, "base_high": base_high, "base_low": base_low,
            "depth_pct": depth_pct, "duration": duration, "prior_pct": prior_pct,
        }
        break

    if best is None:
        return not_found

    quality_flags = []
    if best["depth_pct"] > ideal_max_depth:
        quality_flags.append(f"base deeper than ideal ({best['depth_pct']:.1f}% > {ideal_max_depth:.0f}%)")
    if best["prior_pct"] is None:
        quality_flags.append("prior uptrend could not be evaluated (insufficient history before the base)")

    vdu_segment = df.iloc[best["start_idx"]:]
    if len(df) >= vdu_ma_window:
        ma_vol = df["Volume"].tail(vdu_ma_window).mean()
        vdu_ratio = float(vdu_segment["Volume"].mean() / ma_vol * 100) if ma_vol > 0 else None
        vdu = {"ratio_pct": round(vdu_ratio, 2) if vdu_ratio is not None else None,
               "is_vdu": bool(vdu_ratio <= vdu_max_ratio_pct) if vdu_ratio is not None else None}
    else:
        vdu = {"ratio_pct": None, "is_vdu": None}
    if vdu.get("is_vdu") is False:
        quality_flags.append("no volume dry-up within the base — supply hasn't calmed down yet")

    pivot_price = best["base_high"]
    latest_close = float(df["Close"].iloc[-1])
    last_vol = float(df["Volume"].iloc[-1])
    avg_vol = df["Volume"].tail(vdu_ma_window).mean() if len(df) >= vdu_ma_window else None
    breakout = bool(latest_close >= pivot_price)
    breakout_volume_confirmed = (
        bool(avg_vol and avg_vol > 0 and last_vol > avg_vol * breakout_vol_multiple) if breakout else None
    )

    return {
        "found": True,
        "pattern_name": "flat_base",
        "primary_depth_pct": round(best["depth_pct"], 2),
        "base": {
            "start_date": ind.date_str(df.index[best["start_idx"]]),
            "high": round(best["base_high"], 2),
            "low": round(best["base_low"], 2),
            "depth_pct": round(best["depth_pct"], 2),
            "duration_bars": best["duration"],
            "prior_uptrend_pct": round(best["prior_pct"], 2) if best["prior_pct"] is not None else None,
            "volume_dry_up": vdu,
        },
        "pivot_price": round(pivot_price, 2),
        "breakout": breakout,
        "breakout_volume_confirmed": breakout_volume_confirmed,
        "quality_flags": quality_flags,
    }
