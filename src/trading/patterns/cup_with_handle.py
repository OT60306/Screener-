"""
Cup-with-Handle detection — William O'Neil's most common base pattern (per
his own IBD column: "the most common pattern of big winners... repeated
dozens of times every market cycle" and roughly 70% of the examples in
IBD_AmericaGreatestOpportunity1.pdf are this shape). This is a geometric
best-effort approximation built from the article's own annotated rules, in
the same spirit as vcp.py's ZigZag-based contraction detector — not a
reproduction of any charting tool, and not a claim of matching a human
chartist's read bar-for-bar. Treat every field here as directional input to
the backtest (see backtest_trading.py), not a guarantee.

Rules encoded, each traceable to a specific annotation in the source PDF:
1. Prior uptrend >= ~30% before the cup begins ("You need a prior uptrend of
   at least 30% with strong volume for the bases you buy" — Fairchild Camera).
2. Cup depth 12-50% (O'Neil's normal range is ~12-33%; deeper corrections in
   bear markets are flagged as less ideal, not rejected outright, since
   several examples in the article show good cups >33% deep — e.g. Chrysler's
   36-week cup, ISRG's 46%-deep first base which the article explicitly
   flags as faulty *because* it was that deep. So: reject only far outside
   this band, and separately flag anything above ~35% as "deeper than ideal").
3. Cup duration within [min_bars, max_bars] — O'Neil's examples run from ~6
   weeks to 64+ weeks; both ends are configurable per timeframe.
4. The right side of the cup must recover to near the left side's high
   (within `right_high_tolerance_pct`) — a cup whose right side stalls well
   below the old high hasn't really completed.
5. Handle forms in the UPPER HALF of the cup and corrects only modestly
   (<=15%, ideally <=12%) — "the handle's peak price up from the low of the
   base should get above overhead supply area" and a handle "in the lower
   half of the base... failed" (PeopleSoft base B). A handle that drifts down
   along its lows instead of holding tight is flagged (Houston Oil's handle
   is explicitly marked "Do not buy" for exactly this).
6. Handle should show Volume Dry-Up — reuses the same VDU check as Stage 4/VCP.
7. Pivot = the handle's high; breakout requires a close at/above the pivot
   with volume confirmation (reuses the existing breakout-volume infra).
8. A cup with NO handle at all is still a valid, O'Neil-approved pattern
   (explicitly shown as "Cup without handle" on the Chrysler chart) — this
   detector reports that case too rather than rejecting it, controlled by
   `allow_no_handle` in cfg.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.trading import indicators as ind


def _prior_uptrend_pct(df: pd.DataFrame, left_high_idx: int, lookback_bars: int) -> Optional[float]:
    """% rise from the lowest low in the `lookback_bars` window immediately
    before the cup's left rim, up to the left rim's high — the "prior
    uptrend" gate."""
    start = max(0, left_high_idx - lookback_bars)
    if start >= left_high_idx:
        return None
    window = df.iloc[start:left_high_idx]
    if window.empty:
        return None
    prior_low = float(window["Low"].min())
    left_high_price = float(df["High"].iloc[left_high_idx])
    if prior_low <= 0:
        return None
    return (left_high_price - prior_low) / prior_low * 100


def _segment_vdu(df: pd.DataFrame, seg_start_idx: int, seg_end_idx: int, ma_window: int, max_ratio_pct: float) -> dict:
    """Average volume across [seg_start_idx, seg_end_idx] vs. the trailing
    `ma_window`-bar average ending at seg_end_idx — same VDU logic as
    vcp.py's final_contraction_vdu, generalized to an arbitrary segment."""
    if seg_end_idx < ma_window:
        return {"ratio_pct": None, "is_vdu": None}
    ma_vol = df["Volume"].iloc[max(0, seg_end_idx - ma_window + 1): seg_end_idx + 1].mean()
    if ma_vol <= 0:
        return {"ratio_pct": None, "is_vdu": None}
    segment = df["Volume"].iloc[seg_start_idx: seg_end_idx + 1]
    if segment.empty:
        return {"ratio_pct": None, "is_vdu": None}
    ratio_pct = float(segment.mean() / ma_vol * 100)
    return {"ratio_pct": round(ratio_pct, 2), "is_vdu": bool(ratio_pct <= max_ratio_pct)}


