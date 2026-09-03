#!/usr/bin/env python3
"""CLI: python scan_trading.py [--universe path] [--output path.csv]"""
import argparse

from src.common.config import load_config
from src.common.universe import load_universe
from src.trading.report import scan_universe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default=None, help="Path to ticker CSV (defaults to config.yaml's universe_file)")
    parser.add_argument("--output", default=None, help="Optional path to write results CSV")
    args = parser.parse_args()

    cfg = load_config()
    universe_path = args.universe or cfg.get("universe_file", "data/universe.csv")
    tickers = load_universe(universe_path)

    print(f"Scanning {len(tickers)} tickers...")
    results = scan_universe(tickers, cfg)

    min_match = cfg.get("trading", {}).get("match_score_display_min", 80)
    display_cols = ["ticker", "match_pct", "rs_rating", "breakout", "ema_trend", "last_close"]
    print(results[display_cols].to_string(index=False))

    passing = results[results["match_pct"] >= min_match] if "match_pct" in results.columns else results
    print(f"\n{len(passing)} tickers scoring >= {min_match}%")

    if args.output:
        results.to_csv(args.output, index=False)
        print(f"Wrote full results to {args.output}")


if __name__ == "__main__":
    main()
