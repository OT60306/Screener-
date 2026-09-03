from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd


def load_universe(path: str) -> List[str]:
    """Loads a ticker list from a CSV with a 'ticker' column. Falls back to a
    small built-in demo list if the file doesn't exist yet, so the app runs
    out of the box before the user supplies their own universe."""
    p = Path(path)
    if p.exists():
        df = pd.read_csv(p)
        col = "ticker" if "ticker" in df.columns else df.columns[0]
        return [str(t).strip().upper() for t in df[col].dropna().tolist()]

    return [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO",
        "TSM", "AMD", "CRM", "NOW", "PLTR", "VST", "CEG",
    ]
