"""
VCP (Volatility Contraction Pattern) analysis — Minervini-style base
detection, added to Stage 4 (Entry Trigger & VCP Quality) alongside the
existing pivot/breakout and Volume Dry-Up checks.

This is a geometric best-effort approximation of manual VCP counting, not a
reproduction of any specific charting tool's algorithm: contractions are
found via a ZigZag swing detector (a documented, standard technique — a new
swing point confirms once price reverses by at least a % threshold from the
last extreme), not hand-drawn trendlines. A ZigZag is used rather than a
fixed day-count window specifically because VCP waves get shorter in
duration as they tighten — a fixed window misses the later, tighter waves a
%-based reversal threshold still catches. Exact wave counts can differ from
a human chartist's read — treat the contraction count and depths as
directional, not authoritative.

Five things this adds beyond the existing Stage 4 checks:
1. Contraction count + per-wave depth %, and whether depths are
   progressively tightening (1T/2T/3T-style read) — built by walking the
   swing legs forward and enforcing Minervini's structural rules (see
   `detect_contractions`), not just trimming a trailing tightening run.
2. Contraction-count validation: 1 wave is a plain pullback (not a VCP base
   yet), 2-4 waves is the standard range, 5 is a long-but-acceptable base,
   and 6+ waves means the base has gone on too long / is too loose to trust.
3. Volume Dry-Up measured specifically in the FINAL contraction (not just a
   trailing N-day window) — VCP requires supply to dry up tightest right
   before the breakout, threshold <=50% of the 50-day average (stricter
   than the general Stage 4 VDU's <=70%) — plus a final-contraction depth
   check (tight <=10%, ideally <=5% — the last wave into a breakout should
   be a very tight, dried-up squeeze, same ~9-10% ceiling applied to a cup's
   handle and a double bottom's post-low2 leg in src/trading/patterns/).
4. RS Line new-high check: stock price relative to a benchmark (SPY),
   distinct from the numeric 1-99 RS Rating used elsewhere — a market
   leader's RS Line should be making new highs alongside (or ahead of) price.
5. Pivot = the final contraction's high, with breakout-day volume
   confirmation at >1.5x the 50-day average (stricter than the general
   Stage 4 pocket-pivot confirmation's 1.4x).

## Structural rules enforced by `detect_contractions` (Minervini price structure)

**Low side (the most important rule):** each contraction's low must be a
Higher Low than the low before it. A Lower Low is a strict violation — it
invalidates the base being built (the base up to that point either failed or
was never a real VCP), so the count resets and that leg becomes the new
starting contraction (C1) of a fresh base.

**High side:** an Equal High (retest of the same resistance) or a Lower High
(supply fading, base compressing into a triangle/wedge shape) are both fine.
A Higher High set *during* base formation is not allowed to extend the
existing count — if price pushes above the prior high and can't hold,
rolling back over into a deep pullback, that pullback is not counted as the
next contraction of the old base; the new high resets the count and starts a
fresh C1 instead.

Both resets mean `detect_contractions` returns only the trailing run of legs
that is internally consistent by these two rules — i.e. the base actually
being built right now, not the stock's entire multi-month swing history.

**Count validation** (`classify_contraction_count`) and **final-contraction
tightness** (`final_contraction_tightness`) are then applied to that trailing
run — see their docstrings.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.trading.indicators import find_swings as _find_swings
from src.trading.indicators import date_str as _date_str


def detect_contractions(
    df: pd.DataFrame,
    lookback_days: int = 130,
    zigzag_pct_threshold: float = 8.0,
    tightening_tolerance_pct: float = 3.0,
    equal_high_tolerance_pct: float = 2.0,
    higher_low_buffer_pct: float = 0.5,
) -> list[dict]:
    """Finds every high->low swing leg within the trailing `lookback_days`,
    then walks them forward enforcing Minervini's two structural rules,
    keeping only the TRAILING run that is currently intact:

    - **No Lower Low**: a leg whose low sits below the previous contraction's
      low (beyond `higher_low_buffer_pct`, a small buffer for float/tick
      noise) invalidates everything built so far. The base resets and that
      leg becomes the new C1.
    - **No Higher High during base formation**: a leg whose high sits above
      the previous contraction's high (beyond `equal_high_tolerance_pct`,
      which is what allows a same-level retest to still count as an Equal
      High) means price broke out of the base shape and rolled over — that
      leg is not the next wave of the old base, it resets the count and
      becomes the new C1 instead. A Lower High or Equal High is always fine
      and simply continues the count.

    This is deliberately not "every contraction since the base's origin
    peak": VCP wave counting is about the recent structure right before a
    possible breakout, not a stock's entire multi-month swing history — a
    volatile name can have many legs over months without ever forming a
    proper base, and only the trailing run that hasn't been invalidated by
    either rule is what actually matters for a breakout call."""
    if df is None or df.empty or len(df) < 20:
        return []
    window_df = df.tail(lookback_days)
    swings = _find_swings(window_df, zigzag_pct_threshold)
    if len(swings) < 2:
        return []

    all_legs = []
    for i in range(len(swings) - 1):
        a, b = swings[i], swings[i + 1]
        if a["type"] == "high" and b["type"] == "low" and a["price"] > 0:
            depth_pct = (a["price"] - b["price"]) / a["price"] * 100
            all_legs.append({
                "high": round(a["price"], 2), "high_date": _date_str(a["date"]), "high_idx": a["idx"],
                "low": round(b["price"], 2), "low_date": _date_str(b["date"]), "low_idx": b["idx"],
                "depth_pct": round(depth_pct, 2),
            })
    if not all_legs:
        return []

    base: list[dict] = [dict(all_legs[0])]
    for leg in all_legs[1:]:
        prev = base[-1]
        is_lower_low = leg["low"] < prev["low"] * (1 - higher_low_buffer_pct / 100)
        is_higher_high = leg["high"] > prev["high"] * (1 + equal_high_tolerance_pct / 100)
        if is_lower_low or is_higher_high:
            # Pattern invalidated (Lower Low) or price broke out and failed
            # to hold (Higher High mid-base) — this leg starts a fresh base.
            base = [dict(leg)]
        else:
            base.append(dict(leg))

    for i, leg in enumerate(base):
        leg["wave"] = i + 1
    return base


def is_progressive_tightening(contractions: list[dict], tolerance_pct: float = 3.0) -> Optional[bool]:
    """True if each successive contraction's depth % is smaller than the
    previous one (allowing a small tolerance for near-ties). This is a
    quality read on the trailing run `detect_contractions` already built
    (which enforces the HL/no-HH structural rules) — a base can be
    structurally valid by those rules yet still not be tightening well."""
    if len(contractions) < 2:
        return None
    depths = [c["depth_pct"] for c in contractions]
    return all(depths[i + 1] <= depths[i] + tolerance_pct for i in range(len(depths) - 1))


def contraction_count_label(contractions: list[dict]) -> str:
    n = len(contractions)
    return f"{n}T" if n else "none detected"


def classify_contraction_count(
    contractions: list[dict], standard_max: int = 4, loose_threshold: int = 5
) -> dict:
    """Validates the wave count itself, per Minervini's guidance:
    - 0 waves: no contraction structure detected at all.
    - 1 wave (1T): just an ordinary pullback — not a VCP base yet.
    - 2-4 waves (2T-4T): the standard, tradeable range.
    - exactly `loose_threshold` (default 5T): a long base — still usable but
      flag it as running long.
    - more than `loose_threshold`: the base has been forming too long / is
      too loose to trust — skip the trade.
    """
    n = len(contractions)
    if n == 0:
        return {"count": 0, "label": "none detected", "classification": "no_contraction"}
    if n == 1:
        return {"count": 1, "label": "1T", "classification": "pullback_only"}
    if n > loose_threshold:
        return {"count": n, "label": f"{n}T", "classification": "too_loose"}
    if n == loose_threshold:
        return {"count": n, "label": f"{n}T", "classification": "long_base"}
    return {"count": n, "label": f"{n}T", "classification": "valid_vcp"}


def final_contraction_tightness(
    contractions: list[dict], tight_max_pct: float = 10.0, ideal_max_pct: float = 5.0
) -> dict:
    """The last contraction going into a breakout should be the tightest one
    in the base — pass at <=10% depth (the final wave should be a very tight
    squeeze, not just "smaller than before"), with <=5% considered the
    ideal, tightest-possible setup."""
    if not contractions:
        return {"depth_pct": None, "is_tight_enough": None, "is_ideal": None}
    depth = contractions[-1]["depth_pct"]
    return {
        "depth_pct": depth,
        "is_tight_enough": bool(depth <= tight_max_pct),
        "is_ideal": bool(depth <= ideal_max_pct),
    }


def final_contraction_vdu(
    window_df: pd.DataFrame, contractions: list[dict], ma_window: int = 50, max_ratio_pct: float = 50.0
) -> dict:
    """Volume during the final contraction's high-to-low window vs. the
    50-day average. VCP wants the deepest dry-up right in the last, tightest
    wave — stricter (<=50%) than the general Stage 4 VDU check (<=70%)."""
    if not contractions or window_df is None or len(window_df) < ma_window:
        return {"ratio_pct": None, "is_vdu": None}
    ma_vol = window_df["Volume"].tail(ma_window).mean()
    if ma_vol <= 0:
        return {"ratio_pct": None, "is_vdu": None}
    last = contractions[-1]
    segment = window_df["Volume"].iloc[last["high_idx"]: last["low_idx"] + 1]
    if segment.empty:
        return {"ratio_pct": None, "is_vdu": None}
    ratio_pct = float(segment.mean() / ma_vol * 100)
    return {"ratio_pct": round(ratio_pct, 2), "is_vdu": bool(ratio_pct <= max_ratio_pct)}


def breakout_volume_confirmed(df: pd.DataFrame, multiple: float = 1.5, ma_window: int = 50) -> Optional[bool]:
    """Latest day's volume vs. its 50-day average — VCP's breakout
    confirmation threshold (1.5x) is stricter than the general Stage 4
    pocket-pivot check (1.4x)."""
    if df is None or len(df) < ma_window + 1:
        return None
    avg_vol = df["Volume"].tail(ma_window).mean()
    if avg_vol <= 0:
        return None
    return bool(df["Volume"].iloc[-1] > avg_vol * multiple)


def rs_line_new_high(
    df: pd.DataFrame, benchmark_df: Optional[pd.DataFrame], lookback_days: int = 252, near_high_tolerance_pct: float = 1.0
) -> Optional[bool]:
    """RS Line = stock price / benchmark price, a distinct read from the
    numeric 1-99 RS Rating: a market leader's RS Line should itself be at or
    near a new high, showing the stock outperforming the benchmark, not just
    outperforming a peer-ranked percentile. `near_high_tolerance_pct` treats
    "at" the high as within that %, not requiring an exact tick."""
    if df is None or benchmark_df is None or df.empty or benchmark_df.empty:
        return None
    merged = pd.DataFrame({"stock": df["Close"], "bench": benchmark_df["Close"]}).dropna()
    if len(merged) < 60:
        return None
    rs_line = (merged["stock"] / merged["bench"]).tail(lookback_days)
    high = rs_line.max()
    if high <= 0:
        return None
    return bool(rs_line.iloc[-1] >= high * (1 - near_high_tolerance_pct / 100))


def vcp_analysis(
    df: pd.DataFrame,
    benchmark_df: Optional[pd.DataFrame],
    rs_value: Optional[float],
    cfg: Optional[dict] = None,
) -> dict:
    cfg = cfg or {}
    lookback_days = cfg.get("lookback_days", 130)
    zigzag_pct_threshold = cfg.get("zigzag_pct_threshold", 8.0)
    tightening_tolerance_pct = cfg.get("tightening_tolerance_pct", 3.0)
    equal_high_tolerance_pct = cfg.get("equal_high_tolerance_pct", 2.0)
    higher_low_buffer_pct = cfg.get("higher_low_buffer_pct", 0.5)
    vdu_max_ratio_pct = cfg.get("final_contraction_vdu_max_ratio_pct", 50.0)
    final_tight_max_pct = cfg.get("final_contraction_tight_max_pct", 10.0)
    final_ideal_max_pct = cfg.get("final_contraction_ideal_max_pct", 5.0)
    standard_max_count = cfg.get("standard_max_contractions", 4)
    loose_count_threshold = cfg.get("loose_base_contraction_threshold", 5)
    breakout_vol_multiple = cfg.get("breakout_volume_multiple", 1.5)
    rs_line_lookback_days = cfg.get("rs_line_lookback_days", 252)
    market_leader_rs_min = cfg.get("market_leader_rs_min", 90)
    vdu_ma_window = cfg.get("vdu_ma_window", 50)

    if df is None or df.empty:
        return {
            "contractions": [], "contraction_count_label": "no data", "progressive_tightening": None,
            "count_validation": {"count": 0, "label": "no data", "classification": "no_contraction"},
            "final_contraction_tightness": {"depth_pct": None, "is_tight_enough": None, "is_ideal": None},
            "final_contraction_vdu": {"ratio_pct": None, "is_vdu": None}, "pivot_price": None,
            "breakout": None, "breakout_volume_confirmed": None, "rs_line_new_high": None,
            "rs_rating": rs_value, "market_leader": None,
        }

    window_df = df.tail(lookback_days)
    contractions = detect_contractions(
        df, lookback_days, zigzag_pct_threshold, tightening_tolerance_pct,
        equal_high_tolerance_pct, higher_low_buffer_pct,
    )
    tightening = is_progressive_tightening(contractions, tightening_tolerance_pct)
    count_validation = classify_contraction_count(contractions, standard_max_count, loose_count_threshold)
    tightness = final_contraction_tightness(contractions, final_tight_max_pct, final_ideal_max_pct)
    vdu = final_contraction_vdu(window_df, contractions, vdu_ma_window, vdu_max_ratio_pct)

    pivot_price = contractions[-1]["high"] if contractions else None
    latest_close = float(df["Close"].iloc[-1])
    breakout = bool(pivot_price is not None and latest_close >= pivot_price)
    breakout_vol = breakout_volume_confirmed(df, breakout_vol_multiple, vdu_ma_window) if breakout else None

    return {
        "contractions": contractions,
        "contraction_count_label": contraction_count_label(contractions),
        "progressive_tightening": tightening,
        "count_validation": count_validation,
        "final_contraction_tightness": tightness,
        "final_contraction_vdu": vdu,
        "pivot_price": pivot_price,
        "breakout": breakout,
        "breakout_volume_confirmed": breakout_vol,
        "rs_line_new_high": rs_line_new_high(df, benchmark_df, rs_line_lookback_days),
        "rs_rating": rs_value,
        "market_leader": (rs_value >= market_leader_rs_min) if rs_value is not None else None,
    }
