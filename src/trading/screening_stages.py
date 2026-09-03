"""
Staged screening checklist — Stage 1 (liquidity), Stage 2 (uptrend), Stage 4
(entry trigger). Stage numbering follows the standard Minervini-style
screening pipeline (Stage 1 = tradability, Stage 2 = confirmed uptrend,
Stage 3 = base/pattern quality — covered implicitly by the pivot/consolidation
detection in indicators.find_pivot_breakout rather than broken out as its own
stage here, Stage 4 = entry trigger).

Stage 2 reuses trend_template.py's existing 8-point Trend Template exactly as
is — that function's match_pct is also used by CANSLIM's 'M' check and the
Health Score's market read elsewhere in this project, so it is deliberately
NOT touched here. Liquidity (Stage 1) and Volume Dry-Up (Stage 4) are new,
additive gates layered on top, not folded into the 8-point score.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.trading import indicators as ind
from src.trading import trend_template as tt


def stage1_liquidity(df: pd.DataFrame, cfg: Optional[dict] = None) -> dict:
    """10-day average volume liquidity gate — screens out illiquid names
    prone to wide spreads / slippage on entry-exit."""
    cfg = cfg or {}
    min_avg_volume = cfg.get("min_avg_volume_10d", 350_000)
    window = cfg.get("window_days", 10)

    avg_vol = ind.avg_volume(df, window)
    passed = None if avg_vol is None else avg_vol >= min_avg_volume
    return {
        "avg_volume_10d": round(avg_vol, 0) if avg_vol is not None else None,
        "min_required": min_avg_volume,
        "passed": passed,
    }


def stage4_entry_trigger(df: pd.DataFrame, pivot_info: dict, cfg: Optional[dict] = None) -> dict:
    """Entry-trigger checks: the existing pivot/breakout detector plus the
    new Volume Dry-Up confirmation and the existing up-on-volume ('pocket
    pivot' style) confirmation — grouped together as the Stage 4 read."""
    cfg = cfg or {}
    recent_window = cfg.get("vdu_recent_window_days", 5)
    ma_window = cfg.get("vdu_ma_window_days", 50)
    max_ratio_pct = cfg.get("vdu_max_ratio_pct", 70.0)

    vdu = ind.volume_dry_up(df, recent_window, ma_window, max_ratio_pct)
    volume_confirmed = ind.volume_confirms_move(df)

    return {
        "pivot_price": pivot_info.get("pivot_price"),
        "breakout": pivot_info.get("breakout"),
        "ema_trend": pivot_info.get("ema_trend"),
        "volume_dry_up": vdu,
        "pocket_pivot_volume_confirmed": volume_confirmed,
    }


def build_screening_checklist(
    df: pd.DataFrame,
    cfg: dict,
    rs_value: Optional[float] = None,
    pivot_info: Optional[dict] = None,
) -> dict:
    """Assembles the full staged checklist for one ticker: Stage 1 liquidity,
    Stage 2 uptrend (existing Trend Template), Stage 4 entry trigger (existing
    pivot/breakout + the new VDU check)."""
    trading_cfg = cfg.get("trading", {})
    trend_cfg = trading_cfg.get("trend_template", {})

    stage1 = stage1_liquidity(df, trading_cfg.get("liquidity", {}))
    stage2 = tt.evaluate_all(df, rs_value, {**trend_cfg, "rs_rating_min": trading_cfg.get("rs_rating_min", 70)})
    pivot_info = pivot_info if pivot_info is not None else ind.find_pivot_breakout(df)
    stage4 = stage4_entry_trigger(df, pivot_info, trading_cfg.get("entry_trigger", {}))

    return {
        "stage1_liquidity": stage1,
        "stage2_uptrend": stage2,
        "stage4_entry_trigger": stage4,
    }
