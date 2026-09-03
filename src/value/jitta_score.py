"""
Page 3, section 3.2 — "Jitta Score" proxy.

There's no free API for the real Jitta Score (jitta.com's proprietary
long-term-fundamentals rating) — same situation as CNN's Fear & Greed Index
and IBD's RS Rating elsewhere in this project, so this follows the same
pattern: an in-house, clearly-labeled proxy, not a reproduction.

Where Piotroski (financial_flow.py) reads as a short-term, year-over-year
signal, this is meant to complement it with a longer-horizon read: growth
consistency, profitability durability, cash-generation strength, and
financial-strength trend, blended across whatever multi-year history is
available.

Important limitation, stated up front: Jitta's own methodology looks back up
to 10 years. yfinance's free annual statements (.financials / .balance_sheet
/ .cashflow) typically expose only ~4 years, not 10 — there is no free data
source in this project's stack that goes deeper. This proxy uses whatever
years actually come back and reports how many that was, so the UI can be
honest about the shorter window instead of implying a 10-year read it can't
actually do.
"""
from __future__ import annotations

from typing import Optional


def _clip(value: float) -> float:
    return max(0.0, min(100.0, value))


def _growth_consistency_score(revenue_growth_pct_by_period: Optional[list[float]]) -> Optional[float]:
    """Rewards growing revenue in most available years (consistency) over a
    single strong year (magnitude), which is closer to what a 10-year
    long-term read is trying to capture than a single YoY figure."""
    if not revenue_growth_pct_by_period:
        return None
    growth = revenue_growth_pct_by_period
    consistency_pct = sum(1 for g in growth if g > 0) / len(growth) * 100
    avg_growth = sum(growth) / len(growth)
    magnitude_score = _clip(50 + avg_growth * 2)
    return _clip(consistency_pct * 0.5 + magnitude_score * 0.5)


def _profitability_durability_score(moat_verification: Optional[dict]) -> Optional[float]:
    """Reuses 3.1's ROIC vs. WACC read — years above WACC / years evaluated
    is itself a multi-year durability signal, exactly the kind of thing a
    long-term score should weight more than a single year's ROIC."""
    if not moat_verification:
        return None
    years_evaluated = moat_verification.get("years_evaluated")
    years_above = moat_verification.get("years_above_wacc")
    if not years_evaluated:
        return None
    persistence_pct = (years_above or 0) / years_evaluated * 100
    spread_score = _clip(50 + (moat_verification.get("avg_spread_pct") or 0) * 2)
    return _clip(persistence_pct * 0.6 + spread_score * 0.4)


def _cash_generation_score(fcf_series: Optional[list[float]]) -> Optional[float]:
    """% of available years with positive free cash flow — a business that
    only occasionally generates cash isn't demonstrating the sustained
    strength a long-term score should reward."""
    if not fcf_series:
        return None
    positive = sum(1 for v in fcf_series if v is not None and v > 0)
    return _clip(positive / len(fcf_series) * 100)


def _financial_strength_trend_score(debt_to_equity_series: Optional[list[float]]) -> Optional[float]:
    """Lower D/E is stronger; an improving (declining) trend across the
    available years is worth more than a single snapshot."""
    if not debt_to_equity_series:
        return None
    latest = debt_to_equity_series[0]
    level_score = _clip(100 - latest * 40)
    if len(debt_to_equity_series) < 2:
        return level_score
    oldest = debt_to_equity_series[-1]
    trend_bonus = max(-20.0, min(20.0, (oldest - latest) * 20))
    return _clip(level_score * 0.7 + 50 * 0.3 + trend_bonus * 0.3 - 15)


def _label(score_out_of_10: float) -> str:
    if score_out_of_10 >= 7.5:
        return "Strong long-term fundamentals"
    if score_out_of_10 >= 5.0:
        return "Solid, above-average"
    if score_out_of_10 >= 2.5:
        return "Mixed / below-average"
    return "Weak long-term fundamentals"


def compute_jitta_score_proxy(fundamental_section: dict, historical_section: dict) -> dict:
    """Sub-scores are computed on an internal 0-100 scale (each is naturally
    a percentage — growth-consistency %, WACC-persistence %, etc.), then the
    final blended score is rescaled to 0-10 to match the real Jitta Score's
    own scale, which jitta.com displays as e.g. "7.5", not "75"."""
    margins = historical_section.get("margins_and_growth", {})
    subscores = {
        "growth_consistency": _growth_consistency_score(margins.get("revenue_growth_pct_by_period")),
        "profitability_durability": _profitability_durability_score(fundamental_section.get("moat_verification")),
        "cash_generation_strength": _cash_generation_score(historical_section.get("fcf_series")),
        "financial_strength_trend": _financial_strength_trend_score(historical_section.get("debt_to_equity_series")),
    }
    weights = {
        "growth_consistency": 0.30,
        "profitability_durability": 0.30,
        "cash_generation_strength": 0.25,
        "financial_strength_trend": 0.15,
    }

    years_used = max(
        (len(v) for v in (
            margins.get("revenue_growth_pct_by_period"),
            historical_section.get("fcf_series"),
            historical_section.get("debt_to_equity_series"),
        ) if v),
        default=0,
    )

    available = {k: v for k, v in subscores.items() if v is not None}
    if not available:
        return {"jitta_score_proxy": None, "subscores": subscores, "coverage_pct": 0.0,
                 "years_used": years_used, "label": "unavailable"}

    total_weight = sum(weights[k] for k in available)
    score_out_of_100 = sum(available[k] * weights[k] for k in available) / total_weight
    score_out_of_10 = round(score_out_of_100 / 10, 2)
    coverage_pct = round(len(available) / len(subscores) * 100, 2)

    return {
        "jitta_score_proxy": score_out_of_10,
        "subscores": {k: (round(v, 2) if v is not None else None) for k, v in subscores.items()},
        "coverage_pct": coverage_pct,
        "years_used": years_used,
        "label": _label(score_out_of_10),
    }
