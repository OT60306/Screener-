#!/usr/bin/env python3
"""Scheduled export for external automation (e.g. a Claude coworker reading
results without needing this computer on — see .github/workflows/daily-scan.yml,
which runs this on a cron schedule on GitHub's own runners and commits the
output back to the repo).

Runs the Trading Scanner (System A pattern detection) and the Health
Scorecard leaderboard across the curated watchlist (data/universe.csv — NOT
the full S&P 500 + NASDAQ 100 broad-market pool the interactive app uses for
its own leaderboard, since that's by far the most network-heavy scan in the
app and isn't something to run unattended on a schedule against yfinance)
and writes one combined JSON file any HTTP client can fetch — e.g.
https://raw.githubusercontent.com/<owner>/<repo>/main/data/exports/latest_scan.json

CLI: python scan_export.py [--universe path] [--output path.json]
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.common.config import load_config
from src.common.universe import load_universe
from src.trading.report import scan_universe
from src.value.report import scan_leaderboard


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default=None, help="Path to ticker CSV (defaults to config.yaml's universe_file)")
    parser.add_argument("--output", default="data/exports/latest_scan.json", help="Path to write the combined JSON export")
    args = parser.parse_args()

    cfg = load_config()
    universe_path = args.universe or cfg.get("universe_file", "data/universe.csv")
    tickers = load_universe(universe_path)

    print(f"Scanning {len(tickers)} tickers (watchlist: {universe_path})...")

    trading = scan_universe(tickers, cfg)
    trading_records = trading.to_dict(orient="records")

    leaderboard = scan_leaderboard(tickers, cfg)
    leaderboard_records = leaderboard.to_dict(orient="records")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe_file": universe_path,
        "ticker_count": len(tickers),
        "trading_scan": trading_records,
        "health_leaderboard": leaderboard_records,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"Wrote {len(trading_records)} trading-scan rows + {len(leaderboard_records)} leaderboard rows to {out_path}")


if __name__ == "__main__":
    main()
