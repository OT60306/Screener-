"""
Shared yfinance access layer. Everything else in this project (System A,
System B, Page 1's market health) should fetch price/fundamental data through
here, not by importing yfinance directly, so caching/backoff/degradation stays
in one place.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import pandas as pd
import yfinance as yf

from src.common.cache import cached_fetch

PRICE_HISTORY_PERIOD = "2y"  # enough for 200-day SMA + lookback checks


def _retry(fn, attempts: int = 3, base_delay: float = 1.0):
    last_exc = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # yfinance raises various network/HTTP errors
            last_exc = exc
            time.sleep(base_delay * (2 ** i))
    raise last_exc


def get_price_history(ticker: str, ttl_hours: float = 6) -> Optional[pd.DataFrame]:
    """Daily OHLCV history. Returns None (never raises) if unavailable, so a
    bad ticker never crashes a batch scan."""

    def fetch():
        df = _retry(lambda: yf.Ticker(ticker).history(period=PRICE_HISTORY_PERIOD))
        if df is None or df.empty:
            raise ValueError(f"empty price history for {ticker}")
        # yfinance can return a partial row for the still-open current session
        # (real Volume, but NaN OHLC) — drop it so no consumer's .iloc[-1]
        # silently poisons into NaN. Dropped before caching so a later refetch
        # after the session closes picks up the completed bar.
        df = df.dropna(subset=["Close"])
        if df.empty:
            raise ValueError(f"empty price history for {ticker} after dropping incomplete rows")
        return df.reset_index().to_dict(orient="list")

    try:
        raw, _fresh = cached_fetch("trading", f"price_{ticker}", ttl_hours, fetch)
        df = pd.DataFrame(raw)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], utc=True)
            df = df.set_index("Date")
        return df
    except Exception:
        return None


def get_price_history_long(ticker: str, years: int = 10, ttl_hours: float = 720) -> Optional[pd.DataFrame]:
    """Long-history daily OHLCV for backtesting (src/trading/backtest.py) —
    a separate cache namespace/TTL from the live scanner's 2y/6h series so a
    30-day-old backtest snapshot never collides with (or gets evicted by) the
    scanner's fast-refreshing cache. Same never-raises contract as
    get_price_history."""

    def fetch():
        df = _retry(lambda: yf.Ticker(ticker).history(period=f"{years}y"))
        if df is None or df.empty:
            raise ValueError(f"empty long price history for {ticker}")
        df = df.dropna(subset=["Close"])
        if df.empty:
            raise ValueError(f"empty long price history for {ticker} after dropping incomplete rows")
        return df.reset_index().to_dict(orient="list")

    try:
        raw, _fresh = cached_fetch("trading_long", f"price_{years}y_{ticker}", ttl_hours, fetch)
        df = pd.DataFrame(raw)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], utc=True)
            df = df.set_index("Date")
        return df
    except Exception:
        return None


def get_price_histories_long(
    tickers: list[str], years: int = 10, ttl_hours: float = 720, max_workers: int = 16
) -> dict[str, Optional[pd.DataFrame]]:
    """Batch version of get_price_history_long — see get_price_histories."""
    if not tickers:
        return {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(lambda t: get_price_history_long(t, years, ttl_hours), tickers))
    return dict(zip(tickers, results))


def get_price_histories(tickers: list[str], ttl_hours: float = 6, max_workers: int = 16) -> dict[str, Optional[pd.DataFrame]]:
    """Batch version of get_price_history — fetches many tickers concurrently
    (I/O-bound: network + per-ticker cache file, threads release the GIL
    while waiting on either) instead of one at a time. A full ~500-ticker
    scan is network-latency-bound, so this is the single biggest lever on
    cold-cache scan time; each ticker still goes through the same cache/
    retry/degrade path as get_price_history, so results are identical —
    just fetched in parallel."""
    if not tickers:
        return {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(lambda t: get_price_history(t, ttl_hours), tickers))
    return dict(zip(tickers, results))


def get_info(ticker: str, ttl_hours: float = 168) -> Optional[dict]:
    """Company profile / snapshot fundamentals (sector, industry, margins,
    market cap, etc). Returns None on failure."""

    def fetch():
        info = _retry(lambda: yf.Ticker(ticker).info)
        if not info:
            raise ValueError(f"empty info for {ticker}")
        return info

    try:
        value, _fresh = cached_fetch("value/fundamentals", f"info_{ticker}", ttl_hours, fetch)
        return value
    except Exception:
        return None


def get_financial_statements(ticker: str, ttl_hours: float = 168) -> dict:
    """Returns dict with 'income_stmt', 'balance_sheet', 'cashflow' as
    (possibly empty) records-oriented lists. Missing statements degrade to
    empty lists rather than raising, so downstream ratio functions can check
    length and return None per-metric instead of crashing."""

    def fetch():
        t = yf.Ticker(ticker)
        out = {}
        for attr, key in [
            ("financials", "income_stmt"),
            ("balance_sheet", "balance_sheet"),
            ("cashflow", "cashflow"),
        ]:
            try:
                df = _retry(lambda a=attr: getattr(t, a))
                if df is None or df.empty:
                    out[key] = []
                else:
                    df = df.reset_index()
                    df.columns = [str(c) for c in df.columns]
                    out[key] = df.to_dict(orient="list")
            except Exception:
                out[key] = []
        return out

    try:
        value, _fresh = cached_fetch("value/fundamentals", f"stmts_{ticker}", ttl_hours, fetch)
        return value
    except Exception:
        return {"income_stmt": [], "balance_sheet": [], "cashflow": []}


def get_news(ticker: str, ttl_hours: float = 12, limit: int = 8) -> list[dict]:
    """Recent headlines for a ticker via yfinance's free news feed (Yahoo
    Finance) — real catalysts/news, no separate paid API key required.
    Returns [] (never raises) if unavailable."""

    def fetch():
        raw = _retry(lambda: yf.Ticker(ticker).news) or []
        items = []
        for item in raw[:limit]:
            content = item.get("content", item)  # yfinance has changed this shape across versions
            title = content.get("title") or item.get("title")
            if not title:
                continue
            publisher = (content.get("provider") or {}).get("displayName") if isinstance(content.get("provider"), dict) else item.get("publisher")
            link = (content.get("canonicalUrl") or {}).get("url") if isinstance(content.get("canonicalUrl"), dict) else item.get("link")
            pub_date = content.get("pubDate") or item.get("providerPublishTime")
            items.append({"title": title, "publisher": publisher or "unknown", "link": link, "published": pub_date})
        return items

    try:
        value, _fresh = cached_fetch("value/catalysts", f"news_{ticker}", ttl_hours, fetch)
        return value
    except Exception:
        return []


def statement_to_df(records: list) -> pd.DataFrame:
    """Helper: rebuild a DataFrame from the records list produced above,
    indexed by the line-item column (first column from reset_index)."""
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if df.empty:
        return df
    first_col = df.columns[0]
    return df.set_index(first_col)
