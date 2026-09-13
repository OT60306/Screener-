"""
Static reference stats from the walk-forward backtest run during this
project's development (519 tickers — the full Trading Scanner scan pool —
10 years of weekly bars, see backtest_trading.py / src/trading/backtest.py).
These numbers are NOT live-computed and NOT used to gate or filter anything;
they're shown as context next to a detected pattern so a user can see its
historical batting average at a glance.

None of the 5 patterns tested cleared a 60-70% win-rate threshold (the
original bar for wiring pattern detection into the live scanner as a primary
signal) — win rates settled in a 31-36% band, consistent with these being
trend-following/breakout setups (small, fast-cut losses; occasional large
winners) rather than high-hit-rate setups. Given that, patterns are surfaced
as a SUPPLEMENTARY signal alongside the existing Trend Template/VCP system —
never as a standalone buy trigger and never as an additional filter on the
ranked scan table.

High Tight Flag is intentionally excluded here — only 5 trades turned up
market-wide across the full 10-year sample (consistent with the source PDF's
own "usually only 1 or 2 occurring in a bull market year"), too few to
report a meaningful win rate either way.
"""
BACKTEST_REFERENCE = {
    "cup_with_handle": {"trades": 1849, "win_rate_pct": 35.6, "avg_win_pct": 26.8, "avg_loss_pct": -7.0, "profit_factor": 2.11},
    "double_bottom": {"trades": 572, "win_rate_pct": 31.3, "avg_win_pct": 38.6, "avg_loss_pct": -7.4, "profit_factor": 2.38},
    "ascending_base": {"trades": 457, "win_rate_pct": 35.0, "avg_win_pct": 25.5, "avg_loss_pct": -7.1, "profit_factor": 1.94},
    "flat_base": {"trades": 520, "win_rate_pct": 32.9, "avg_win_pct": 18.7, "avg_loss_pct": -7.2, "profit_factor": 1.27},
    # Only 5 trades market-wide in the 10-year sample — consistent with the
    # PDF's own "usually only 1 or 2 occurring in a bull market year," but far
    # too few to report a meaningful win rate/profit factor either way.
    "high_tight_flag": {"trades": 5, "win_rate_pct": None, "avg_win_pct": None, "avg_loss_pct": -8.0,
                          "profit_factor": None, "insufficient_sample": True},
}
