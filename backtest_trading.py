#!/usr/bin/env python3
"""
CLI: python backtest_trading.py [--universe path] [--years 10] [--output path.csv]

Backtests the Cup-with-Handle detector (src/trading/patterns/cup_with_handle.py)
over `--years` of weekly history across the scan universe (watchlist + full
S&P 500/NASDAQ-100, same pool the live Trading Scanner uses), and reports the
win rate — this is the gate check before wiring pattern-based entries into
the live scanner (see src/trading/backtest.py's docstring for the exact rules).

First run is slow: pulls `--years` of daily history per ticker (a separate,
long-TTL cache namespace from the live 2y scanner cache — see
get_price_histories_long in src/common/data_fetch.py), so budget real time
for a full-universe run. Use --universe to point at a smaller ticker list
first.
"""
import argparse

from src.common.config import load_config
from src.common.universe import load_universe
from src.common.market_index import get_broad_market_universe
from src.common.data_fetch import get_price_histories_long
from src.trading.backtest import run_backtest, summarize_trades
from src.trading.patterns.cup_with_handle import detect_cup_with_handle
from src.trading.patterns.flat_base import detect_flat_base
from src.trading.patterns.double_bottom import detect_double_bottom
from src.trading.patterns.ascending_base import detect_ascending_base
from src.trading.patterns.high_tight_flag import detect_high_tight_flag

PATTERNS = {
    "cup_with_handle": detect_cup_with_handle,
    "flat_base": detect_flat_base,
    "double_bottom": detect_double_bottom,
    "ascending_base": detect_ascending_base,
    "high_tight_flag": detect_high_tight_flag,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default=None, help="Path to ticker CSV (defaults to watchlist + S&P500/NASDAQ100)")
    parser.add_argument("--years", type=int, default=10, help="Years of history to backtest (default 10)")
    parser.add_argument("--pattern", default="cup_with_handle", choices=list(PATTERNS.keys()))
    parser.add_argument("--output", default=None, help="Optional path to write the full trade log CSV")
    args = parser.parse_args()

    cfg = load_config()

    if args.universe:
        tickers = load_universe(args.universe)
    else:
        watchlist = load_universe(cfg.get("universe_file", "data/universe.csv"))
        broad_market = get_broad_market_universe()
        tickers = sorted(set(watchlist) | set(broad_market))

    print(f"Fetching {args.years}y of history for {len(tickers)} tickers (first run is slow, then cached)...")
    price_data = get_price_histories_long(tickers, years=args.years)
    fetched = sum(1 for df in price_data.values() if df is not None and not df.empty)
    print(f"Got usable history for {fetched}/{len(tickers)} tickers.")

    pattern_cfg = cfg.get("trading", {}).get("weekly", {}).get("patterns", {}).get(args.pattern, {})
    trades = run_backtest(price_data, pattern_cfg, pattern_fn=PATTERNS[args.pattern])

    if trades.empty:
        print("No closed trades found in the backtest window.")
        return

    summary = summarize_trades(trades.to_dict(orient="records"))
    print(f"\n=== {args.pattern} backtest summary ===")
    for k, v in summary.items():
        print(f"{k}: {v}")

    print(f"\nTop 10 trades by return:")
    print(trades.sort_values("return_pct", ascending=False).head(10).to_string(index=False))
    print(f"\nBottom 10 trades by return:")
    print(trades.sort_values("return_pct", ascending=True).head(10).to_string(index=False))

    if args.output:
        trades.to_csv(args.output, index=False)
        print(f"\nWrote full trade log to {args.output}")


if __name__ == "__main__":
    main()
