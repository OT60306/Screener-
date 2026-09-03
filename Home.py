import streamlit as st

from src.common.theme import apply_theme

st.set_page_config(page_title="Stock Intel & Health Scorecard", layout="wide")
apply_theme()

st.title("Stock Intel & Health Scorecard")
st.markdown(
    """
Use the sidebar to navigate:

- **Market Pulse** — Fear & Greed, index charts, macro calendar, market-wide trend health
- **Trading Scanner** — Minervini Trend Template + O'Neil CANSLIM scan, ranked, >80% matches
- **Health Scorecard** — deep fundamental read on one stock + Top 15 healthiest-stocks leaderboard

All data is cached locally (`data/cache/`) with graceful fallback if a source
is unavailable — see `CLAUDE.md` for the full design notes.
"""
)

st.info(
    "First run will populate the cache from yfinance and can take a moment. "
    "If you're offline or yfinance is rate-limited, pages will show cached/'unavailable' "
    "states instead of crashing."
)
