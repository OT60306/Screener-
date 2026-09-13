"""
Minervini's 8-point Trend Template. Each check returns True/False/None
(None = couldn't be evaluated — not enough history). `evaluate_all` combines
them and also returns a % match score for Page 2.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.trading import indicators as ind


def check_price_above_150_200(df: pd.DataFrame, mid_window: int = 150, slow_window: int = 200) -> Optional[bool]:
    sma_mid, sma_slow = ind.sma(df, mid_window), ind.sma(df, slow_window)
    p_mid, p_slow = ind.latest(sma_mid), ind.latest(sma_slow)
    price = ind.latest(df["Close"]) if df is not None and not df.empty else None
    if None in (p_mid, p_slow, price):
        return None
    return price > p_mid and price > p_slow


def check_150_above_200(df: pd.DataFrame, mid_window: int = 150, slow_window: int = 200) -> Optional[bool]:
    p_mid, p_slow = ind.latest(ind.sma(df, mid_window)), ind.latest(ind.sma(df, slow_window))
    if None in (p_mid, p_slow):
        return None
    return p_mid > p_slow


def check_200_trending_up(df: pd.DataFrame, slow_window: int = 200, lookback_days: int = 21) -> Optional[bool]:
    return ind.sma_trending_up(df, slow_window, lookback_days)


def check_50_above_150_above_200(
    df: pd.DataFrame, fast_window: int = 50, mid_window: int = 150, slow_window: int = 200
) -> Optional[bool]:
    p_fast, p_mid, p_slow = (ind.latest(ind.sma(df, w)) for w in (fast_window, mid_window, slow_window))
    if None in (p_fast, p_mid, p_slow):
        return None
    return p_fast > p_mid > p_slow


def check_price_above_50(df: pd.DataFrame, fast_window: int = 50) -> Optional[bool]:
    p_fast = ind.latest(ind.sma(df, fast_window))
    price = ind.latest(df["Close"]) if df is not None and not df.empty else None
    if None in (p_fast, price):
        return None
    return price > p_fast


def check_above_52wk_low(
    df: pd.DataFrame, min_pct: float = 30, lookback_bars: int = 252, min_bars: int = 200
) -> Optional[bool]:
    pct = ind.pct_above_52wk_low(df, lookback_bars, min_bars)
    if pct is None:
        return None
    return pct >= min_pct


def check_within_52wk_high(
    df: pd.DataFrame, max_pct_below: float = 25, lookback_bars: int = 252, min_bars: int = 200
) -> Optional[bool]:
    pct = ind.pct_below_52wk_high(df, lookback_bars, min_bars)
    if pct is None:
        return None
    return pct <= max_pct_below


def check_rs_rating(rs_value: Optional[float], min_rating: float = 70) -> Optional[bool]:
    if rs_value is None:
        return None
    return rs_value >= min_rating


CHECK_NAMES = [
    "price_above_150_200",
    "sma150_above_sma200",
    "sma200_trending_up",
    "sma_stack_50_150_200",
    "price_above_50",
    "above_52wk_low_min_pct",
    "within_52wk_high_max_pct",
    "rs_rating_min",
]


def evaluate_all(
    df: pd.DataFrame,
    rs_value: Optional[float],
    cfg: Optional[dict] = None,
) -> dict:
    """Runs all 8 checks. cfg can override thresholds (pct_above_52wk_low_min,
    pct_below_52wk_high_max, sma_trend_lookback_days, rs_rating_min) and, for
    a non-daily timeframe (see the Trading Scanner's Day/Week toggle), the SMA
    windows and 52-period high/low lookback themselves (fast_sma, mid_sma,
    slow_sma, high_low_lookback_bars, high_low_min_bars) — the weekly config
    passes 10/30/40-week SMAs and a 52-bar high/low window in place of the
    daily 50/150/200-day defaults.
    Returns {'results': {name: bool|None}, 'match_pct': float, 'evaluated_pct': float}.
    match_pct is computed over checks that COULD be evaluated (avoids
    penalizing a stock just for short history on one sub-check)."""
    cfg = cfg or {}
    lookback = cfg.get("sma_trend_lookback_days", 21)
    low_min = cfg.get("pct_above_52wk_low_min", 30)
    high_max = cfg.get("pct_below_52wk_high_max", 25)
    rs_min = cfg.get("rs_rating_min", 70)
    fast_w = cfg.get("fast_sma", 50)
    mid_w = cfg.get("mid_sma", 150)
    slow_w = cfg.get("slow_sma", 200)
    hl_lookback = cfg.get("high_low_lookback_bars", 252)
    hl_min_bars = cfg.get("high_low_min_bars", 200)

    results = {
        "price_above_150_200": check_price_above_150_200(df, mid_w, slow_w),
        "sma150_above_sma200": check_150_above_200(df, mid_w, slow_w),
        "sma200_trending_up": check_200_trending_up(df, slow_w, lookback),
        "sma_stack_50_150_200": check_50_above_150_above_200(df, fast_w, mid_w, slow_w),
        "price_above_50": check_price_above_50(df, fast_w),
        "above_52wk_low_min_pct": check_above_52wk_low(df, low_min, hl_lookback, hl_min_bars),
        "within_52wk_high_max_pct": check_within_52wk_high(df, high_max, hl_lookback, hl_min_bars),
        "rs_rating_min": check_rs_rating(rs_value, rs_min),
    }

    evaluated = {k: v for k, v in results.items() if v is not None}
    match_pct = (sum(1 for v in evaluated.values() if v) / len(evaluated) * 100) if evaluated else 0.0
    evaluated_pct = len(evaluated) / len(results) * 100

    return {"results": results, "match_pct": round(match_pct, 1), "evaluated_pct": round(evaluated_pct, 1)}
