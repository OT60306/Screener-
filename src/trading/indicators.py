"""
Pure indicator functions. Every function here takes a price DataFrame
(index=Date, columns include Close/High/Low/Volume) and returns a value or
None if there isn't enough history — never raises on bad/short data.

This module is reused by: Page 2's scoring, Page 1's index-level market
health, Page 3's entry-timing view, and every chart's EMA/pivot overlay.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def _has_enough_history(df: pd.DataFrame, min_days: int) -> bool:
    return df is not None and not df.empty and len(df) >= min_days


def sma(df: pd.DataFrame, window: int) -> Optional[pd.Series]:
    if not _has_enough_history(df, window):
        return None
    return df["Close"].rolling(window).mean()


def ema(df: pd.DataFrame, span: int) -> Optional[pd.Series]:
    if not _has_enough_history(df, span):
        return None
    return df["Close"].ewm(span=span, adjust=False).mean()


def latest(series: Optional[pd.Series]) -> Optional[float]:
    if series is None or series.dropna().empty:
        return None
    return float(series.dropna().iloc[-1])


def pct_above_52wk_low(df: pd.DataFrame) -> Optional[float]:
    if not _has_enough_history(df, 200):
        return None
    window = df.tail(252)
    low = window["Low"].min()
    price = df["Close"].iloc[-1]
    if low <= 0:
        return None
    return float((price - low) / low * 100)


def pct_below_52wk_high(df: pd.DataFrame) -> Optional[float]:
    if not _has_enough_history(df, 200):
        return None
    window = df.tail(252)
    high = window["High"].max()
    price = df["Close"].iloc[-1]
    if high <= 0:
        return None
    return float((high - price) / high * 100)


def sma_trending_up(df: pd.DataFrame, window: int, lookback_days: int = 21) -> Optional[bool]:
    series = sma(df, window)
    if series is None or len(series.dropna()) < lookback_days + 1:
        return None
    recent = series.dropna()
    return bool(recent.iloc[-1] > recent.iloc[-1 - lookback_days])


def weighted_return(df: pd.DataFrame) -> Optional[float]:
    """IBD-style weighted performance: heavier weight on the most recent
    quarter. Used as the RS Rating input before percentile ranking."""
    if not _has_enough_history(df, 252):
        return None
    close = df["Close"]

    def ret(days):
        if len(close) <= days:
            return None
        return (close.iloc[-1] / close.iloc[-1 - days]) - 1

    r3, r6, r9, r12 = ret(63), ret(126), ret(189), ret(252)
    if None in (r3, r6, r9, r12):
        return None
    # 3-month move weighted double, per common IBD-style RS formulas
    return float(2 * r3 + r6 + r9 + r12)


def rs_rating(weighted_returns: dict[str, float]) -> dict[str, float]:
    """Percentile-rank each ticker's weighted_return against the given set
    (a benchmark universe or the scan universe itself). Returns 1-99 scale,
    IBD-style. `weighted_returns`: {ticker: weighted_return_value}."""
    if not weighted_returns:
        return {}
    tickers = list(weighted_returns.keys())
    values = np.array([weighted_returns[t] for t in tickers])
    ranks = pd.Series(values).rank(pct=True) * 98 + 1
    return {t: float(r) for t, r in zip(tickers, ranks)}


def volume_confirms_move(df: pd.DataFrame, lookback: int = 50) -> Optional[bool]:
    """True if the latest day's volume is above its recent average AND price
    moved up — a simple up-on-volume confirmation used in CANSLIM's 'S'."""
    if not _has_enough_history(df, lookback + 1):
        return None
    avg_vol = df["Volume"].tail(lookback).mean()
    last_vol = df["Volume"].iloc[-1]
    price_up = df["Close"].iloc[-1] > df["Close"].iloc[-2]
    if avg_vol <= 0:
        return None
    return bool(last_vol > avg_vol * 1.4 and price_up)


def avg_volume(df: pd.DataFrame, window: int = 10) -> Optional[float]:
    """N-day average share volume — Stage 1 liquidity filter input."""
    if not _has_enough_history(df, window):
        return None
    return float(df["Volume"].tail(window).mean())


def volume_dry_up(
    df: pd.DataFrame,
    recent_window: int = 5,
    ma_window: int = 50,
    max_ratio_pct: float = 70.0,
) -> dict:
    """Volume Dry-Up (VDU) check: compares the average volume over the most
    recent `recent_window` sessions (the tail end of a base/handle) against
    the `ma_window`-day average volume. A ratio at or below `max_ratio_pct`
    (default 70%) confirms supply has dried up — sellers have exhausted
    themselves — ahead of a breakout or pocket pivot. Returns the ratio and
    a pass/fail; both None if there isn't enough history."""
    if not _has_enough_history(df, ma_window):
        return {"ratio_pct": None, "is_vdu": None}
    ma_vol = df["Volume"].tail(ma_window).mean()
    if ma_vol <= 0:
        return {"ratio_pct": None, "is_vdu": None}
    recent_vol = df["Volume"].tail(recent_window).mean()
    ratio_pct = float(recent_vol / ma_vol * 100)
    return {"ratio_pct": round(ratio_pct, 2), "is_vdu": bool(ratio_pct <= max_ratio_pct)}


def find_pivot_breakout(df: pd.DataFrame, base_window: int = 35, ema_span: int = 21) -> dict:
    """
    Simple pivot/breakout detector (Part 1 — entry timing overlay):
    - 'pivot' = the high of the most recent consolidation base (a `base_window`
      day window where price has been range-bound relative to its own volatility)
    - 'breakout' = True if the latest close clears the pivot on above-average
      volume
    Returns a dict with pivot price, whether a breakout just fired, and the
    EMA trend state — degrades to all-None fields if there isn't enough history.
    """
    result = {"pivot_price": None, "breakout": None, "ema_trend": None, "latest_close": None}
    if not _has_enough_history(df, base_window + ema_span):
        return result

    window = df.tail(base_window)
    pivot_price = float(window["High"].max())
    last_close = float(df["Close"].iloc[-1])
    avg_vol = df["Volume"].tail(base_window).mean()
    last_vol = df["Volume"].iloc[-1]

    breakout = bool(last_close >= pivot_price and last_vol > avg_vol * 1.3)

    e = ema(df, ema_span)
    e200 = ema(df, 200) if _has_enough_history(df, 200) else None
    if e is not None and len(e.dropna()) >= 2:
        slope_up = e.dropna().iloc[-1] > e.dropna().iloc[-5] if len(e.dropna()) >= 5 else None
        above_200 = None
        if e200 is not None and not e200.dropna().empty:
            above_200 = last_close > float(e200.dropna().iloc[-1])
        if slope_up is True and above_200 is not False:
            trend = "uptrend"
        elif slope_up is False:
            trend = "downtrend"
        else:
            trend = "base-building"
    else:
        trend = None

    result.update(
        pivot_price=pivot_price,
        breakout=breakout,
        ema_trend=trend,
        latest_close=last_close,
    )
    return result
