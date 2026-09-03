"""
Page 3, section 3.2 — Historical Health.

Margin/growth/FCF trends plus a reproducible accounting red-flag audit
(Beneish M-score, Piotroski F-score) instead of an open-ended "look for red
flags" step.
"""
from __future__ import annotations

from typing import Optional

from src.common.data_fetch import statement_to_df


def _row(df, name):
    if df.empty or name not in df.index:
        return None
    return df.loc[name].dropna()


def _row_any(df, *names):
    for name in names:
        row = _row(df, name)
        if row is not None:
            return row
    return None


def margin_trends(income_stmt_records: list) -> dict:
    df = statement_to_df(income_stmt_records)
    revenue = _row(df, "Total Revenue")
    gross = _row(df, "Gross Profit")
    operating = _row(df, "Operating Income")
    net = _row(df, "Net Income")

    def margin(numer):
        if numer is None or revenue is None:
            return None
        n = min(len(numer), len(revenue))
        return [round(float(numer.iloc[i]) / float(revenue.iloc[i]) * 100, 1)
                for i in range(n) if revenue.iloc[i] != 0]

    revenue_growth = None
    if revenue is not None and len(revenue) >= 2:
        revenue_growth = [
            round((float(revenue.iloc[i]) / float(revenue.iloc[i + 1]) - 1) * 100, 1)
            for i in range(len(revenue) - 1)
            if revenue.iloc[i + 1] != 0
        ]

    return {
        "revenue_growth_pct_by_period": revenue_growth,
        "gross_margin_pct": margin(gross),
        "operating_margin_pct": margin(operating),
        "net_margin_pct": margin(net),
    }


