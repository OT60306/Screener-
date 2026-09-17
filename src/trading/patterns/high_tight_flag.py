"""
High Tight Flag detection — O'Neil's rarest, most explosive pattern. Directly
quoted from the source PDF (Taser International): "A high tight flag is a
rare pattern with usually only 1 or 2 occurring in a bull market year. On the
chart you will see a fast runup of 100% or more in only 4 to 8 weeks followed
by 3 to 5 weeks of sideways action holding most of the huge gain." Also shown
on Qualcomm's and Google's charts ("Buy: a high tight flag").

Rules encoded, straight from that description:
1. The "pole": a rise of >= `min_pole_pct` (default 90%, just under the
   PDF's "100% or more" to allow for near-misses) within `max_pole_bars`
   (default ~8 weeks).
2. The "flag": after the pole's peak, a sideways-to-down consolidation
   lasting `min_flag_bars`-`max_flag_bars` (default ~3-5 weeks) that gives
   back no more than `max_flag_depth_pct` of the peak price — "holding most
   of the huge gain" is the key discriminator from an ordinary post-runup
   pullback.
3. Pivot = the pole's peak; breakout requires a volume-confirmed close at or
   above it (the flag should show lighter volume, tightening supply, before
   the next leg up).
4. Final-leg readiness (same spirit as vcp.py's final-contraction check,
   cup_with_handle.py's rule 9, and double_bottom.py's rule 6): the flag
   itself (pole peak up to the latest bar) IS the final leg here — it should
   be TIGHT (high-low range <= `final_leg_max_pct`) AND show volume dry-up
   over that same stretch (`final_leg_vdu_max_ratio_pct`), on top of the
   simpler `max_flag_depth_pct` check above (which only bounds how far the
   flag gave back, not whether it's actually gone quiet).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.trading import indicators as ind


def detect_high_tight_flag(df: pd.DataFrame, cfg: Optional[dict] = None) -> dict:
    """Same no-look-ahead convention as the other detectors here: pass `df`
    truncated to the bar being evaluated."""
    cfg = cfg or {}
    lookback_bars = cfg.get("lookback_bars", 60)
    zigzag_pct = cfg.get("zigzag_pct_threshold", 15.0)
    min_pole_pct = cfg.get("min_pole_pct", 90.0)
    max_pole_bars = cfg.get("max_pole_bars", 8)
    min_flag_bars = cfg.get("min_flag_bars", 2)
    max_flag_bars = cfg.get("max_flag_bars", 6)
    max_flag_depth_pct = cfg.get("max_flag_depth_pct", 25.0)
    vdu_ma_window = cfg.get("vdu_ma_window", 10)
    final_leg_max_pct = cfg.get("final_leg_max_pct", 10.0)
    final_leg_vdu_max_ratio = cfg.get("final_leg_vdu_max_ratio_pct", 50.0)
    breakout_vol_multiple = cfg.get("breakout_volume_multiple", 1.4)

    not_found = {"found": False}
    if df is None or df.empty or len(df) < max_pole_bars + min_flag_bars + 2:
        return not_found

    window_df = df.tail(lookback_bars)
    offset = len(df) - len(window_df)
    swings = ind.find_swings(window_df, zigzag_pct)
    if len(swings) < 2:
        return not_found

    n = len(df)
    best = None
    for i in range(len(swings) - 2, -1, -1):  # newest-first
        pole_low, pole_high = swings[i], swings[i + 1]
        if not (pole_low["type"] == "low" and pole_high["type"] == "high"):
            continue
        if pole_low["price"] <= 0:
            continue
        pole_gain_pct = (pole_high["price"] - pole_low["price"]) / pole_low["price"] * 100
        pole_duration = pole_high["idx"] - pole_low["idx"]
        if pole_gain_pct < min_pole_pct or pole_duration > max_pole_bars or pole_duration < 1:
            continue

        pole_high_idx = pole_high["idx"] + offset
        flag_duration = (n - 1) - pole_high_idx
        if not (min_flag_bars <= flag_duration <= max_flag_bars):
            continue
        # The flag must not include the current/last bar in defining its own
        # low (same self-referential-pivot bug class as the other detectors
        # — here it doesn't affect the pivot, since pivot is the pole's high,
        # a confirmed swing point, but the flag LOW check must still exclude
        # today's bar or a breakout day's low could wrongly read as "shallow".
        flag_segment = df.iloc[pole_high_idx: n - 1]
        if flag_segment.empty:
            continue
        flag_low = float(flag_segment["Low"].min())
        flag_depth_pct = (pole_high["price"] - flag_low) / pole_high["price"] * 100 if pole_high["price"] > 0 else None
        if flag_depth_pct is None or flag_depth_pct > max_flag_depth_pct:
            continue

        best = {
            "pole_low": pole_low, "pole_high": pole_high, "pole_gain_pct": pole_gain_pct,
            "pole_duration": pole_duration, "flag_duration": flag_duration,
            "flag_low": flag_low, "flag_depth_pct": flag_depth_pct,
        }
        break

    if best is None:
        return not_found

    pivot_price = best["pole_high"]["price"]
    bstate = ind.breakout_state(df, pivot_price, vdu_ma_window, breakout_vol_multiple)
    breakout = bstate["breakout"]
    breakout_volume_confirmed = bstate["breakout_volume_confirmed"]

    quality_flags = []
    pole_high_idx = best["pole_high"]["idx"] + offset
    final_leg = ind.final_leg_readiness(
        df, pole_high_idx, len(df) - 1, final_leg_max_pct, vdu_ma_window, final_leg_vdu_max_ratio,
    )
    if final_leg["is_ready"] is False:
        quality_flags.append(
            f"flag not yet tight/volume-dried-up (range {final_leg['depth_pct']}% "
            f"vs {final_leg_max_pct:.0f}% max, VDU {final_leg['volume_dry_up']['ratio_pct']}% "
            f"vs {final_leg_vdu_max_ratio:.0f}% max) — may still need more time before a genuine breakout"
        )

    return {
        "found": True,
        "pattern_name": "high_tight_flag",
        "primary_depth_pct": round(best["flag_depth_pct"], 2),
        "base": {
            "pole_low": round(best["pole_low"]["price"], 2), "pole_low_date": ind.date_str(df.index[best["pole_low"]["idx"] + offset]),
            "pole_high": round(best["pole_high"]["price"], 2), "pole_high_date": ind.date_str(df.index[best["pole_high"]["idx"] + offset]),
            "pole_gain_pct": round(best["pole_gain_pct"], 2),
            "pole_duration_bars": best["pole_duration"],
            "flag_low": round(best["flag_low"], 2),
            "flag_depth_pct": round(best["flag_depth_pct"], 2),
            "flag_duration_bars": best["flag_duration"],
            "final_leg": final_leg,
        },
        "pivot_price": round(pivot_price, 2),
        "breakout": breakout,
        "breakout_volume_confirmed": breakout_volume_confirmed,
        "final_leg_ready": final_leg["is_ready"],
        "quality_flags": quality_flags,
    }
