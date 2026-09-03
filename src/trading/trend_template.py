"""
Minervini's 8-point Trend Template. Each check returns True/False/None
(None = couldn't be evaluated — not enough history). `evaluate_all` combines
them and also returns a % match score for Page 2.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.trading import indicators as ind


def check_price_above_150_200(df: pd.DataFrame) -> Optional[bool]:
    sma150, sma200 = ind.sma(df, 150), ind.sma(df, 200)
    p150, p200 = ind.latest(sma150), ind.latest(sma200)
    price = ind.latest(df["Close"]) if df is not None and not df.empty else None
    if None in (p150, p200, price):
        return None
    return price > p150 and price > p200


def check_150_above_200(df: pd.DataFrame) -> Optional[bool]:
    p150, p200 = ind.latest(ind.sma(df, 150)), ind.latest(ind.sma(df, 200))
    if None in (p150, p200):
        return None
    return p150 > p200


def check_200_trending_up(df: pd.DataFrame, lookback_days: int = 21) -> Optional[bool]:
    return ind.sma_trending_up(df, 200, lookback_days)


def check_50_above_150_above_200(df: pd.DataFrame) -> Optional[bool]:
    p50, p150, p200 = (ind.latest(ind.sma(df, w)) for w in (50, 150, 200))
    if None in (p50, p150, p200):
        return None
    return p50 > p150 > p200


def check_price_above_50(df: pd.DataFrame) -> Optional[bool]:
    p50 = ind.latest(ind.sma(df, 50))
    price = ind.latest(df["Close"]) if df is not None and not df.empty else None
    if None in (p50, price):
        return None
    return price > p50


def check_above_52wk_low(df: pd.DataFrame, min_pct: float = 30) -> Optional[bool]:
    pct = ind.pct_above_52wk_low(df)
    if pct is None:
        return None
    return pct >= min_pct


def check_within_52wk_high(df: pd.DataFrame, max_pct_below: float = 25) -> Optional[bool]:
    pct = ind.pct_below_52wk_high(df)
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
    pct_below_52wk_high_max, sma_trend_lookback_days, rs_rating_min).
    Returns {'results': {name: bool|None}, 'match_pct': float, 'evaluated_pct': float}.
    match_pct is computed over checks that COULD be evaluated (avoids
    penalizing a stock just for short history on one sub-check)."""
    cfg = cfg or {}
    lookback = cfg.get("sma_trend_lookback_days", 21)
    low_min = cfg.get("pct_above_52wk_low_min", 30)
    high_max = cfg.get("pct_below_52wk_high_max", 25)
    rs_min = cfg.get("rs_rating_min", 70)

    results = {
        "price_above_150_200": check_price_above_150_200(df),
        "sma150_above_sma200": check_150_above_200(df),
        "sma200_trending_up": check_200_trending_up(df, lookback),
        "sma_stack_50_150_200": check_50_above_150_above_200(df),
        "price_above_50": check_price_above_50(df),
        "above_52wk_low_min_pct": check_above_52wk_low(df, low_min),
        "within_52wk_high_max_pct": check_within_52wk_high(df, high_max),
        "rs_rating_min": check_rs_rating(rs_value, rs_min),
    }

    evaluated = {k: v for k, v in results.items() if v is not None}
    match_pct = (sum(1 for v in evaluated.values() if v) / len(evaluated) * 100) if evaluated else 0.0
    evaluated_pct = len(evaluated) / len(results) * 100

    return {"results": results, "match_pct": round(match_pct, 1), "evaluated_pct": round(evaluated_pct, 1)}
