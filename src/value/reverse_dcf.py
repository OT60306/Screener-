"""
Page 3, section 3.4 — Reverse DCF.

Instead of assuming a growth rate to compute fair value, back-solve for the
growth rate the *current price* already implies, given explicit discount-rate
and terminal-growth assumptions (kept visible, not buried).
"""
from __future__ import annotations

from typing import Optional


def _dcf_value(fcf0: float, growth: float, discount_rate: float, terminal_growth: float, years: int) -> float:
    value = 0.0
    fcf = fcf0
    for year in range(1, years + 1):
        fcf = fcf * (1 + growth)
        value += fcf / ((1 + discount_rate) ** year)
    terminal_fcf = fcf * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    value += terminal_value / ((1 + discount_rate) ** years)
    return value


def implied_growth_rate(
    market_cap: float,
    latest_fcf: float,
    discount_rate: float = 0.10,
    terminal_growth: float = 0.025,
    years: int = 10,
    tolerance: float = 0.001,
) -> Optional[float]:
    """Binary-search the growth rate g such that the DCF value ≈ market cap.
    Returns None if inputs are invalid (e.g. negative/zero FCF — reverse DCF
    isn't meaningful there without adjustment)."""
    if latest_fcf is None or latest_fcf <= 0 or market_cap is None or market_cap <= 0:
        return None

    lo, hi = -0.20, 0.60
    for _ in range(60):
        mid = (lo + hi) / 2
        val = _dcf_value(latest_fcf, mid, discount_rate, terminal_growth, years)
        if abs(val - market_cap) / market_cap < tolerance:
            return round(mid * 100, 2)
        if val < market_cap:
            lo = mid
        else:
            hi = mid
    return round(((lo + hi) / 2) * 100, 2)


def fair_value_per_share(
    latest_fcf: Optional[float],
    growth_pct: Optional[float],
    shares_outstanding: Optional[float],
    discount_rate: float,
    terminal_growth: float,
    years: int,
) -> Optional[float]:
    """Forward DCF (not reverse): what would this business be worth if it
    grows at `growth_pct` (e.g. its own historical CAGR) instead of the
    market-implied rate — expressed per share so it's directly comparable to
    the quoted price."""
    if latest_fcf is None or latest_fcf <= 0 or growth_pct is None or not shares_outstanding:
        return None
    value = _dcf_value(latest_fcf, growth_pct / 100, discount_rate, terminal_growth, years)
    return round(value / shares_outstanding, 2)


def margin_of_safety(implied_growth_pct: Optional[float], historical_growth_pct: Optional[float]) -> dict:
    """Compares what the market is pricing in against what the business has
    actually demonstrated historically. Not a precise 'margin of safety' in
    the classic Graham price-vs-value sense (that needs a growth ASSUMPTION,
    not the implied one) — this instead answers: is the market's implied
    growth reasonable given the track record?"""
    if implied_growth_pct is None:
        return {"verdict": "unavailable", "gap_pct": None}
    if historical_growth_pct is None:
        return {"verdict": "no historical benchmark available", "gap_pct": None}

    gap = historical_growth_pct - implied_growth_pct
    if gap > 5:
        verdict = "market pricing in LESS than historical growth — potentially undervalued if growth persists"
    elif gap < -5:
        verdict = "market pricing in MORE than historical growth — priced for acceleration, higher risk"
    else:
        verdict = "market's implied growth roughly matches historical growth"

    return {"verdict": verdict, "gap_pct": round(gap, 1)}


def build_reverse_dcf_section(
    market_cap: Optional[float],
    latest_fcf: Optional[float],
    historical_revenue_cagr_pct: Optional[float],
    cfg: dict,
    shares_outstanding: Optional[float] = None,
    current_price: Optional[float] = None,
    industry_growth_pct: Optional[float] = None,
) -> dict:
    dcf_cfg = cfg.get("value", {}).get("reverse_dcf", {})
    discount_rate = dcf_cfg.get("discount_rate", 0.10)
    terminal_growth = dcf_cfg.get("terminal_growth", 0.025)
    years = dcf_cfg.get("projection_years", 10)

    implied = implied_growth_rate(market_cap, latest_fcf, discount_rate, terminal_growth, years)
    mos = margin_of_safety(implied, historical_revenue_cagr_pct)

    fv = fair_value_per_share(
        latest_fcf, historical_revenue_cagr_pct, shares_outstanding, discount_rate, terminal_growth, years
    )
    fv_upside_pct = None
    if fv is not None and current_price:
        fv_upside_pct = round((fv / current_price - 1) * 100, 2)

    return {
        "assumptions": {"discount_rate_pct": discount_rate * 100, "terminal_growth_pct": terminal_growth * 100, "years": years},
        "implied_growth_rate_pct": implied,
        "historical_revenue_cagr_pct": historical_revenue_cagr_pct,
        "industry_growth_pct": industry_growth_pct,
        "fair_value_at_historical_cagr": fv,
        "current_price": current_price,
        "fair_value_upside_pct": fv_upside_pct,
        "assessment": mos,
    }