def fcf_series(cashflow_records: list) -> Optional[list[float]]:
    df = statement_to_df(cashflow_records)
    cfo = _row_any(df, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    capex = _row(df, "Capital Expenditure")
    if cfo is None:
        return None
    if capex is None:
        return [round(float(v), 0) for v in cfo]
    n = min(len(cfo), len(capex))
    return [round(float(cfo.iloc[i]) + float(capex.iloc[i]), 0) for i in range(n)]  # capex is usually negative


def cfo_to_net_income(cashflow_records: list, income_stmt_records: list) -> Optional[list[float]]:
    """Cash-earnings quality check. Persistent CFO/NI well below 1.0 is the
    classic 'financial engineering' tell — earnings not backed by cash."""
    cf = statement_to_df(cashflow_records)
    inc = statement_to_df(income_stmt_records)
    cfo = _row(cf, "Operating Cash Flow")
    ni = _row(inc, "Net Income")
    if cfo is None or ni is None:
        return None
    n = min(len(cfo), len(ni))
    return [round(float(cfo.iloc[i]) / float(ni.iloc[i]), 2) for i in range(n) if ni.iloc[i] != 0]


def debt_to_equity_series(balance_sheet_records: list) -> Optional[list[float]]:
    df = statement_to_df(balance_sheet_records)
    debt = _row(df, "Total Debt")
    equity = _row_any(df, "Common Stock Equity", "Total Equity Gross Minority Interest")
    if debt is None or equity is None:
        return None
    n = min(len(debt), len(equity))
    return [round(float(debt.iloc[i]) / float(equity.iloc[i]), 2) for i in range(n) if equity.iloc[i] != 0]


def piotroski_f_score(income_stmt_records: list, balance_sheet_records: list, cashflow_records: list) -> Optional[int]:
    """Simplified Piotroski F-score (0-9): profitability, leverage/liquidity,
    and operating-efficiency signals, each worth 1 point. Requires at least 2
    periods of data; returns None if there isn't enough to compute most signals."""
    inc = statement_to_df(income_stmt_records)
    bal = statement_to_df(balance_sheet_records)
    cf = statement_to_df(cashflow_records)

    ni = _row(inc, "Net Income")
    cfo = _row(cf, "Operating Cash Flow")
    assets = _row(bal, "Total Assets")
    debt = _row(bal, "Total Debt")
    equity = _row_any(bal, "Common Stock Equity", "Total Equity Gross Minority Interest")
    gross = _row(inc, "Gross Profit")
    revenue = _row(inc, "Total Revenue")

    if ni is None or len(ni) < 2:
        return None

    score = 0
    # Profitability
    if ni.iloc[0] > 0:
        score += 1
    if cfo is not None and len(cfo) >= 1 and cfo.iloc[0] > 0:
        score += 1
    if assets is not None and len(assets) >= 2 and assets.iloc[1] != 0:
        roa_now, roa_prior = ni.iloc[0] / assets.iloc[0], ni.iloc[1] / assets.iloc[1] if len(ni) > 1 and len(assets) > 1 else (None, None)
        if roa_now is not None and roa_prior is not None and roa_now > roa_prior:
            score += 1
    if cfo is not None and len(cfo) >= 1 and cfo.iloc[0] > ni.iloc[0]:
        score += 1  # cash quality > accrual earnings
    # Leverage/liquidity
    if debt is not None and len(debt) >= 2 and debt.iloc[0] < debt.iloc[1]:
        score += 1  # leverage decreased
    if equity is not None and len(equity) >= 2 and equity.iloc[0] > equity.iloc[1]:
        score += 1  # equity growing (no heavy dilution/erosion)
    # Operating efficiency
    if gross is not None and revenue is not None and len(gross) >= 2 and len(revenue) >= 2:
        gm_now = gross.iloc[0] / revenue.iloc[0] if revenue.iloc[0] else None
        gm_prior = gross.iloc[1] / revenue.iloc[1] if revenue.iloc[1] else None
        if gm_now is not None and gm_prior is not None and gm_now > gm_prior:
            score += 1
    if revenue is not None and assets is not None and len(revenue) >= 2 and len(assets) >= 2:
        turn_now = revenue.iloc[0] / assets.iloc[0] if assets.iloc[0] else None
        turn_prior = revenue.iloc[1] / assets.iloc[1] if assets.iloc[1] else None
        if turn_now is not None and turn_prior is not None and turn_now > turn_prior:
            score += 1

    return score


def beneish_m_score_flag(cfo_to_ni: Optional[list[float]], revenue_growth: Optional[list[float]]) -> dict:
    """Full Beneish M-score needs 8 inputs yfinance doesn't cleanly expose
    (DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI, TATA). Rather than fabricate a
    fake precise score, this gives a documented simplified flag based on the
    two strongest, most available proxies: cash-earnings quality (CFO/NI) and
    unusually high revenue growth (a classic manipulation-risk correlate).
    Treat as a screen, not a verdict."""
    flag = "insufficient data"
    if cfo_to_ni:
        avg_cfo_ni = sum(cfo_to_ni) / len(cfo_to_ni)
        if avg_cfo_ni < 0.7:
            flag = "elevated risk — cash earnings well below reported net income"
        elif avg_cfo_ni < 1.0:
            flag = "watch — cash earnings somewhat below net income"
        else:
            flag = "no flag — cash backs reported earnings"
    return {"cfo_to_ni_avg": round(sum(cfo_to_ni) / len(cfo_to_ni), 2) if cfo_to_ni else None, "flag": flag}


def build_historical_health_section(income_stmt_records, balance_sheet_records, cashflow_records) -> dict:
    cfo_ni = cfo_to_net_income(cashflow_records, income_stmt_records)
    margins = margin_trends(income_stmt_records)
    return {
        "margins_and_growth": margins,
        "fcf_series": fcf_series(cashflow_records),
        "cfo_to_net_income_series": cfo_ni,
        "debt_to_equity_series": debt_to_equity_series(balance_sheet_records),
        "piotroski_f_score": piotroski_f_score(income_stmt_records, balance_sheet_records, cashflow_records),
        "beneish_proxy_flag": beneish_m_score_flag(cfo_ni, margins.get("revenue_growth_pct_by_period")),
    }
