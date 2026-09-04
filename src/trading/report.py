"""
Runs the full Trend Template + CANSLIM scan across a universe and produces
the ranked table Page 2 displays (and the per-ticker detail view).
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd
import streamlit as st

from src.common.data_fetch import get_price_history, get_price_histories, get_info, get_financial_statements
from src.common.market_index import get_broad_market_universe
from src.trading import indicators as ind
from src.trading import trend_template as tt
from src.trading import canslim as cs
from src.trading.market_health import evaluate_market_health
from src.trading.screening_stages import stage1_liquidity, stage4_entry_trigger
from src.trading.vcp import vcp_analysis


def _weighted_returns_for(tickers: list[str]) -> dict[str, float]:
    price_data = get_price_histories(tickers)
    weighted_returns = {}
    for t, df in price_data.items():
        if df is None or df.empty:
            continue
        wr = ind.weighted_return(df)
        # defensive: a NaN weighted_return (e.g. from a stray NaN price bar
        # slipping through) must never poison this ticker's own rank entry —
        # excluded here even though get_price_history now drops incomplete
        # in-progress-session rows at the source
        if wr is not None and not math.isnan(wr):
            weighted_returns[t] = wr
    return weighted_returns


@st.cache_data(ttl=3600, show_spinner=False)
def _broad_market_weighted_returns() -> dict[str, float]:
    """The expensive, shared part of RS ranking: weighted_return for every
    ticker in the broad market universe (~500+ tickers). Cached at the
    Streamlit layer (not just the underlying per-ticker price cache) so this
    is computed once per hour and reused across every caller in that window
    — the full scan, each stock-detail ticker switch, and every search —
    instead of once per interaction. Fetched in parallel via
    get_price_histories, the other half of the cold-scan speedup."""
    return _weighted_returns_for(get_broad_market_universe())


def _rs_ratings_for(tickers: list[str], cfg: dict) -> dict[str, float]:
    """RS Rating must be a percentile rank against a broad market cross-
    section, not just whatever small watchlist is being scanned — ranking a
    handful of already-strong momentum names only against each other
    structurally inflates scores (the top 20% of any list scores ~80+ by
    construction, regardless of how those names actually compare to the
    market). This ranks `tickers` within the union of `tickers` and the full
    S&P 500 + NASDAQ-100 constituent list (see src/common/market_index.py) —
    the broadest free cross-section available without a paid data feed."""
    broad_returns = _broad_market_weighted_returns()
    extra_tickers = [t for t in tickers if t not in broad_returns]
    extra_returns = _weighted_returns_for(extra_tickers) if extra_tickers else {}
    all_returns = {**broad_returns, **extra_returns}
    return ind.rs_rating(all_returns)


def scan_universe(tickers: list[str], cfg: Optional[dict] = None) -> pd.DataFrame:
    cfg = cfg or {}
    trading_cfg = cfg.get("trading", {})
    trend_cfg = trading_cfg.get("trend_template", {})
    rs_min = trading_cfg.get("rs_rating_min", 70)
    liquidity_cfg = trading_cfg.get("liquidity", {})
    entry_trigger_cfg = trading_cfg.get("entry_trigger", {})
    vcp_cfg = trading_cfg.get("vcp", {})

    price_data = get_price_histories(tickers)
    rs_ratings = _rs_ratings_for(tickers, cfg)
    benchmark_df = get_price_history(cfg.get("benchmark_ticker", "SPY"))

    index_trend = evaluate_market_health(cfg.get("benchmark_ticker", "SPY"), trend_cfg)

    rows = []
    for t in tickers:
        df = price_data.get(t)
        if df is None or df.empty:
            rows.append({"ticker": t, "match_pct": None, "rs_rating": None, "error": "no price data"})
            continue

        rs_value = rs_ratings.get(t)
        trend_result = tt.evaluate_all(df, rs_value, {**trend_cfg, "rs_rating_min": rs_min})
        pivot_info = ind.find_pivot_breakout(df)
        liquidity = stage1_liquidity(df, liquidity_cfg)
        entry_trigger = stage4_entry_trigger(df, pivot_info, entry_trigger_cfg)
        vcp = vcp_analysis(df, benchmark_df, rs_value, vcp_cfg)

        rows.append(
            {
                "ticker": t,
                "match_pct": trend_result["match_pct"],
                "evaluated_pct": trend_result["evaluated_pct"],
                "rs_rating": round(rs_value, 1) if rs_value is not None else None,
                "trend_checks": trend_result["results"],
                "pivot_price": pivot_info["pivot_price"],
                "breakout": pivot_info["breakout"],
                "ema_trend": pivot_info["ema_trend"],
                "last_close": pivot_info["latest_close"],
                "market_health_match_pct": index_trend.get("match_pct"),
                "avg_volume_10d": liquidity["avg_volume_10d"],
                "liquidity_passed": liquidity["passed"],
                "vdu_ratio_pct": entry_trigger["volume_dry_up"]["ratio_pct"],
                "vdu_passed": entry_trigger["volume_dry_up"]["is_vdu"],
                "vcp_contractions": vcp["contraction_count_label"],
                "vcp_tightening": vcp["progressive_tightening"],
                "vcp_final_vdu_pct": vcp["final_contraction_vdu"]["ratio_pct"],
                "vcp_pivot_price": vcp["pivot_price"],
                "vcp_breakout_vol_confirmed": vcp["breakout_volume_confirmed"],
                "vcp_rs_line_new_high": vcp["rs_line_new_high"],
                "vcp_market_leader": vcp["market_leader"],
            }
        )

    out = pd.DataFrame(rows)
    if "match_pct" in out.columns:
        out = out.sort_values("match_pct", ascending=False, na_position="last")
    return out.reset_index(drop=True)


def stock_detail(ticker: str, cfg: Optional[dict] = None) -> dict:
    """Full detail for Page 2's per-stock drill-down (and reused by Page 3's
    entry-timing section)."""
    cfg = cfg or {}
    trading_cfg = cfg.get("trading", {})
    trend_cfg = trading_cfg.get("trend_template", {})
    rs_min = trading_cfg.get("rs_rating_min", 70)

    df = get_price_history(ticker)
    if df is None or df.empty:
        return {"ticker": ticker, "error": "no price data"}

    info = get_info(ticker)
    stmts = get_financial_statements(ticker)
    wr = ind.weighted_return(df)
    rs_value = _rs_ratings_for([ticker], cfg).get(ticker)

    trend_result = tt.evaluate_all(df, rs_value, {**trend_cfg, "rs_rating_min": rs_min})
    index_trend = evaluate_market_health(cfg.get("benchmark_ticker", "SPY"), trend_cfg)
    canslim_result = cs.evaluate_all(df, stmts.get("income_stmt", []), info, rs_value, index_trend)
    pivot_info = ind.find_pivot_breakout(df)
    liquidity = stage1_liquidity(df, trading_cfg.get("liquidity", {}))
    entry_trigger = stage4_entry_trigger(df, pivot_info, trading_cfg.get("entry_trigger", {}))
    benchmark_df = get_price_history(cfg.get("benchmark_ticker", "SPY"))
    vcp = vcp_analysis(df, benchmark_df, rs_value, trading_cfg.get("vcp", {}))

    return {
        "ticker": ticker,
        "price_history": df,
        "trend_template": trend_result,
        "canslim": canslim_result,
        "pivot": pivot_info,
        "weighted_return": wr,
        "info": info,
        "stage1_liquidity": liquidity,
        "stage4_entry_trigger": entry_trigger,
        "vcp": vcp,
    }
