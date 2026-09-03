from __future__ import annotations

from typing import Optional

import pandas as pd

from src.common.data_fetch import get_info, get_financial_statements, get_price_history, get_news
from src.trading.indicators import find_pivot_breakout
from src.value.fundamentals import build_fundamental_section
from src.value.financial_flow import build_historical_health_section
from src.value.reverse_dcf import build_reverse_dcf_section
from src.value.catalysts_governance import build_catalysts_governance_section
from src.value.health_score import compute_health_score
from src.value.jitta_score import compute_jitta_score_proxy


def _historical_revenue_cagr(historical_section: dict) -> Optional[float]:
    growth = historical_section.get("margins_and_growth", {}).get("revenue_growth_pct_by_period")
    if not growth:
        return None
    return round(sum(growth) / len(growth), 1)


def build_stock_health_report(ticker: str, cfg: dict, news_fn=None) -> dict:
    """Full Page 3 report for one ticker: 3.1-3.4 + entry-timing chart data + Health Score."""
    info = get_info(ticker)
    stmts = get_financial_statements(ticker)
    df = get_price_history(ticker)

    wacc_pct = 8.0  # generic default; refine per-company if a real WACC input is added later
    fundamental = build_fundamental_section(info, stmts["income_stmt"], stmts["balance_sheet"], wacc_pct, ticker, cfg)
    historical = build_historical_health_section(stmts["income_stmt"], stmts["balance_sheet"], stmts["cashflow"])

    market_cap = info.get("marketCap") if info else None
    fcf_list = historical.get("fcf_series")
    latest_fcf = fcf_list[0] if fcf_list else None
    hist_cagr = _historical_revenue_cagr(historical)
    shares_outstanding = info.get("sharesOutstanding") if info else None
    current_price = info.get("currentPrice") or info.get("regularMarketPrice") if info else None
    # No free industry/TAM-growth data source is wired in — analyst forward
    # revenue growth estimate is used as a documented proxy, same pattern as
    # the RS Rating proxy (see CLAUDE.md non-goals).
    industry_growth_pct = (
        round(info.get("revenueGrowth") * 100, 2)
        if info and info.get("revenueGrowth") is not None
        else None
    )
    reverse_dcf = build_reverse_dcf_section(
        market_cap, latest_fcf, hist_cagr, cfg, shares_outstanding, current_price, industry_growth_pct
    )

    news_fn = news_fn or (lambda t: get_news(t))
    catalysts_gov = build_catalysts_governance_section(ticker, info, news_fn)

    weights = cfg.get("value", {}).get("health_score_weights", {})
    health = compute_health_score(fundamental, historical, reverse_dcf, weights)
    jitta_proxy = compute_jitta_score_proxy(fundamental, historical)
    historical["jitta_score_proxy"] = jitta_proxy

    pivot = find_pivot_breakout(df) if df is not None and not df.empty else {}

    return {
        "ticker": ticker,
        "3.1_fundamental": fundamental,
        "3.2_historical_health": historical,
        "3.3_reverse_dcf_and_catalysts": {**reverse_dcf, **catalysts_gov},
        "entry_timing": pivot,
        "health_score": health,
        "price_history": df,
        "company_name": info.get("shortName") if info else ticker,
    }


def scan_leaderboard(tickers: list[str], cfg: dict) -> pd.DataFrame:
    """Runs the numeric parts of the Page 3 report across a watchlist/universe
    and returns the Top-N Health Score leaderboard (size from config)."""
    top_n = cfg.get("value", {}).get("top_leaderboard_size", 15)
    rows = []
    for t in tickers:
        try:
            report = build_stock_health_report(t, cfg)
            rows.append(
                {
                    "ticker": t,
                    "company_name": report["company_name"],
                    "health_score": report["health_score"]["health_score"],
                    "coverage_pct": report["health_score"]["coverage_pct"],
                    "moat_verdict": report["3.1_fundamental"]["moat_verification"]["verdict"],
                    "piotroski_f_score": report["3.2_historical_health"]["piotroski_f_score"],
                    "jitta_score_proxy": report["3.2_historical_health"]["jitta_score_proxy"]["jitta_score_proxy"],
                }
            )
        except Exception as exc:
            rows.append({"ticker": t, "company_name": None, "health_score": None, "error": str(exc)})

    out = pd.DataFrame(rows)
    if "health_score" in out.columns:
        out = out.sort_values("health_score", ascending=False, na_position="last")
    return out.head(top_n).reset_index(drop=True)
