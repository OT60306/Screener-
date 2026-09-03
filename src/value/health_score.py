"""
Health Score for the Page 3 Top-15 leaderboard.

Only fully numeric sub-scores go in: historical health (3.2), moat quality
(3.1), reverse-DCF margin-of-safety read (3.4a). Circle of competence,
catalysts text, and governance notes are intentionally excluded — see
CLAUDE.md flag #2. (Ecosystem/value-chain position was retired from this
project — see 3_Health_Scorecard.py.)
"""
from __future__ import annotations

from typing import Optional


def _historical_health_score(historical_section: dict) -> Optional[float]:
    f_score = historical_section.get("piotroski_f_score")
    beneish_flag = historical_section.get("beneish_proxy_flag", {}).get("flag")

    if f_score is None:
        return None
    score = (f_score / 9) * 100

    if beneish_flag == "elevated risk — cash earnings well below reported net income":
        score -= 25
    elif beneish_flag == "watch — cash earnings somewhat below net income":
        score -= 10

    return max(0.0, min(100.0, score))


def _moat_quality_score(fundamental_section: dict) -> Optional[float]:
    mv = fundamental_section.get("moat_verification", {})
    verdict = mv.get("verdict")
    avg_spread = mv.get("avg_spread_pct")

    if verdict is None or verdict == "unknown":
        return None

    base = {
        "strong structural moat": 85,
        "moderate / inconsistent moat": 55,
        "no evidence of durable moat": 25,
    }.get(verdict, 50)

    if avg_spread is not None:
        base += max(-15, min(15, avg_spread))  # nudge by spread magnitude, capped

    return max(0.0, min(100.0, base))


def _reverse_dcf_score(reverse_dcf_section: dict) -> Optional[float]:
    gap = reverse_dcf_section.get("assessment", {}).get("gap_pct")
    if gap is None:
        return None
    # positive gap (market pricing LESS growth than historical) is favorable
    return max(0.0, min(100.0, 50 + gap * 3))


def compute_health_score(
    fundamental_section: dict,
    historical_section: dict,
    reverse_dcf_section: dict,
    weights: dict,
) -> dict:
    subscores = {
        "historical_health": _historical_health_score(historical_section),
        "moat_quality": _moat_quality_score(fundamental_section),
        "reverse_dcf_margin_of_safety": _reverse_dcf_score(reverse_dcf_section),
    }

    available = {k: v for k, v in subscores.items() if v is not None}
    if not available:
        return {"health_score": None, "subscores": subscores, "coverage_pct": 0.0}

    # re-normalize weights over whatever sub-scores are actually available,
    # so a ticker missing one data point isn't unfairly zeroed out
    total_weight = sum(weights.get(k, 0) for k in available)
    if total_weight == 0:
        return {"health_score": None, "subscores": subscores, "coverage_pct": 0.0}

    weighted = sum(available[k] * weights.get(k, 0) for k in available) / total_weight
    coverage_pct = len(available) / len(subscores) * 100

    return {"health_score": round(weighted, 1), "subscores": subscores, "coverage_pct": round(coverage_pct, 1)}
