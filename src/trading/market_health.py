"""
Applies the Trend Template to an index/benchmark itself, to answer "is the
market in a confirmed uptrend?" — the CANSLIM 'M'. Shared by Page 1 (Market
Pulse) and System A's CANSLIM scoring.
"""
from __future__ import annotations

from typing import Optional

from src.common.data_fetch import get_price_history
from src.trading import indicators as ind
from src.trading import trend_template as tt


def evaluate_market_health(ticker: str = "SPY", cfg: Optional[dict] = None) -> dict:
    """Returns the same shape as trend_template.evaluate_all, plus the ticker
    used, so Page 1 can render it directly and CANSLIM's 'M' check can reuse
    match_pct without recomputation."""
    df = get_price_history(ticker)
    if df is None or df.empty:
        return {"ticker": ticker, "results": {}, "match_pct": 0.0, "evaluated_pct": 0.0, "error": "no data"}

    wr = ind.weighted_return(df)
    rs_value = 99.0 if wr is not None and wr > 0 else (1.0 if wr is not None else None)
    # RS Rating is meaningless for the benchmark against itself; only the
    # other 7 Trend Template checks matter for market health.
    result = tt.evaluate_all(df, rs_value=None, cfg=cfg)
    result["ticker"] = ticker
    return result
