"""
Double Bottom (W-shape) detection. The source PDF states the defining rule
explicitly, comparing Qualcomm's first (faulty) base to its working one:
"a double bottom should see the second bottom undercut the first" — and
separately: "Sound bases that work almost always have only one or two bottom
areas... a double bottom should see the second bottom undercut the first."
Several examples cite durations in the ~9-22 week range (EMC's "9-week
classic double bottom base", eBay's "16-week double bottom", Amgen's
"classic double-bottom base").

Rules encoded:
1. Low1 -> middle peak -> Low2 swing structure (a W).
2. Low2 must undercut Low1 (be at or below it, within a small tolerance for
   near-ties) — the PDF's core discriminator between a working double bottom
   and a faulty one.
3. Overall depth (middle peak to the lower of the two lows) within a
   plausible band, duration within a plausible week range — both configurable,
   same spirit as Cup-with-Handle's bands.
4. Prior uptrend gate, same rationale as every other detector here.
5. Pivot = the middle peak's high (the resistance the W needs to clear);
   breakout requires a volume-confirmed close at or above it.
6. Final-leg readiness (same spirit as vcp.py's final-contraction check and
   cup_with_handle.py's rule 9): the segment from the second bottom (Low2)
   up to the latest bar — the leg climbing back toward the pivot, the W's
   equivalent of a handle — must be TIGHT (high-low range <=`final_leg_max_pct`,
   default ~9-10%) AND show volume dry-up over that same stretch
   (`final_leg_vdu_max_ratio_pct`, default 50%). A double bottom whose second
   low undercut the first (rule 2) can still be a long way from an actual
   breakout if this final climb is wide and choppy on heavy volume — this
   flags that explicitly via `final_leg_ready` rather than only inferring it
   from the pivot distance.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.trading import indicators as ind


def detect_double_bottom(df: pd.DataFrame, cfg: Optional[dict] = None) -> dict:
    """Same no-look-ahead convention as the other detectors: pass `df`
    truncated to the bar being evaluated."""
    cfg = cfg or {}
    lookback_bars = cfg.get("lookback_bars", 200)
    zigzag_pct = cfg.get("zigzag_pct_threshold", 10.0)
    min_depth = cfg.get("min_depth_pct", 15.0)
    max_depth = cfg.get("max_depth_pct", 50.0)
    min_duration = cfg.get("min_duration_bars", 30)
    max_duration = cfg.get("max_duration_bars", 150)
    undercut_tolerance_pct = cfg.get("undercut_tolerance_pct", 1.0)
    prior_uptrend_min = cfg.get("prior_uptrend_min_pct", 25.0)
    prior_uptrend_lookback = cfg.get("prior_uptrend_lookback_bars", 100)
    vdu_ma_window = cfg.get("vdu_ma_window", 50)
    final_leg_max_pct = cfg.get("final_leg_max_pct", 10.0)
    final_leg_vdu_max_ratio = cfg.get("final_leg_vdu_max_ratio_pct", 50.0)
    breakout_vol_multiple = cfg.get("breakout_volume_multiple", 1.4)

    not_found = {"found": False}
    if df is None or df.empty or len(df) < min_duration + 5:
        return not_found

    window_df = df.tail(lookback_bars)
    offset = len(df) - len(window_df)
    swings = ind.find_swings(window_df, zigzag_pct)
    if len(swings) < 3:
        return not_found

    best = None
    for i in range(len(swings) - 3, -1, -1):  # newest-first
        low1, mid_high, low2 = swings[i], swings[i + 1], swings[i + 2]
        if not (low1["type"] == "low" and mid_high["type"] == "high" and low2["type"] == "low"):
            continue
        if mid_high["price"] <= 0:
            continue
        if low2["price"] > low1["price"] * (1 + undercut_tolerance_pct / 100):
            continue  # second bottom didn't undercut the first — the PDF's faulty-base signature

        lower_low = min(low1["price"], low2["price"])
        depth_pct = (mid_high["price"] - lower_low) / mid_high["price"] * 100
        duration_bars = low2["idx"] - low1["idx"]
        if not (min_depth <= depth_pct <= max_depth):
            continue
        if not (min_duration <= duration_bars <= max_duration):
            continue

        low1_df_idx = low1["idx"] + offset
        # prior uptrend measured into the base's own left-side high (the bar
        # right before low1 starts declining), not into low1 itself
        left_high = float(df["High"].iloc[max(0, low1_df_idx - 1): low1_df_idx + 1].max())
        prior_pct = ind.prior_uptrend_pct(df, low1_df_idx, prior_uptrend_lookback, ref_price=left_high)
        if prior_pct is not None and prior_pct < prior_uptrend_min:
            continue

        best = {"low1": low1, "mid_high": mid_high, "low2": low2, "depth_pct": depth_pct,
                "duration_bars": duration_bars, "prior_pct": prior_pct}
        break

    if best is None:
        return not_found

    low1, mid_high, low2 = best["low1"], best["mid_high"], best["low2"]
    quality_flags = []
    if best["prior_pct"] is None:
        quality_flags.append("prior uptrend could not be evaluated (insufficient history before the base)")
    undercut_pct = (low1["price"] - low2["price"]) / low1["price"] * 100 if low1["price"] > 0 else None
    if undercut_pct is not None and undercut_pct < 0.5:
        quality_flags.append("second bottom barely undercut the first — borderline signature")

    low2_df_idx = low2["idx"] + offset
    final_leg = ind.final_leg_readiness(
        df, low2_df_idx, len(df) - 1, final_leg_max_pct, vdu_ma_window, final_leg_vdu_max_ratio,
    )
    if final_leg["is_ready"] is False:
        quality_flags.append(
            f"post-low2 leg not yet tight/volume-dried-up (range {final_leg['depth_pct']}% "
            f"vs {final_leg_max_pct:.0f}% max, VDU {final_leg['volume_dry_up']['ratio_pct']}% "
            f"vs {final_leg_vdu_max_ratio:.0f}% max) — base may still need more time before a genuine breakout"
        )

    pivot_price = mid_high["price"]
    bstate = ind.breakout_state(df, pivot_price, vdu_ma_window, breakout_vol_multiple)
    breakout = bstate["breakout"]
    breakout_volume_confirmed = bstate["breakout_volume_confirmed"]

    return {
        "found": True,
        "pattern_name": "double_bottom",
        "primary_depth_pct": round(best["depth_pct"], 2),
        "base": {
            "low1": round(low1["price"], 2), "low1_date": ind.date_str(df.index[low1["idx"] + offset]),
            "mid_high": round(mid_high["price"], 2), "mid_high_date": ind.date_str(df.index[mid_high["idx"] + offset]),
            "low2": round(low2["price"], 2), "low2_date": ind.date_str(df.index[low2["idx"] + offset]),
            "undercut_pct": round(undercut_pct, 2) if undercut_pct is not None else None,
            "depth_pct": round(best["depth_pct"], 2),
            "duration_bars": best["duration_bars"],
            "prior_uptrend_pct": round(best["prior_pct"], 2) if best["prior_pct"] is not None else None,
            "final_leg": final_leg,
        },
        "pivot_price": round(pivot_price, 2),
        "breakout": breakout,
        "breakout_volume_confirmed": breakout_volume_confirmed,
        "final_leg_ready": final_leg["is_ready"],
        "quality_flags": quality_flags,
    }
