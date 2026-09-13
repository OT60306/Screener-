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
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.trading import indicators as ind


def _prior_uptrend_pct(df: pd.DataFrame, low1_idx: int, lookback_bars: int) -> Optional[float]:
    start = max(0, low1_idx - lookback_bars)
    if start >= low1_idx:
        return None
    window = df.iloc[start:low1_idx]
    if window.empty:
        return None
    prior_low = float(window["Low"].min())
    low1_price = float(df["Low"].iloc[low1_idx])
    # prior uptrend measured into the base's own left-side high (the bar right
    # before low1 starts declining), not into low1 itself
    left_high = float(df["High"].iloc[max(0, low1_idx - 1): low1_idx + 1].max())
    if prior_low <= 0:
        return None
    return (left_high - prior_low) / prior_low * 100


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
        prior_pct = _prior_uptrend_pct(df, low1_df_idx, prior_uptrend_lookback)
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

    pivot_price = mid_high["price"]
    latest_close = float(df["Close"].iloc[-1])
    last_vol = float(df["Volume"].iloc[-1])
    avg_vol = df["Volume"].tail(vdu_ma_window).mean() if len(df) >= vdu_ma_window else None
    breakout = bool(latest_close >= pivot_price)
    breakout_volume_confirmed = (
        bool(avg_vol and avg_vol > 0 and last_vol > avg_vol * breakout_vol_multiple) if breakout else None
    )

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
        },
        "pivot_price": round(pivot_price, 2),
        "breakout": breakout,
        "breakout_volume_confirmed": breakout_volume_confirmed,
        "quality_flags": quality_flags,
    }
