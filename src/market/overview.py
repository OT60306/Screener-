from __future__ import annotations

from src.common.data_fetch import get_price_history
from src.market.fear_greed import compute_fear_greed
from src.market.macro_calendar import get_upcoming_events
from src.trading.market_health import evaluate_market_health


def build_market_pulse(cfg: dict, index_tickers: list[str]) -> dict:
    """One selection drives both the index charts and the per-index market
    health read — every ticker the user picks gets both, no separate
    benchmark picker."""
    trend_cfg = cfg.get("trading", {}).get("trend_template", {})
    tickers = index_tickers or [cfg.get("benchmark_ticker", "SPY")]

    return {
        "fear_greed": compute_fear_greed(),
        "macro_events": get_upcoming_events(cfg),
        "market_health": {t: evaluate_market_health(t, trend_cfg) for t in tickers},
        "index_charts": {t: get_price_history(t) for t in tickers},
    }
