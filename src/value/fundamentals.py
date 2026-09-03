"""
Page 3, section 3.1 — Fundamental.

Circle of competence is intentionally NOT computed here — it's a manual note
the user answers per ticker (see report.py). Everything else here is a pure
function over yfinance info/financial statements.
"""
from __future__ import annotations

import re
from typing import Optional

from src.common.cache import cached_fetch
from src.common.data_fetch import statement_to_df

COC_AUTO_TTL_HOURS = 24 * 182  # ~6 months — product lineups don't change weekly;
                                 # decoupled from info's own (much shorter) refresh TTL


def classify_revenue_model(info: Optional[dict]) -> str:
    """Heuristic classification from sector/industry/business summary
    keywords — a rough starting label, not a certainty. Best-effort."""
    if not info:
        return "unknown"
    industry = (info.get("industry") or "").lower()
    summary = (info.get("longBusinessSummary") or "").lower()
    text = f"{industry} {summary}"

    if any(k in text for k in ["software", "saas", "subscription", "cloud services"]):
        return "subscription / recurring"
    if any(k in text for k in ["semiconductor", "hardware", "equipment", "foundry"]):
        return "capex-heavy hardware"
    if any(k in text for k in ["advertising", "media", "social"]):
        return "advertising"
    if any(k in text for k in ["bank", "insurance", "financial services"]):
        return "financial services (spread/fee-based)"
    if any(k in text for k in ["retail", "e-commerce", "consumer"]):
        return "transactional / retail"
    if any(k in text for k in ["royalty", "licensing", "intellectual property"]):
        return "licensing"
    return "unclassified — review manually"


def business_description(info: Optional[dict]) -> str:
    """Plain-language "what does this business do" note — pulled from
    yfinance's own business summary (real data), not fabricated. This is the
    factual anchor a user reads before answering the circle-of-competence
    gate themselves."""
    if not info:
        return "No business description available."
    summary = info.get("longBusinessSummary")
    if summary:
        # first 2 sentences is plenty for a scorecard, not the full 10-K bio
        parts = summary.split(". ")
        return ". ".join(parts[:2]).rstrip(".") + "."
    sector = info.get("sector")
    industry = info.get("industry")
    if sector or industry:
        return f"{industry or 'Unclassified'} company in the {sector or 'unclassified'} sector."
    return "No business description available."


def _series_or_none(df, row_name):
    if df.empty or row_name not in df.index:
        return None
    return df.loc[row_name].dropna()


def latest_gross_margin_pct(income_stmt_records: list) -> Optional[float]:
    inc = statement_to_df(income_stmt_records)
    gross = _series_or_none(inc, "Gross Profit")
    revenue = _series_or_none(inc, "Total Revenue")
    if gross is None or revenue is None or len(revenue) == 0 or revenue.iloc[0] == 0:
        return None
    return round(float(gross.iloc[0]) / float(revenue.iloc[0]) * 100, 2)


def roic_series(income_stmt_records: list, balance_sheet_records: list) -> Optional[list[float]]:
    """Approximate ROIC per period = NOPAT / Invested Capital, where
    NOPAT ~= Operating Income * (1 - effective tax rate proxy of 21%), and
    Invested Capital ~= Total Debt + Total Equity - Cash. Best-effort given
    what yfinance exposes; document the approximation in the UI."""
    inc = statement_to_df(income_stmt_records)
    bal = statement_to_df(balance_sheet_records)
    op_income = _series_or_none(inc, "Operating Income")
    equity = _series_or_none(bal, "Common Stock Equity")
    if equity is None:
        equity = _series_or_none(bal, "Total Equity Gross Minority Interest")
    debt = _series_or_none(bal, "Total Debt")
    cash = _series_or_none(bal, "Cash And Cash Equivalents")

    if op_income is None or equity is None:
        return None

    values = []
    for i in range(min(len(op_income), len(equity))):
        nopat = float(op_income.iloc[i]) * 0.79
        d = float(debt.iloc[i]) if debt is not None and i < len(debt) else 0.0
        c = float(cash.iloc[i]) if cash is not None and i < len(cash) else 0.0
        invested_capital = float(equity.iloc[i]) + d - c
        if invested_capital > 0:
            values.append(nopat / invested_capital * 100)
    return values or None


def moat_verification(roic_values: Optional[list[float]], wacc_pct: float = 8.0) -> dict:
    """Structural moat = ROIC sustained above WACC across multiple years, not
    one good year. wacc_pct defaults to a generic 8% — replace with a real
    per-company WACC estimate when available."""
    if not roic_values:
        return {"verdict": "unknown", "years_above_wacc": None, "avg_spread_pct": None}

    spreads = [r - wacc_pct for r in roic_values]
    years_above = sum(1 for s in spreads if s > 0)
    avg_spread = sum(spreads) / len(spreads)

    if years_above == len(spreads) and avg_spread > 5:
        verdict = "strong structural moat"
    elif years_above >= len(spreads) * 0.6:
        verdict = "moderate / inconsistent moat"
    else:
        verdict = "no evidence of durable moat"

    return {
        "verdict": verdict,
        "years_above_wacc": years_above,
        "years_evaluated": len(spreads),
        "avg_spread_pct": round(avg_spread, 2),
        "latest_roic_pct": round(roic_values[0], 2),
        "wacc_pct": wacc_pct,
    }


