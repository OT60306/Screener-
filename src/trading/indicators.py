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


def find_swings(df: pd.DataFrame, pct_threshold: float = 5.0) -> list[dict]:
    """ZigZag swing detection: tracks a running extreme (starting by looking
    for a high), and confirms it as a swing point only once price reverses by
    at least `pct_threshold`% from that extreme — then flips to tracking the
    opposite extreme. Standard technique; adapts to shrinking/growing wave
    sizes naturally since the threshold is relative, not a fixed bar count.
    Shared by vcp.py's contraction detection and the pattern detectors in
    src/trading/patterns/."""
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


def date_str(d) -> str:
    return str(d.date()) if hasattr(d, "date") else str(d)


def resample_weekly(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Daily OHLCV -> weekly bars (week ending Friday), for the Trading
    Scanner's Day/Week timeframe toggle. Weeks with no trading (holiday-only
    weeks) never appear in daily data, so no explicit drop is needed. Every
    window-based check downstream (SMA/EMA/high-low/VDU/VCP) just runs on
    whatever bars it's handed — a week-count window on this output reads as
    weeks the same way a day-count window reads as days on the daily df."""
    if df is None or df.empty:
        return None
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    weekly = df.resample("W-FRI").agg(agg).dropna(subset=["Close"])
    return weekly


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


def pct_above_52wk_low(df: pd.DataFrame, lookback_bars: int = 252, min_bars: int = 200) -> Optional[float]:
    """`lookback_bars`/`min_bars` are expressed in the df's own bar unit — 252
    trading days for a daily df, 52 weeks for a weekly df (both ~1 year)."""
    if not _has_enough_history(df, min_bars):
        return None
    window = df.tail(lookback_bars)
    low = window["Low"].min()
    price = df["Close"].iloc[-1]
    if low <= 0:
        return None
    return float((price - low) / low * 100)


def pct_below_52wk_high(df: pd.DataFrame, lookback_bars: int = 252, min_bars: int = 200) -> Optional[float]:
    if not _has_enough_history(df, min_bars):
        return None
    window = df.tail(lookback_bars)
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


def find_pivot_breakout(
    df: pd.DataFrame, base_window: int = 35, ema_span: int = 21, slow_ema_span: int = 200
) -> dict:
    """
    Simple pivot/breakout detector (Part 1 — entry timing overlay):
    - 'pivot' = the high of the most recent consolidation base (a `base_window`
      bar window where price has been range-bound relative to its own volatility)
    - 'breakout' = True if the latest close clears the pivot on above-average
      volume
    `base_window`/`ema_span`/`slow_ema_span` are in the df's own bar unit — pass
    week-scaled values for a weekly df (see the Trading Scanner's Day/Week
    toggle's weekly config).
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
    e200 = ema(df, slow_ema_span) if _has_enough_history(df, slow_ema_span) else None
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


def prior_uptrend_pct(
    df: pd.DataFrame,
    ref_idx: int,
    lookback_bars: int,
    ref_price: Optional[float] = None,
) -> Optional[float]:
    """% rise from the lowest low in the `lookback_bars` window immediately
    before `ref_idx`, up to a reference high price — the "prior uptrend"
    gate shared by the cup_with_handle, double_bottom, and flat_base pattern
    detectors in src/trading/patterns/ (was previously copy-pasted in each).
    `ref_price` defaults to the High at `ref_idx`; pass an explicit value
    when the caller needs a different anchor (e.g. double_bottom widens it
    to a small window around its left low)."""
    start = max(0, ref_idx - lookback_bars)
    if start >= ref_idx:
        return None
    window = df.iloc[start:ref_idx]
    if window.empty:
        return None
    prior_low = float(window["Low"].min())
    if ref_price is None:
        ref_price = float(df["High"].iloc[ref_idx])
    if prior_low <= 0:
        return None
    return (ref_price - prior_low) / prior_low * 100


def breakout_state(
    df: pd.DataFrame,
    pivot_price: Optional[float],
    vol_ma_window: int,
    breakout_vol_multiple: float,
) -> dict:
    """Shared breakout/volume-confirmation check used by every pattern
    detector in src/trading/patterns/ (ascending_base, double_bottom,
    flat_base, high_tight_flag, cup_with_handle) — was previously
    copy-pasted in each of those files. `breakout` = last close at/above
    pivot; `breakout_volume_confirmed` = None unless there's a breakout, in
    which case it's whether last volume cleared `vol_ma_window`-day average
    volume by `breakout_vol_multiple`."""
    latest_close = float(df["Close"].iloc[-1])
    last_vol = float(df["Volume"].iloc[-1])
    avg_vol = df["Volume"].tail(vol_ma_window).mean() if len(df) >= vol_ma_window else None
    breakout = bool(pivot_price and latest_close >= pivot_price)
    breakout_volume_confirmed = (
        bool(avg_vol and avg_vol > 0 and last_vol > avg_vol * breakout_vol_multiple) if breakout else None
    )
    return {
        "latest_close": latest_close,
        "last_vol": last_vol,
        "avg_vol": avg_vol,
        "breakout": breakout,
        "breakout_volume_confirmed": breakout_volume_confirmed,
    }


def segment_vdu(df: pd.DataFrame, seg_start_idx: int, seg_end_idx: int, ma_window: int, max_ratio_pct: float) -> dict:
    """Average volume across [seg_start_idx, seg_end_idx] (df-local, inclusive)
    vs. the trailing `ma_window`-bar average ending at seg_end_idx. Same
    convention as `volume_dry_up` but for an arbitrary historical segment
    instead of always the trailing N bars — needed to check VDU specifically
    over a handle, a post-low2 leg, or any other named segment rather than
    just "the last 5 days". Shared by cup_with_handle.py, double_bottom.py,
    and (via `final_leg_readiness` below) every other pattern detector that
    needs a "was volume dry over this specific stretch" check."""
    if df is None or df.empty or seg_end_idx < ma_window - 1 or seg_end_idx < seg_start_idx:
        return {"ratio_pct": None, "is_vdu": None}
    ma_vol = df["Volume"].iloc[max(0, seg_end_idx - ma_window + 1): seg_end_idx + 1].mean()
    if ma_vol <= 0:
        return {"ratio_pct": None, "is_vdu": None}
    segment = df["Volume"].iloc[seg_start_idx: seg_end_idx + 1]
    if segment.empty:
        return {"ratio_pct": None, "is_vdu": None}
    ratio_pct = float(segment.mean() / ma_vol * 100)
    return {"ratio_pct": round(ratio_pct, 2), "is_vdu": bool(ratio_pct <= max_ratio_pct)}


def final_leg_readiness(
    df: pd.DataFrame,
    seg_start_idx: int,
    seg_end_idx: int,
    tight_max_pct: float = 10.0,
    vdu_ma_window: int = 50,
    vdu_max_ratio_pct: float = 50.0,
) -> dict:
    """The "coiled spring right before breakout" check: the very last leg
    going into a breakout — VCP's final contraction, a cup's handle, or a
    double bottom's post-low2 leg back up toward the pivot — should be tight
    AND volume-dry at the same time, not just one or the other. Requested
    criterion: that final leg's own high-low range should not exceed
    ~9-10% (default `tight_max_pct=10.0`), and volume over that same window
    should have dried up vs. the trailing average (reuses `segment_vdu`,
    defaulting to VCP's stricter 50% ratio rather than the general 70% Stage
    4 threshold, since this is specifically checking for the *tightest,
    driest* leg of the whole base — the last squeeze before price actually
    breaks out — not just "some" dry-up anywhere in the base).

    `is_ready` is True only when both the tightness and VDU checks pass;
    it's None (not False) when there isn't enough history to know either
    one, so callers don't mistake "unknown" for "failed". This also applies
    to the segment's own length: a 1-2 bar "final leg" is too short to say
    anything meaningful about its range or volume (a single quiet day can
    look "tight and dry" by pure chance), so segments shorter than
    `MIN_SEGMENT_BARS` return unknown rather than a possibly false-positive
    is_ready=True."""
    MIN_SEGMENT_BARS = 3
    not_enough = {
        "depth_pct": None, "is_tight": None,
        "volume_dry_up": {"ratio_pct": None, "is_vdu": None}, "is_ready": None,
    }
    if df is None or df.empty or seg_end_idx < seg_start_idx:
        return not_enough
    segment = df.iloc[seg_start_idx: seg_end_idx + 1]
    if segment.empty or len(segment) < MIN_SEGMENT_BARS:
        return not_enough
    seg_high = float(segment["High"].max())
    seg_low = float(segment["Low"].min())
    if seg_high <= 0:
        return not_enough
    depth_pct = (seg_high - seg_low) / seg_high * 100
    is_tight = bool(depth_pct <= tight_max_pct)
    vdu = segment_vdu(df, seg_start_idx, seg_end_idx, vdu_ma_window, vdu_max_ratio_pct)
    is_ready = bool(is_tight and vdu["is_vdu"]) if vdu["is_vdu"] is not None else None
    return {
        "depth_pct": round(depth_pct, 2),
        "is_tight": is_tight,
        "volume_dry_up": vdu,
        "is_ready": is_ready,
    }
