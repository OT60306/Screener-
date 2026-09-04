"""
VCP (Volatility Contraction Pattern) analysis — Minervini-style base
detection, added to Stage 4 (Entry Trigger & VCP Quality) alongside the
existing pivot/breakout and Volume Dry-Up checks.

This is a geometric best-effort approximation of manual VCP counting, not a
reproduction of any specific charting tool's algorithm: contractions are
found via a ZigZag swing detector (a documented, standard technique — a new
swing point confirms once price reverses by at least a % threshold from the
last extreme), not hand-drawn trendlines. A ZigZag is used rather than a
fixed day-count window specifically because VCP waves get shorter in
duration as they tighten — a fixed window misses the later, tighter waves a
%-based reversal threshold still catches. Exact wave counts can differ from
a human chartist's read — treat the contraction count and depths as
directional, not authoritative.

Four things this adds beyond the existing Stage 4 checks:
1. Contraction count + per-wave depth %, and whether depths are
   progressively tightening (1T/2T/3T-style read).
2. Volume Dry-Up measured specifically in the FINAL contraction (not just a
   trailing N-day window) — VCP requires supply to dry up tightest right
   before the breakout, threshold <=50% of the 50-day average (stricter
   than the general Stage 4 VDU's <=70%).
3. RS Line new-high check: stock price relative to a benchmark (SPY),
   distinct from the numeric 1-99 RS Rating used elsewhere — a market
   leader's RS Line should be making new highs alongside (or ahead of) price.
4. Pivot = the final contraction's high, with breakout-day volume
   confirmation at >1.5x the 50-day average (stricter than the general
   Stage 4 pocket-pivot confirmation's 1.4x).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def _find_swings(df: pd.DataFrame, pct_threshold: float = 5.0) -> list[dict]:
    """ZigZag swing detection: tracks a running extreme (starting by looking
    for a high), and confirms it as a swing point only once price reverses
    by at least `pct_threshold`% from that extreme — then flips to tracking
    the opposite extreme. Standard technique; adapts to shrinking wave sizes
    naturally since the threshold is relative, not a fixed day count."""
    n = len(df)
    if n == 0:
        return []
    highs, lows = df["High"], df["Low"]

    swings: list[dict] = []
    looking_for_high = True
    ext_idx, ext_price = 0, float(highs.iloc[0])

    for i in range(1, n):
        hi, lo = float(highs.iloc[i]), float(lows.iloc[i])
        if looking_for_high:
            if hi > ext_price:
                ext_idx, ext_price = i, hi
            elif ext_price > 0 and (ext_price - lo) / ext_price * 100 >= pct_threshold:
                swings.append({"idx": ext_idx, "date": df.index[ext_idx], "price": ext_price, "type": "high"})
                looking_for_high = False
                ext_idx, ext_price = i, lo
        else:
            if lo < ext_price:
                ext_idx, ext_price = i, lo
            elif ext_price > 0 and (hi - ext_price) / ext_price * 100 >= pct_threshold:
                swings.append({"idx": ext_idx, "date": df.index[ext_idx], "price": ext_price, "type": "low"})
                looking_for_high = True
                ext_idx, ext_price = i, hi

    return swings


def _date_str(d) -> str:
    return str(d.date()) if hasattr(d, "date") else str(d)


def detect_contractions(
    df: pd.DataFrame,
    lookback_days: int = 130,
    zigzag_pct_threshold: float = 8.0,
    tightening_tolerance_pct: float = 3.0,
) -> list[dict]:
    """Finds every high->low swing leg within the trailing `lookback_days`,
    then keeps only the TRAILING run where each wave is progressively
    tighter than (or close to) the one before it — walking backward from the
    most recent wave and stopping at the first one that breaks the
    tightening pattern.

    This is deliberately not "every contraction since the base's origin
    peak": VCP wave counting is about the recent structure right before a
    possible breakout, not a stock's entire multi-month swing history — a
    volatile name can have many legs over months without ever forming a
    proper tightening base, and only the last few progressively-smaller
    waves are what actually matter for a breakout call."""
    if df is None or df.empty or len(df) < 20:
        return []
    window_df = df.tail(lookback_days)
    swings = _find_swings(window_df, zigzag_pct_threshold)
    if len(swings) < 2:
        return []

    all_legs = []
    for i in range(len(swings) - 1):
        a, b = swings[i], swings[i + 1]
        if a["type"] == "high" and b["type"] == "low" and a["price"] > 0:
            depth_pct = (a["price"] - b["price"]) / a["price"] * 100
            all_legs.append({
                "high": round(a["price"], 2), "high_date": _date_str(a["date"]), "high_idx": a["idx"],
                "low": round(b["price"], 2), "low_date": _date_str(b["date"]), "low_idx": b["idx"],
                "depth_pct": round(depth_pct, 2),
            })
    if not all_legs:
        return []

    trailing = [all_legs[-1]]
    for leg in reversed(all_legs[:-1]):
        if leg["depth_pct"] >= trailing[0]["depth_pct"] - tightening_tolerance_pct:
            trailing.insert(0, leg)
        else:
            break

    for i, leg in enumerate(trailing):
        leg["wave"] = i + 1
    return trailing


def is_progressive_tightening(contractions: list[dict], tolerance_pct: float = 3.0) -> Optional[bool]:
    """True if each successive contraction's depth % is smaller than the
    previous one (allowing a small tolerance for near-ties)."""
    if len(contractions) < 2:
        return None
    depths = [c["depth_pct"] for c in contractions]
    return all(depths[i + 1] <= depths[i] + tolerance_pct for i in range(len(depths) - 1))


def contraction_count_label(contractions: list[dict]) -> str:
    n = len(contractions)
    return f"{n}T" if n else "none detected"


def final_contraction_vdu(
    window_df: pd.DataFrame, contractions: list[dict], ma_window: int = 50, max_ratio_pct: float = 50.0
) -> dict:
    """Volume during the final contraction's high-to-low window vs. the
    50-day average. VCP wants the deepest dry-up right in the last, tightest
    wave — stricter (<=50%) than the general Stage 4 VDU check (<=70%)."""
    if not contractions or window_df is None or len(window_df) < ma_window:
        return {"ratio_pct": None, "is_vdu": None}
    ma_vol = window_df["Volume"].tail(ma_window).mean()
    if ma_vol <= 0:
        return {"ratio_pct": None, "is_vdu": None}
    last = contractions[-1]
    segment = window_df["Volume"].iloc[last["high_idx"]: last["low_idx"] + 1]
    if segment.empty:
        return {"ratio_pct": None, "is_vdu": None}
    ratio_pct = float(segment.mean() / ma_vol * 100)
    return {"ratio_pct": round(ratio_pct, 2), "is_vdu": bool(ratio_pct <= max_ratio_pct)}


def breakout_volume_confirmed(df: pd.DataFrame, multiple: float = 1.5, ma_window: int = 50) -> Optional[bool]:
    """Latest day's volume vs. its 50-day average — VCP's breakout
    confirmation threshold (1.5x) is stricter than the general Stage 4
    pocket-pivot check (1.4x)."""
    if df is None or len(df) < ma_window + 1:
        return None
    avg_vol = df["Volume"].tail(ma_window).mean()
    if avg_vol <= 0:
        return None
    return bool(df["Volume"].iloc[-1] > avg_vol * multiple)


def rs_line_new_high(
    df: pd.DataFrame, benchmark_df: Optional[pd.DataFrame], lookback_days: int = 252, near_high_tolerance_pct: float = 1.0
) -> Optional[bool]:
    """RS Line = stock price / benchmark price, a distinct read from the
    numeric 1-99 RS Rating: a market leader's RS Line should itself be at or
    near a new high, showing the stock outperforming the benchmark, not just
    outperforming a peer-ranked percentile. `near_high_tolerance_pct` treats
    "at" the high as within that %, not requiring an exact tick."""
    if df is None or benchmark_df is None or df.empty or benchmark_df.empty:
        return None
    merged = pd.DataFrame({"stock": df["Close"], "bench": benchmark_df["Close"]}).dropna()
    if len(merged) < 60:
        return None
    rs_line = (merged["stock"] / merged["bench"]).tail(lookback_days)
    high = rs_line.max()
    if high <= 0:
        return None
    return bool(rs_line.iloc[-1] >= high * (1 - near_high_tolerance_pct / 100))


def vcp_analysis(
    df: pd.DataFrame,
    benchmark_df: Optional[pd.DataFrame],
    rs_value: Optional[float],
    cfg: Optional[dict] = None,
) -> dict:
    cfg = cfg or {}
    lookback_days = cfg.get("lookback_days", 130)
    zigzag_pct_threshold = cfg.get("zigzag_pct_threshold", 8.0)
    tightening_tolerance_pct = cfg.get("tightening_tolerance_pct", 3.0)
    vdu_max_ratio_pct = cfg.get("final_contraction_vdu_max_ratio_pct", 50.0)
    breakout_vol_multiple = cfg.get("breakout_volume_multiple", 1.5)
    rs_line_lookback_days = cfg.get("rs_line_lookback_days", 252)
    market_leader_rs_min = cfg.get("market_leader_rs_min", 90)

    if df is None or df.empty:
        return {
            "contractions": [], "contraction_count_label": "no data", "progressive_tightening": None,
            "final_contraction_vdu": {"ratio_pct": None, "is_vdu": None}, "pivot_price": None,
            "breakout": None, "breakout_volume_confirmed": None, "rs_line_new_high": None,
            "rs_rating": rs_value, "market_leader": None,
        }

    window_df = df.tail(lookback_days)
    contractions = detect_contractions(df, lookback_days, zigzag_pct_threshold, tightening_tolerance_pct)
    tightening = is_progressive_tightening(contractions, tightening_tolerance_pct)
    vdu = final_contraction_vdu(window_df, contractions, 50, vdu_max_ratio_pct)

    pivot_price = contractions[-1]["high"] if contractions else None
    latest_close = float(df["Close"].iloc[-1])
    breakout = bool(pivot_price is not None and latest_close >= pivot_price)
    breakout_vol = breakout_volume_confirmed(df, breakout_vol_multiple) if breakout else None

    return {
        "contractions": contractions,
        "contraction_count_label": contraction_count_label(contractions),
        "progressive_tightening": tightening,
        "final_contraction_vdu": vdu,
        "pivot_price": pivot_price,
        "breakout": breakout,
        "breakout_volume_confirmed": breakout_vol,
        "rs_line_new_high": rs_line_new_high(df, benchmark_df, rs_line_lookback_days),
        "rs_rating": rs_value,
        "market_leader": (rs_value >= market_leader_rs_min) if rs_value is not None else None,
    }
