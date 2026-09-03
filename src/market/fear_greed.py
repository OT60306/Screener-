"""
Fear & Greed Index — there's no free official API for CNN's version, so this
is an in-house proxy built from data yfinance already gives us. CNN's real
index blends 7 signals (momentum, price strength, breadth, put/call, junk
bond demand, market volatility, safe haven demand); options data (put/call)
isn't available for free, so this approximates the other 6 with a comparable
method for each — notably comparing VIX to its own 50-day average (CNN's
actual volatility methodology) rather than a 1-year percentile, which was the
biggest source of drift from the real index.

This is a proxy, not the CNN index — label it as such in the UI. Swap in a
real source later behind this same function signature if one becomes
available.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from src.common.cache import cached_fetch
from src.common.data_fetch import get_price_history


def _clip_score(raw: float) -> float:
    return float(np.clip(raw, 0, 100))


def _volatility_score() -> Optional[float]:
    """CNN-style: VIX vs. its own 50-day moving average, not a 1-year
    percentile. VIX well below its recent average => low fear (greed); well
    above => high fear."""
    df = get_price_history("^VIX")
    if df is None or df.empty or len(df) < 50:
        return None
    sma50 = df["Close"].rolling(50).mean().iloc[-1]
    latest = df["Close"].iloc[-1]
    if sma50 <= 0:
        return None
    spread_pct = (latest - sma50) / sma50 * 100
    # a 30% spread either side maps to the 0-100 extremes
    return _clip_score(50 - spread_pct * (50 / 30))


def _momentum_score() -> Optional[float]:
    """SPY vs. its own 125-day SMA — same methodology CNN uses for the S&P
    500 momentum signal."""
    df = get_price_history("SPY")
    if df is None or df.empty or len(df) < 125:
        return None
    sma125 = df["Close"].rolling(125).mean().iloc[-1]
    price = df["Close"].iloc[-1]
    if sma125 <= 0:
        return None
    spread_pct = (price - sma125) / sma125 * 100
    return _clip_score(50 + spread_pct * 5)


def _breadth_score(sample_tickers: list[str]) -> Optional[float]:
    """Proxy for market breadth. CNN's real breadth signal (McClellan Volume
    Summation Index) is a *cumulative* advance/decline measure, not a
    snapshot — it's specifically built to catch narrow-leadership rallies
    (price grinding to highs while participation quietly deteriorates, a
    classic hidden-fear divergence). A single "% above 50-day SMA" reading
    misses that entirely, so this blends the current level with its 10-day
    trend, weighting the trend more heavily."""
    daily_frac = []  # % of sample above its own 50-day SMA, for each of the last ~11 sessions
    for offset in range(10, -1, -1):
        above = total = 0
        for t in sample_tickers:
            df = get_price_history(t)
            if df is None or df.empty or len(df) < 50 + offset + 1:
                continue
            trimmed = df.iloc[: len(df) - offset] if offset else df
            sma50 = trimmed["Close"].rolling(50).mean().iloc[-1]
            total += 1
            if trimmed["Close"].iloc[-1] > sma50:
                above += 1
        daily_frac.append(above / total if total else None)

    valid = [v for v in daily_frac if v is not None]
    if not valid:
        return None
    level = valid[-1] * 100
    trend = (valid[-1] - valid[0]) * 100 if len(valid) > 1 else 0.0
    return _clip_score(50 + (level - 50) * 0.6 + trend * 2.5)


def _strength_score(sample_tickers: list[str]) -> Optional[float]:
    """Proxy for CNN's 'stock price strength': net % of the sample within 5%
    of its 52-week high (new-high-like behavior) minus % within 5% of its
    52-week low."""
    net = 0
    total = 0
    for t in sample_tickers:
        df = get_price_history(t)
        if df is None or df.empty or len(df) < 200:
            continue
        window = df.tail(252)
        high, low, price = window["High"].max(), window["Low"].min(), df["Close"].iloc[-1]
        if high <= 0 or low <= 0:
            continue
        total += 1
        if price >= high * 0.95:
            net += 1
        elif price <= low * 1.05:
            net -= 1
    if total == 0:
        return None
    return _clip_score(50 + (net / total) * 50)


def _safe_haven_score() -> Optional[float]:
    """Stocks (SPY) vs. bonds (TLT) — 20-trading-day relative return. Stocks
    outperforming bonds => greed; bonds outperforming (flight to safety) => fear."""
    spy = get_price_history("SPY")
    tlt = get_price_history("TLT")
    if spy is None or tlt is None or len(spy) < 21 or len(tlt) < 21:
        return None
    spy_ret = spy["Close"].iloc[-1] / spy["Close"].iloc[-21] - 1
    tlt_ret = tlt["Close"].iloc[-1] / tlt["Close"].iloc[-21] - 1
    spread_pct = (spy_ret - tlt_ret) * 100
    return _clip_score(50 + spread_pct * 4)


def _junk_bond_demand_score() -> Optional[float]:
    """High-yield (HYG) vs. investment-grade (LQD) bond ETF — 20-trading-day
    relative return. Junk outperforming IG => risk appetite (greed)."""
    hyg = get_price_history("HYG")
    lqd = get_price_history("LQD")
    if hyg is None or lqd is None or len(hyg) < 21 or len(lqd) < 21:
        return None
    hyg_ret = hyg["Close"].iloc[-1] / hyg["Close"].iloc[-21] - 1
    lqd_ret = lqd["Close"].iloc[-1] / lqd["Close"].iloc[-21] - 1
    spread_pct = (hyg_ret - lqd_ret) * 100
    return _clip_score(50 + spread_pct * 10)


# The 11 SPDR sector ETFs + small-cap (IWM) and mid-cap (MDY) — a handful of
# concentrated AI-era mega-caps (the previous sample) skews breadth/strength
# toward "greedy" whenever a few large names are strong even if the broader
# market isn't; sector/cap-size ETFs are a much closer proxy for the
# market-wide breadth CNN's real index measures (NYSE advance/decline volume).
BREADTH_SAMPLE = [
    "XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLRE", "XLU", "XLC",
    "IWM", "MDY",
]


def compute_fear_greed() -> dict:
    def fetch():
        components = {
            "market_momentum": _momentum_score(),
            "stock_price_strength": _strength_score(BREADTH_SAMPLE),
            "stock_price_breadth": _breadth_score(BREADTH_SAMPLE),
            "market_volatility": _volatility_score(),
            "safe_haven_demand": _safe_haven_score(),
            "junk_bond_demand": _junk_bond_demand_score(),
        }
        valid = [v for v in components.values() if v is not None]
        composite = round(sum(valid) / len(valid), 2) if valid else None
        label = _label(composite) if composite is not None else "unavailable"
        return {"composite": composite, "label": label, "components": components}

    try:
        value, is_fresh = cached_fetch("market", "fear_greed", ttl_hours=24, fetch_fn=fetch)
        value["is_fresh"] = is_fresh
        return value
    except Exception:
        return {"composite": None, "label": "unavailable", "components": {}, "is_fresh": False}


def _label(score: float) -> str:
    if score < 25:
        return "Extreme Fear"
    if score < 45:
        return "Fear"
    if score < 55:
        return "Neutral"
    if score < 75:
        return "Greed"
    return "Extreme Greed"
