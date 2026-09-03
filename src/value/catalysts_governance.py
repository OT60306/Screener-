"""
Page 3, section 3.4 — Recent Catalysts & Governance.

This is the ONE place in System B where a news/LLM step could plug in — and
exactly like the Gemini lesson that started this whole rebuild, it must be
optional, isolated, and never block the rest of Page 3 if it fails or a quota
runs out. No news API key is wired in by default; this returns a clear
"not configured" state rather than fabricating catalysts.
"""
from __future__ import annotations

from typing import Optional


def get_catalysts(ticker: str, news_fn: Optional[callable] = None) -> dict:
    """news_fn: optional callable(ticker) -> list[dict] plugged in by the
    caller (e.g. a news API or an LLM-with-search step). Left unset by
    default so this never silently depends on a paid/quota-limited service."""
    if news_fn is None:
        return {"items": [], "status": "not configured — plug a news source into news_fn"}
    try:
        items = news_fn(ticker)
        return {"items": items, "status": "ok"}
    except Exception as exc:
        return {"items": [], "status": f"fetch failed: {exc}"}


def get_governance(info: Optional[dict]) -> dict:
    """Best-effort governance snapshot from yfinance's info payload. Optional
    section (flagged in CLAUDE.md as not originally in the latest spec) —
    kept because it's nearly free given info is already fetched for 3.1."""
    if not info:
        return {"status": "unavailable"}
    return {
        "insider_ownership_pct": round(info.get("heldPercentInsiders", 0) * 100, 2) if info.get("heldPercentInsiders") is not None else None,
        "institutional_ownership_pct": round(info.get("heldPercentInstitutions", 0) * 100, 2) if info.get("heldPercentInstitutions") is not None else None,
        "payout_ratio": info.get("payoutRatio"),
        "status": "ok",
    }


def build_catalysts_governance_section(ticker: str, info: Optional[dict], news_fn: Optional[callable] = None) -> dict:
    return {
        "catalysts": get_catalysts(ticker, news_fn),
        "governance": get_governance(info),
    }