def _moat_narrative(moat: dict, gross_margin_pct: Optional[float]) -> str:
    if moat.get("verdict") in (None, "unknown"):
        return "Not enough financial history to evaluate ROIC vs. WACC."
    roic = moat.get("latest_roic_pct")
    wacc = moat.get("wacc_pct")
    gm = f", gross margin {gross_margin_pct:.2f}%" if gross_margin_pct is not None else ""
    comparison = "above" if roic is not None and wacc is not None and roic > wacc else "below"
    return (
        f"Latest ROIC {roic:.2f}% {comparison} WACC {wacc:.2f}%{gm} — "
        f"{moat['verdict']} ({moat.get('years_above_wacc')}/{moat.get('years_evaluated')} years above WACC)."
    )


def _split_list_fragment(fragment: str) -> list[str]:
    """'A, B, and C' / 'A; and B' -> ['A', 'B', 'C'], filtering out fragments
    that are too long to be a product/segment name (a sign the regex grabbed
    prose, not a list). A 2-item fragment with no comma ('Powerwall and
    Megapack') is split on a bare ' and ' too, as long as both halves stay
    short — long halves usually mean it's a descriptive clause, not a pair of
    names."""
    fragment = re.sub(r"\s*;\s*and\s+", ", ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"\s*,\s*and\s+", ", ", fragment, flags=re.IGNORECASE)
    items = []
    for part in re.split(r",|;", fragment):
        part = re.sub(r"^\s*(and|the|including)\s+", "", part.strip(" ."), flags=re.IGNORECASE).strip()
        if not part:
            continue
        words = part.split()
        if len(words) > 5 and " and " in part.lower():
            halves = re.split(r"\s+and\s+", part, maxsplit=1, flags=re.IGNORECASE)
            if len(halves) == 2 and all(1 <= len(h.split()) <= 4 for h in halves):
                items.extend(h.strip() for h in halves)
                continue
        if 1 <= len(words) <= 5:
            items.append(part)
    return items


# Checked in priority order against yfinance's longBusinessSummary: an
# explicit brand list ("... under the X, Y brands") or product list
# ("products such as X, Y") is closer to "flagship products" than a generic
# reported business-segment list, so those are tried first; segments are the
# fallback every company's summary reliably has — in either of the two ways
# it's commonly phrased ("operates in three segments: A, B, C" vs.
# "operates through A and B segments").
_PRODUCT_PATTERNS = [
    r"under the\s+([^.]+?)\s+brands?\.",
    r"products?,?\s+such as\s+([^.]+?)\.",
    r"operates?\s+(?:in|through)\s+\w+\s+segments?[,:]\s+([^.]+?)\.",
    r"operates?\s+(?:in|through)\s+([^.]+?)\s+segments?\.",
]


def _auto_products_from_summary(summary: Optional[str]) -> list[str]:
    """Best-effort auto-extraction of flagship products/segments from
    yfinance's own business summary — no fabrication, just pattern-matching
    real sentences. Quality varies by how a given company's summary is
    written; a config.yaml override (circle_of_competence_products) always
    takes priority when present. Label this as auto-extracted in the UI."""
    if not summary:
        return []
    for pattern in _PRODUCT_PATTERNS:
        match = re.search(pattern, summary, re.IGNORECASE)
        if match:
            items = _split_list_fragment(match.group(1))
            if items:
                return items[:6]
    return []


def circle_of_competence_products(ticker: str, cfg: Optional[dict], info: Optional[dict] = None) -> dict:
    """Flagship/strongest products for this ticker. A curated entry in
    config.yaml (value.circle_of_competence_products) always wins when
    present — that's hand-verified and matches the exact product names a
    user would recognize, and is never overwritten by this function (config
    stays a hand-edited file, not a write target for the app).

    Otherwise this auto-extracts from the company's own yfinance business
    summary (see _auto_products_from_summary), same as any other external
    data in this project: fetched through the disk cache with its own TTL —
    here ~6 months, since product lineups don't change week to week and we
    don't want the list churning every time `info` itself refreshes."""
    if cfg:
        mapping = cfg.get("value", {}).get("circle_of_competence_products", {})
        curated = mapping.get(ticker.upper())
        if curated:
            return {"items": curated, "source": "curated"}

    def fetch():
        return _auto_products_from_summary(info.get("longBusinessSummary") if info else None)

    try:
        auto, _fresh = cached_fetch("value/fundamentals", f"coc_auto_{ticker.upper()}", COC_AUTO_TTL_HOURS, fetch)
    except Exception:
        auto = []
    return {"items": auto, "source": "auto" if auto else "none"}


def build_fundamental_section(
    info: Optional[dict],
    income_stmt_records: list,
    balance_sheet_records: list,
    wacc_pct: float = 8.0,
    ticker: str = "",
    cfg: Optional[dict] = None,
) -> dict:
    roic_vals = roic_series(income_stmt_records, balance_sheet_records)
    moat = moat_verification(roic_vals, wacc_pct)
    gross_margin_pct = latest_gross_margin_pct(income_stmt_records)
    return {
        "business_description": business_description(info),
        "circle_of_competence_products": circle_of_competence_products(ticker, cfg, info),
        "revenue_model": classify_revenue_model(info),
        "roic_series_pct": roic_vals,
        "gross_margin_pct": gross_margin_pct,
        "moat_verification": moat,
        "moat_narrative": _moat_narrative(moat, gross_margin_pct),
        "circle_of_competence_note": "Manual — answer per ticker in the UI, not scored.",
    }
