"""
Walk-forward backtest for the Cup-with-Handle detector
(src/trading/patterns/cup_with_handle.py), run via backtest_trading.py.

Runs on WEEKLY bars — O'Neil's own base-reading examples are weekly charts,
the pattern's bar counts (7-65 week cups) are naturally weekly-sized, and a
weekly walk is ~5x cheaper than a daily one over a 10-year window, which
matters when scanning hundreds of tickers.

No look-ahead: at each week i, the detector only ever sees bars [0..i]. A
breakout confirmed as of week i's close is entered at week (i+1)'s open (the
next bar a real trader could actually act in) — never at week i's own close.
Every exit check likewise only uses bars at or after the entry week.

Sell rules encoded (both are explicit, repeated rules across the source PDF
— "cut all losses when down 7% or 8%" and "sell when a stock closes a week
below its 10-week moving-average line... on huge increase in average weekly
volume"):
1. Stop loss: exits at entry_price * (1 - stop_loss_pct) the first week the
   LOW touches that price — modeled as a stop order, not a closing-price exit.
2. Trend break: exits at that week's close the first week Close < 10-week SMA
   AND that week's Volume > its own trailing 10-week average * volume_spike_multiple.
3. Max hold: a safety net so no trade is left open forever in the sample —
   exits at that week's close after `max_hold_weeks`.
A trade still open when the ticker's history runs out is EXCLUDED from the
results (its outcome is unknown, not a loss) rather than mark-to-market'd,
to avoid quietly injecting look-ahead-shaped bias into the win rate.
"""
from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from src.trading import indicators as ind
from src.trading.patterns.cup_with_handle import detect_cup_with_handle

PatternFn = Callable[[pd.DataFrame, Optional[dict]], dict]

DEFAULT_CFG = {
    "stop_loss_pct": 8.0,
    "trend_sma_window": 10,
    "volume_baseline_window": 10,
    "volume_spike_multiple": 1.4,
    "max_hold_weeks": 52,
    "min_bars_before_scan": 68,  # matches the weekly cup lookback_bars default
}


def _simulate_one_entry(df: pd.DataFrame, entry_idx: int, entry_price: float, cfg: dict) -> dict:
    """Walks forward from entry_idx (inclusive) applying the sell rules.
    Returns a trade dict, or {"open": True} if it never exits within `df`."""
    stop_price = entry_price * (1 - cfg["stop_loss_pct"] / 100)
    sma = df["Close"].rolling(cfg["trend_sma_window"]).mean()
    vol_baseline = df["Volume"].rolling(cfg["volume_baseline_window"]).mean().shift(1)
    max_hold = cfg["max_hold_weeks"]

    for j in range(entry_idx, len(df)):
        row = df.iloc[j]
        hold_weeks = j - entry_idx + 1

        if row["Low"] <= stop_price:
            return {
                "exit_idx": j, "exit_date": ind.date_str(df.index[j]), "exit_price": stop_price,
                "exit_reason": "stop_loss", "hold_weeks": hold_weeks,
            }

        sma_j = sma.iloc[j]
        vol_base_j = vol_baseline.iloc[j]
        if pd.notna(sma_j) and pd.notna(vol_base_j) and vol_base_j > 0:
            if row["Close"] < sma_j and row["Volume"] > vol_base_j * cfg["volume_spike_multiple"]:
                return {
                    "exit_idx": j, "exit_date": ind.date_str(df.index[j]), "exit_price": float(row["Close"]),
                    "exit_reason": "trend_break", "hold_weeks": hold_weeks,
                }

        if hold_weeks >= max_hold:
            return {
                "exit_idx": j, "exit_date": ind.date_str(df.index[j]), "exit_price": float(row["Close"]),
                "exit_reason": "max_hold", "hold_weeks": hold_weeks,
            }

    return {"open": True}


