"""
Broad market-index constituent lists — S&P 500 and NASDAQ-100 — the widest
free, no-paid-API cross-sections this project can pull. Scraped from
Wikipedia's maintained constituent tables (same "no hard external-API
dependency in any critical path" treatment as every other source here:
cached long since constituents change rarely, with a hand-curated CSV
fallback if the fetch ever fails or Wikipedia's table structure changes, so
a blocked network path or a page edit never crashes the scanner).
"""
from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

from src.common.cache import cached_fetch
from src.common.universe import load_universe

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; stock-intel-health-scorecard/1.0)"}
_FALLBACK_FILE = "data/rs_benchmark_universe.csv"
_MIN_SP500 = 400       # sanity floor — trips a fallback if Wikipedia's table structure changes
_MIN_NASDAQ100 = 80


def _clean_tickers(raw: list) -> list[str]:
    # Wikipedia uses "." for share classes (BRK.B); yfinance wants "-" (BRK-B)
    return [str(t).strip().upper().replace(".", "-") for t in raw if str(t).strip()]


def get_sp500_tickers(ttl_hours: float = 720) -> list[str]:
    """~500 tickers, scraped from Wikipedia's S&P 500 constituents table.
    Cached 30 days by default — the index barely changes week to week."""

    def fetch():
        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=_HEADERS, timeout=20
        )
        resp.raise_for_status()
        table = pd.read_html(StringIO(resp.text))[0]
        tickers = _clean_tickers(table["Symbol"].tolist())
        if len(tickers) < _MIN_SP500:
            raise ValueError(f"unexpectedly few S&P 500 tickers parsed: {len(tickers)}")
        return tickers

    try:
        tickers, _fresh = cached_fetch("market", "sp500_constituents", ttl_hours, fetch)
        return tickers
    except Exception:
        return load_universe(_FALLBACK_FILE)


def get_nasdaq100_tickers(ttl_hours: float = 720) -> list[str]:
    """~100 tickers, scraped from Wikipedia's NASDAQ-100 constituents table."""

    def fetch():
        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies", headers=_HEADERS, timeout=20
        )
        resp.raise_for_status()
        table = pd.read_html(StringIO(resp.text))[0]
        tickers = _clean_tickers(table["Ticker"].tolist())
        if len(tickers) < _MIN_NASDAQ100:
            raise ValueError(f"unexpectedly few NASDAQ-100 tickers parsed: {len(tickers)}")
        return tickers

    try:
        tickers, _fresh = cached_fetch("market", "nasdaq100_constituents", ttl_hours, fetch)
        return tickers
    except Exception:
        return []  # NASDAQ-100 heavily overlaps S&P 500 (already in the fallback) — safe to drop, not crash


def get_broad_market_universe(ttl_hours: float = 720) -> list[str]:
    """Union of S&P 500 + NASDAQ-100 — the RS Rating peer set and (merged
    with the user's own watchlist) the Trading Scanner's scan pool."""
    tickers = set(get_sp500_tickers(ttl_hours)) | set(get_nasdaq100_tickers(ttl_hours))
    return sorted(tickers)
