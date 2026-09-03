#!/usr/bin/env python3
"""CLI: python scan_value.py TICKER [--output report.md]"""
import argparse
import json

from src.common.config import load_config
from src.value.report import build_stock_health_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--output", default=None, help="Optional path to write JSON report")
    args = parser.parse_args()

    cfg = load_config()
    report = build_stock_health_report(args.ticker.upper(), cfg)

    # price_history is a DataFrame — drop it from console/JSON output
    printable = {k: v for k, v in report.items() if k != "price_history"}

    print(json.dumps(printable, indent=2, default=str))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(printable, f, indent=2, default=str)
        print(f"\nWrote report to {args.output}")


if __name__ == "__main__":
    main()
