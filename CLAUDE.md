# CLAUDE.md — Stock Intel & Health Scorecard

## Why this project was restarted
The previous version called the Gemini API for **both data fetching and analysis**.
That coupled the core logic to a paid/rate-limited LLM API, so it broke the
moment the quota ran out.

**Core architectural decision for this rebuild: no hard external-API
dependency in any critical path** — not just LLMs. This project now pulls
from *several* external sources (yfinance, a Fear & Greed source, a macro
calendar source, news for catalysts). Every one of them gets the same
treatment: cached, wrapped in a fallback, and never allowed to take down a
page that doesn't strictly need it.

## Product: 3-page app
This is a Streamlit (or equivalent) multi-page dashboard, not just CLIs. Pages:

| Page | Purpose | Backend |
|---|---|---|
| 1. Market Pulse (home) | Overall market condition: Fear & Greed, index charts, macro calendar (NFP, FOMC), market-level Minervini/O'Neil read | `src/market/` |
| 2. Trading Scanner | Score every stock in the universe against Minervini/O'Neil, show only >80% matches, ranked; click a stock for chart + matched criteria + entry point; link to Page 3 | `src/trading/` (System A) |
| 3. Stock Health Scorecard | Deep fundamental read on one stock (Fundamental / Historical Health / Ecosystem / Reverse DCF & Catalysts) + Top 15 healthiest-stocks leaderboard | `src/value/` (System B) |

**Navigation:** Page 2's stock detail links straight into Page 3 with the same
ticker pre-loaded (pass ticker via `st.query_params`, so it's a shareable URL,
not just in-memory state). All three pages reuse one chart component so the
candlestick/EMA/pivot view looks identical everywhere.

## Four things worth flagging before you build this

1. **Fear & Greed Index and the macro calendar (NFP, FOMC) aren't in
   yfinance.** You need a separate source for each — treat them exactly like
   the Gemini lesson: cache aggressively (macro calendar dates barely move —
   cache for days; Fear & Greed can refresh daily), and if the source is down,
   Page 1 should still render the index charts and Minervini market-health
   read, just with that one widget showing "unavailable" instead of crashing
   the page. If you don't have a paid data source for these, the Fear & Greed
   index can be approximated in-house (VIX percentile + breadth + momentum)
   rather than depending on scraping a third-party page.