def detect_cup_with_handle(df: pd.DataFrame, cfg: Optional[dict] = None) -> dict:
    """Scans the trailing `lookback_bars` for the most recent valid cup (and
    handle, if one has formed) as of the LAST bar in `df` — callers doing a
    walk-forward backtest must pass a `df` truncated to the bar being
    evaluated (no look-ahead), same convention as every other pure function
    in this project.

    Returns {"found": False} if nothing qualifies, otherwise a dict with
    the cup/handle geometry, pivot price, breakout state, and a
    `quality_flags` list of non-fatal warnings (e.g. "cup deeper than ideal",
    "no handle yet — still forming")."""
    cfg = cfg or {}
    lookback_bars = cfg.get("lookback_bars", 340)
    zigzag_pct = cfg.get("zigzag_pct_threshold", 12.0)
    min_depth = cfg.get("min_cup_depth_pct", 12.0)
    max_depth = cfg.get("max_cup_depth_pct", 50.0)
    ideal_max_depth = cfg.get("ideal_max_cup_depth_pct", 35.0)
    min_duration = cfg.get("min_cup_duration_bars", 35)
    max_duration = cfg.get("max_cup_duration_bars", 325)
    right_high_tolerance = cfg.get("right_high_tolerance_pct", 10.0)
    prior_uptrend_min = cfg.get("prior_uptrend_min_pct", 30.0)
    prior_uptrend_lookback = cfg.get("prior_uptrend_lookback_bars", 130)
    handle_max_depth = cfg.get("handle_max_depth_pct", 15.0)
    handle_ideal_max_depth = cfg.get("handle_ideal_max_depth_pct", 12.0)
    min_handle_bars = cfg.get("min_handle_duration_bars", 5)
    max_handle_bars = cfg.get("max_handle_duration_bars", 25)
    handle_vdu_ma_window = cfg.get("handle_vdu_ma_window", 50)
    handle_vdu_max_ratio = cfg.get("handle_vdu_max_ratio_pct", 70.0)
    breakout_vol_multiple = cfg.get("breakout_volume_multiple", 1.4)
    allow_no_handle = cfg.get("allow_no_handle", True)

    not_found = {"found": False}
    if df is None or df.empty or len(df) < min_duration + 5:
        return not_found

    window_df = df.tail(lookback_bars)
    offset = len(df) - len(window_df)  # translate window-local swing idx -> df-local idx
    swings = ind.find_swings(window_df, zigzag_pct)
    if len(swings) < 3:
        return not_found

    # Walk swing triplets (high, low, high) newest-first so the most recent
    # qualifying cup wins — an older, already-invalidated cup earlier in the
    # window shouldn't shadow a fresh one that formed after it.
    best = None
    for i in range(len(swings) - 3, -1, -1):
        a, b, c = swings[i], swings[i + 1], swings[i + 2]
        if not (a["type"] == "high" and b["type"] == "low" and c["type"] == "high"):
            continue
        left_high, cup_low, right_high = a["price"], b["price"], c["price"]
        if left_high <= 0 or right_high <= 0:
            continue
        depth_pct = (left_high - cup_low) / left_high * 100
        duration_bars = c["idx"] - a["idx"]
        if not (min_depth <= depth_pct <= max_depth):
            continue
        if not (min_duration <= duration_bars <= max_duration):
            continue
        if right_high < left_high * (1 - right_high_tolerance / 100):
            continue  # right side never recovered near the old high — cup incomplete

        left_high_df_idx = a["idx"] + offset
        prior_pct = _prior_uptrend_pct(df, left_high_df_idx, prior_uptrend_lookback)
        if prior_pct is not None and prior_pct < prior_uptrend_min:
            continue  # no real prior advance — not a base worth buying

        best = {
            "a": a, "b": b, "c": c, "c_swing_idx": i + 2,
            "depth_pct": depth_pct, "duration_bars": duration_bars, "prior_pct": prior_pct,
        }
        break

    if best is None:
        return not_found

    a, b, c = best["a"], best["b"], best["c"]
    quality_flags = []
    if best["depth_pct"] > ideal_max_depth:
        quality_flags.append(f"cup deeper than ideal ({best['depth_pct']:.1f}% > {ideal_max_depth:.0f}%)")
    if best["prior_pct"] is None:
        quality_flags.append("prior uptrend could not be evaluated (insufficient history before the cup)")

    right_high_idx = c["idx"] + offset
    cup_midpoint = b["price"] + 0.5 * (a["price"] - b["price"])

    # Handle: the next swing low after the right rim (if any), plus whatever
    # forms after it up to the latest bar.
    handle = None
    remaining = swings[best["c_swing_idx"] + 1:]
    handle_low_swing = next((s for s in remaining if s["type"] == "low"), None)

    if handle_low_swing is not None:
        handle_low_idx = handle_low_swing["idx"] + offset
        handle_low_price = handle_low_swing["price"]
        handle_depth_pct = (c["price"] - handle_low_price) / c["price"] * 100 if c["price"] > 0 else None
        in_upper_half = handle_low_price >= cup_midpoint
        # Pivot is the cup rim itself (c["price"]) — NOT the max high seen
        # since the handle low, which would wrongly include the current/
        # latest bar's own high on a breakout bar and inflate the pivot to
        # match it (making close>=pivot nearly impossible to satisfy, since
        # a bar's close rarely equals its own high). A handle staying below
        # the rim until the actual breakout is the whole point of the pattern.
        pivot_price = c["price"]
        handle_duration_bars = (len(df) - 1) - right_high_idx
        vdu = _segment_vdu(df, right_high_idx, len(df) - 1, handle_vdu_ma_window, handle_vdu_max_ratio)

        if handle_depth_pct is not None and handle_depth_pct > handle_max_depth:
            quality_flags.append(f"handle too deep ({handle_depth_pct:.1f}% > {handle_max_depth:.0f}%)")
        elif handle_depth_pct is not None and handle_depth_pct > handle_ideal_max_depth:
            quality_flags.append(f"handle deeper than ideal ({handle_depth_pct:.1f}% > {handle_ideal_max_depth:.0f}%)")
        if not in_upper_half:
            quality_flags.append("handle drifted into the lower half of the cup — faulty per O'Neil's rule")
        if handle_duration_bars < min_handle_bars:
            quality_flags.append("handle still short — may not be fully formed yet")
        elif handle_duration_bars > max_handle_bars:
            quality_flags.append("handle running long — base may be getting stale")
        if vdu.get("is_vdu") is False:
            quality_flags.append("no volume dry-up in the handle — supply hasn't calmed down yet")

        handle = {
            "low": round(handle_low_price, 2), "low_date": ind.date_str(df.index[handle_low_idx]),
            "depth_pct": round(handle_depth_pct, 2) if handle_depth_pct is not None else None,
            "in_upper_half": in_upper_half,
            "duration_bars": handle_duration_bars,
            "volume_dry_up": vdu,
        }
    else:
        pivot_price = c["price"]
        if allow_no_handle:
            quality_flags.append("no handle formed — valid O'Neil pattern (\"cup without handle\") but less common")
        else:
            return not_found

    latest_close = float(df["Close"].iloc[-1])
    avg_vol = df["Volume"].tail(handle_vdu_ma_window).mean() if len(df) >= handle_vdu_ma_window else None
    last_vol = float(df["Volume"].iloc[-1])
    breakout = bool(pivot_price and latest_close >= pivot_price)
    breakout_volume_confirmed = (
        bool(avg_vol and avg_vol > 0 and last_vol > avg_vol * breakout_vol_multiple) if breakout else None
    )

    return {
        "found": True,
        "pattern_name": "cup_with_handle",
        "primary_depth_pct": round(best["depth_pct"], 2),
        "cup": {
            "left_high": round(a["price"], 2), "left_high_date": ind.date_str(df.index[a["idx"] + offset]),
            "low": round(b["price"], 2), "low_date": ind.date_str(df.index[b["idx"] + offset]),
            "right_high": round(c["price"], 2), "right_high_date": ind.date_str(df.index[right_high_idx]),
            "depth_pct": round(best["depth_pct"], 2),
            "duration_bars": best["duration_bars"],
            "prior_uptrend_pct": round(best["prior_pct"], 2) if best["prior_pct"] is not None else None,
        },
        "handle": handle,
        "pivot_price": round(pivot_price, 2) if pivot_price else None,
        "breakout": breakout,
        "breakout_volume_confirmed": breakout_volume_confirmed,
        "quality_flags": quality_flags,
    }
