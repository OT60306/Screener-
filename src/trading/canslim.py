"""
O'Neil CANSLIM checks. Each function returns a value or None ('not
computable from available data' — flagged, never guessed). C/A/I are
best-effort given yfinance's patchy fundamentals; N/S/L/M are fully computable.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.common.data_fetch import statement_to_df
from src.trading import indicators as ind


def current_quarterly_earnings_growth(income_stmt_records: list) -> Optional[float]:
    """C — latest quarter EPS/net income YoY % growth. Best-effort: yfinance's
    quarterly history depth varies by ticker."""
    df = statement_to_df(income_stmt_records)
    if df.empty or "Net Income" not in df.index:
        return None
    row = df.loc["Net Income"].dropna()
    if len(row) < 2:
        return None
    latest, prior = row.iloc[0], row.iloc[1]
    if prior == 0:
        return None
    return float((latest - prior) / abs(prior) * 100)


def annual_earnings_growth(income_stmt_records: list) -> Optional[float]:
    """A — multi-year annual earnings growth trend (CAGR over available years)."""
    df = statement_to_df(income_stmt_records)
    if df.empty or "Net Income" not in df.index:
        return None
    row = df.loc["Net Income"].dropna()
    if len(row) < 2:
        return None
    years = len(row) - 1
    latest, earliest = row.iloc[0], row.iloc[-1]
    if earliest <= 0 or years <= 0:
        return None
    return float(((latest / earliest) ** (1 / years) - 1) * 100)


def new_highs(df: pd.DataFrame) -> Optional[bool]:
    """N — proxy: within 10% of 52-week high right now."""
    pct = ind.pct_below_52wk_high(df)
    if pct is None:
        return None
    return pct <= 10


def supply_demand_volume(df: pd.DataFrame) -> Optional[bool]:
    """S — up-on-volume confirmation."""
    return ind.volume_confirms_move(df)


def leader_relative_strength(rs_value: Optional[float], min_rating: float = 70) -> Optional[bool]:
    """L — reuses the RS Rating computed for the Trend Template."""
    if rs_value is None:
        return None
    return rs_value >= min_rating


def institutional_sponsorship(info: Optional[dict]) -> Optional[float]:
    """I — % held by institutions, where yfinance has it. Sparse/stale data —
    treat as directional, not precise."""
    if not info:
        return None
    val = info.get("heldPercentInstitutions")
    return float(val * 100) if val is not None else None


def market_direction(index_trend_result: Optional[dict]) -> Optional[bool]:
    """M — pass through the index-level Trend Template result (shared with
    Page 1's market health check)."""
    if not index_trend_result:
        return None
    return index_trend_result.get("match_pct", 0) >= 70


def evaluate_all(
    df: pd.DataFrame,
    income_stmt_records: list,
    info: Optional[dict],
    rs_value: Optional[float],
    index_trend_result: Optional[dict],
) -> dict:
    return {
        "C_current_qtr_earnings_growth_pct": current_quarterly_earnings_growth(income_stmt_records),
        "A_annual_earnings_growth_pct": annual_earnings_growth(income_stmt_records),
        "N_near_new_highs": new_highs(df),
        "S_volume_confirms": supply_demand_volume(df),
        "L_relative_strength_leader": leader_relative_strength(rs_value),
        "I_institutional_pct": institutional_sponsorship(info),
        "M_market_in_uptrend": market_direction(index_trend_result),
    }