2. **Automatic "Top 15 healthiest stocks" conflicts with a decision from last
   round.** We deliberately made "circle of competence" a *manual, non-computable
   gate* (there's no ratio for "do you personally understand this business").
   A ranked leaderboard needs a fully numeric score, so: **circle of
   competence is excluded from the ranking score** and shown only as a manual
   note when a user opens a specific ticker on Page 3. The leaderboard's Health
   Score is built purely from the objectively computable parts — see "Health
   Score formula" below.

3. **Governance (insider ownership, capital allocation, related-party
   transactions) was in the previous spec but isn't mentioned in this one.**
   Recommend keeping a small governance sub-section under 3.4 rather than
   dropping it — it's cheap to compute from what's already being fetched for
   catalysts, and it catches problems a pure catalysts/news feed won't. Flag
   for you to confirm; built as optional/low-priority if you'd rather cut it.

4. **The AI value-chain example in your spec lists 3 layers (Compute →
   Hyperscalers → Power & Energy); the version we scoped earlier had a 4th
   layer (Enterprise Apps).** Doesn't matter which is "right" — the point is
   this should be a config-driven list per sector (`config.yaml`), not
   hardcoded, so it's a two-line edit either way and works for non-AI sectors
   too.

## Tech stack
- **Language:** Python 3.11+
- **Frontend:** Streamlit multi-page app (`app/1_Market_Pulse.py`,
  `app/2_Trading_Scanner.py`, `app/3_Health_Scorecard.py`) — fastest path to
  clickable pages + charts + cross-page navigation without a separate frontend
  stack. Pages stay thin; all logic lives in `src/`.
- **Charts:** Plotly (candlestick + EMA overlay + volume + pivot/breakout
  markers), one shared component reused on all 3 pages
- **Data:** `yfinance` for price/fundamentals; TBD source for Fear & Greed and
  macro calendar (decide/confirm before building Page 1 — don't block Pages 2
  and 3 on this decision)
- **Cache:** `data/cache/{market,trading,value}/`, per-source TTL
- **Testing:** `pytest`, frozen fixtures, no live network calls in tests

## yfinance caveats
- Unofficial wrapper — can break silently on Yahoo site changes. Pin a version.
- Rate limits on aggressive polling — batch, backoff, cache.
- Fundamentals fields are patchier than price data — every check degrades
  gracefully (`None`/"unknown"), never crashes the batch on one bad ticker.

---

## Page 1 — Market Pulse (`src/market/`)
- **Fear & Greed Index** — widget with its own cache + fallback (see flag #1)
- **Index charts** — for each market/index the user selects to track
- **Macro event calendar** — Nonfarm Payroll, FOMC meetings, and other
  market-moving scheduled events; cache long, since these are known in advance
- **Market health via Minervini/O'Neil** — apply the Trend Template to the
  index itself (this is the "M" in CANSLIM) — **reuses `market_health.py`
  from System A**, don't reimplement

### Module layout
```
src/market/
├── fear_greed.py        # own source or in-house proxy, cached + fallback
├── macro_calendar.py    # NFP/FOMC/etc. dates, cached (changes rarely)
└── overview.py            # combines index charts + market_health.py output
```

---

## Page 2 — Trading Scanner (System A: Minervini Trend Template + O'Neil CANSLIM)

### Scoring & display
- Score every ticker in the universe against the 8-point Trend Template +
  computable CANSLIM checks, express as a **% match**, sort descending
- **Display only stocks scoring > 80%** (keep this threshold in `config.yaml`,
  not hardcoded)
- Click a stock → detail view: which specific criteria passed/failed, the
  suggested entry point (from the pivot/breakout logic below), and the chart
- "View Health" link → Page 3, same ticker

### Criteria (unchanged from before)
1. Price > 150-day SMA and > 200-day SMA
2. 150-day SMA > 200-day SMA
3. 200-day SMA trending up ≥1 month
4. 50-day SMA > 150-day SMA > 200-day SMA
5. Price > 50-day SMA
6. Price ≥ 30% above 52-week low
7. Price within 25% of 52-week high
8. RS Rating ≥ 70

| CANSLIM | Computable? |
|---|---|
| C — quarterly earnings growth | Partial |
| A — annual earnings growth | Partial |
| N — new highs | Yes |
| S — volume confirmation | Yes |
| L — relative strength | Yes |
| I — institutional sponsorship | Limited |
| M — market direction | Yes (shared with Page 1) |

### Module layout
```
src/trading/
├── indicators.py       # SMA, 52wk hi/lo, RS rating, EMA, volume, pivot/breakout detection
├── trend_template.py   # the 8 Minervini rules, pure functions
├── canslim.py           # CANSLIM checks
├── market_health.py     # "M" — index-level trend status, shared with Page 1
└── report.py             # % match scoring, sorted output
```
`indicators.py`'s EMA/pivot/breakout logic is the same module the shared chart
component and Page 3's entry-timing view both call — one trend engine, reused
everywhere, not reimplemented per page.

---

## Page 3 — Stock Health Scorecard (System B)

### 3.1 Fundamental
- What the business does, revenue model classification (subscription,
  transactional, capex-heavy hardware, licensing, ad-based, etc.)
- **Circle of competence** — manual note shown to the user, not scored (see flag #2)
- Competitive moat — ROIC vs. WACC as a multi-year spread (structural moat =
  sustained ROIC > WACC across a cycle, not one good year)
- Customer concentration & retention — top-N customer % of revenue where
  disclosed, net revenue retention/repeat-purchase proxy where available

### 3.2 Historical Health
- Multi-year revenue growth, gross/operating/net margin trends, FCF and FCF
  margin, ROIC (shared with 3.1's moat check — compute once, reuse)
- **Accounting red-flag audit:** Beneish M-score, Piotroski F-score, D/E
  trend, CFO/Net Income ratio, receivables/inventory growth vs. revenue growth
- Rolls up into this page's contribution to the Health Score

### 3.3 Ecosystem & Partners
- Layered value-chain mapping, **layers defined per sector in `config.yaml`**
  (e.g. AI: Compute/Silicon → Hyperscalers → Power & Energy → ...; adjust
  freely, see flag #4)
- For each layer: who occupies it, is it a bottleneck (pricing power) or
  commoditized, and where does the subject company sit

### 3.4 Reverse DCF & Catalysts
- **Reverse DCF:** back-solve the growth rate the current price already
  implies; compare against the company's own historical growth (3.2) and
  industry growth — is the market pricing something the business has shown it
  can do, or something heroic? Output the margin of safety explicitly.
- **📰 Recent News & Regulatory Catalysts:** upcoming earnings, product
  launches, regulatory decisions, macro dynamics affecting the business —
  needs a news/search step, refreshed every run (short cache TTL, unlike the
  rest of this page)
- **Governance** (optional, see flag #3): insider ownership/buying-selling,
  capital allocation history, related-party transactions

### Top 15 leaderboard
Page 3 also shows the 15 highest-scoring stocks market-wide by Health Score.

### Health Score formula (for the leaderboard — must be fully numeric)
Weighted combination of:
- 3.2 Historical Health / red-flag audit score
- 3.1 Moat quantitative score (ROIC–WACC spread, concentration/retention)
- 3.4 Reverse DCF margin of safety score
- 3.3 Ecosystem position score (bottleneck layer vs. commoditized layer)

Excluded from the score (shown as notes only, per-ticker, not for ranking):
circle of competence, qualitative catalysts/news text, governance notes.
Keep the weights in `config.yaml` so they're tunable without a code change.

### Module layout
```
src/value/
├── fundamentals.py            # 3.1 — revenue model, moat ROIC vs WACC, concentration/retention
├── financial_flow.py           # 3.2 — margins/growth/FCF/ROIC + Beneish/Piotroski red-flag audit
├── value_chain_ecosystem.py    # 3.3 — layer mapping, config-driven per sector
├── reverse_dcf.py               # 3.4a — implied growth rate solver
├── catalysts_governance.py      # 3.4b — catalysts (fresh) + governance (cached), optional LLM/news step
├── health_score.py               # combines the numeric parts into the leaderboard score
└── report.py                       # assembles the full Page-3 view for one ticker
```

---

## Shared repo layout
```
stock-scanner/
├── CLAUDE.md
├── config.yaml                  # thresholds, cache TTLs, value-chain layers per sector, health-score weights
├── data/
│   └── cache/
│       ├── market/               # fear & greed, macro calendar
│       ├── trading/               # price/volume, refreshed frequently
│       └── value/
│           ├── fundamentals/      # long TTL
│           ├── governance/        # long TTL
│           └── catalysts/         # short TTL
├── src/
│   ├── common/
│   │   ├── data_fetch.py
│   │   ├── cache.py
│   │   └── universe.py
│   ├── market/                     # Page 1
│   ├── trading/                     # Page 2 / System A
│   └── value/                        # Page 3 / System B
├── app/
│   ├── 1_Market_Pulse.py
│   ├── 2_Trading_Scanner.py
│   └── 3_Health_Scorecard.py
├── scan_trading.py                 # CLI, System A (batch/testing use)
├── scan_value.py                    # CLI, System B (batch/testing use)
└── tests/
    └── fixtures/
```

## Design rules
- Every deterministic rule is a **pure function**: `(data) -> value | None`.
  `None` means "couldn't be evaluated," never crash the batch or the page.
- Pages in `app/` are display-only — they call `src/`, they don't compute.
- Ticker selection flows through `st.query_params` so links between pages are
  shareable URLs, not just session state.
- Every external data source (yfinance, Fear & Greed, macro calendar, news for
  catalysts) is wrapped with cache + graceful fallback. None of them may block
  a page section that doesn't need them.
- Circle of competence and governance/catalyst text are notes, never inputs to
  the numeric Health Score.
- Keep all thresholds, sector value-chain layers, and health-score weights in
  `config.yaml`.

## Dev commands (to be wired up as the project is built)
```
pip install -r requirements.txt
streamlit run app/1_Market_Pulse.py

# batch/testing CLIs
python scan_trading.py --universe data/universe.csv --output out/trading_results.csv
python scan_value.py --ticker AAPL --output out/value_report.md

pytest
```

## Non-goals
- Not building a brokerage/execution integration.
- Not attempting true IBD RS Rating (proprietary) — using a documented proxy.
- Not depending on any paid data API by default (yfinance only) unless a
  Fear & Greed / macro-calendar source requires one — confirm before building Page 1.
- Not automating "circle of competence" — manual note by design.
- Not making news/catalysts required for Page 3 to render — the numeric
  sections (3.1–3.3, reverse DCF) must always work standalone.