def simulate_ticker(
    ticker: str,
    weekly_df: pd.DataFrame,
    pattern_cfg: Optional[dict] = None,
    backtest_cfg: Optional[dict] = None,
    pattern_fn: PatternFn = detect_cup_with_handle,
) -> list[dict]:
    """Walks one ticker's full weekly history looking for `pattern_fn`
    breakouts, simulating one trade per breakout (no pyramiding — the next
    scan resumes only after the current trade closes). `pattern_fn` must
    follow the same contract as detect_cup_with_handle: takes (df, cfg),
    returns a dict with at least "found"/"breakout"/"breakout_volume_confirmed",
    so any detector in src/trading/patterns/ plugs into this same walk-forward
    simulator and sell-rule engine. Returns a list of closed-trade dicts;
    open-at-end-of-history trades are dropped (see module docstring)."""
    cfg = {**DEFAULT_CFG, **(backtest_cfg or {})}
    min_bars = cfg["min_bars_before_scan"]
    trades = []

    if weekly_df is None or len(weekly_df) < min_bars + 2:
        return trades

    i = min_bars
    n = len(weekly_df)
    while i < n - 1:  # need at least one future bar (i+1) to enter on
        window = weekly_df.iloc[: i + 1]
        result = pattern_fn(window, pattern_cfg)
        if result.get("found") and result.get("breakout") and result.get("breakout_volume_confirmed"):
            entry_idx = i + 1
            entry_price = float(weekly_df["Open"].iloc[entry_idx])
            sim = _simulate_one_entry(weekly_df, entry_idx, entry_price, cfg)
            if sim.get("open"):
                break  # trade never closed within available history — stop scanning this ticker
            return_pct = (sim["exit_price"] - entry_price) / entry_price * 100
            trades.append({
                "ticker": ticker,
                "entry_date": ind.date_str(weekly_df.index[entry_idx]),
                "entry_price": round(entry_price, 2),
                "exit_date": sim["exit_date"],
                "exit_price": round(sim["exit_price"], 2),
                "exit_reason": sim["exit_reason"],
                "hold_weeks": sim["hold_weeks"],
                "return_pct": round(return_pct, 2),
                "win": return_pct > 0,
                "pattern_name": result.get("pattern_name"),
                "pattern_depth_pct": result.get("primary_depth_pct"),
            })
            i = sim["exit_idx"] + 1  # resume scanning only after this trade closes
        else:
            i += 1

    return trades


def summarize_trades(trades: list[dict]) -> dict:
    """Aggregate win rate / avg return / profit factor from a flat trade list
    (across however many tickers were backtested)."""
    n = len(trades)
    if n == 0:
        return {"total_trades": 0, "win_rate_pct": None}

    wins = [t for t in trades if t["win"]]
    losses = [t for t in trades if not t["win"]]
    win_rate = len(wins) / n * 100
    avg_win_pct = sum(t["return_pct"] for t in wins) / len(wins) if wins else None
    avg_loss_pct = sum(t["return_pct"] for t in losses) / len(losses) if losses else None
    gross_win = sum(t["return_pct"] for t in wins)
    gross_loss = abs(sum(t["return_pct"] for t in losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None
    avg_hold_weeks = sum(t["hold_weeks"] for t in trades) / n

    exit_reason_counts: dict[str, int] = {}
    for t in trades:
        exit_reason_counts[t["exit_reason"]] = exit_reason_counts.get(t["exit_reason"], 0) + 1

    return {
        "total_trades": n,
        "win_rate_pct": round(win_rate, 1),
        "avg_win_pct": round(avg_win_pct, 2) if avg_win_pct is not None else None,
        "avg_loss_pct": round(avg_loss_pct, 2) if avg_loss_pct is not None else None,
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "avg_hold_weeks": round(avg_hold_weeks, 1),
        "exit_reason_counts": exit_reason_counts,
    }


def run_backtest(
    price_data: dict[str, pd.DataFrame],
    pattern_cfg: Optional[dict] = None,
    backtest_cfg: Optional[dict] = None,
    pattern_fn: PatternFn = detect_cup_with_handle,
) -> pd.DataFrame:
    """`price_data`: {ticker: daily OHLCV df} (already fetched — see
    backtest_trading.py for the long-history fetch). Resamples to weekly and
    simulates every ticker with `pattern_fn` (any detector in
    src/trading/patterns/). Returns a flat DataFrame of closed trades."""
    all_trades: list[dict] = []
    for ticker, daily_df in price_data.items():
        if daily_df is None or daily_df.empty:
            continue
        weekly_df = ind.resample_weekly(daily_df)
        all_trades.extend(simulate_ticker(ticker, weekly_df, pattern_cfg, backtest_cfg, pattern_fn))
    return pd.DataFrame(all_trades)
