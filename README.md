# Stock Intel & Health Scorecard

3-page Streamlit app: Market Pulse, Trading Scanner (Minervini/O'Neil), and
Stock Health Scorecard (fundamentals/moat/ecosystem/reverse DCF). Full design
rationale and known limitations are in `CLAUDE.md` — read that first.

## Setup
```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run the app
```bash
streamlit run Home.py
```
Opens at `http://localhost:8501`. Sidebar navigates the 3 pages.

## Run the CLI batch scanners (no browser needed)
```bash
python scan_trading.py            # System A, prints ranked matches
python scan_value.py AAPL          # System B, prints the full health report for one ticker
```

## Run tests
```bash
pytest tests/ -v
```

## What's real vs. what's a placeholder right now
- **Price/volume/fundamentals (yfinance):** live, real.
- **Trend Template, CANSLIM (computable parts), RS Rating, EMA/pivot/breakout:**
  fully implemented, real math over real data.
- **Piotroski F-Score, Beneish M-score proxy, ROIC vs WACC, Reverse DCF:**
  fully implemented — read the docstrings in `src/value/`, some are
  simplified/documented approximations (e.g. Beneish uses 2 of the usual 8
  inputs, since yfinance doesn't expose the rest cleanly).
- **Fear & Greed Index:** an in-house proxy (VIX percentile + SPY momentum +
  breadth), not the official CNN index — there's no free API for that.
- **Macro calendar (NFP, FOMC):** a static list maintained in `config.yaml`,
  not a live economic-calendar feed.
- **Catalysts (news) and customer concentration:** intentionally return
  "not configured" / "not available" rather than fabricated data — no news
  API key is wired in by default. Plug a source into
  `src/value/catalysts_governance.py`'s `news_fn` parameter if you have one.
- **Value-chain layers:** config-driven (`config.yaml` →
  `value.value_chain_layers`) — only a couple of example sectors/tickers are
  pre-filled; extend as you research more companies.

## Network note
This was built and syntax/logic-tested in a sandboxed environment without
internet access, so it could not be run end-to-end against live Yahoo Finance
data here. Every module was checked for compiling correctly, and the pure
(non-network) logic — indicators, Trend Template, reverse DCF math, health
score combination — was verified against synthetic data (see
`tests/test_indicators.py` and the sanity checks in the build notes). Run it
locally with real internet access to pull live data; if something in the
yfinance-dependent paths breaks (Yahoo does change its API occasionally),
check the pinned version in `requirements.txt` first.
