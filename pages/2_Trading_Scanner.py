import streamlit as st

from src.common.config import load_config
from src.common.universe import load_universe
from src.common.market_index import get_broad_market_universe
from src.common.charts import price_chart
from src.common.theme import apply_theme
from src.common.checklist import render_trend_template_checklist
from src.common.format import fmt, fmt_pct, fmt_mixed, render_kv_rows
from src.trading.report import scan_universe, stock_detail

st.set_page_config(page_title="Trading Scanner", layout="wide")
apply_theme()
st.title("Trading Scanner — Minervini Trend Template + O'Neil CANSLIM")

cfg = load_config()
universe = load_universe(cfg.get("universe_file", "data/universe.csv"))
broad_market = get_broad_market_universe()  # full S&P 500 + NASDAQ-100, cached ~30 days
# Scan the watchlist merged with the full S&P 500 + NASDAQ-100 constituent
# list — the broadest free cross-section this project can pull without a
# paid data feed (see src/common/market_index.py). RS Rating is ranked
# against this same broad pool (see _rs_ratings_for in src/trading/report.py).
scan_pool = sorted(set(universe) | set(broad_market))
rs_rating_display_min = 80
min_avg_volume_10d = cfg.get("trading", {}).get("liquidity", {}).get("min_avg_volume_10d", 350_000)

st.caption(
    f"Scanning {len(scan_pool)} tickers — {len(universe)}-ticker watchlist merged with the full "
    f"S&P 500 + NASDAQ-100 ({len(broad_market)} tickers, deduplicated). **Stage 1 — Liquidity Filter:** "
    f"10-day avg volume > {min_avg_volume_10d:,.0f} shares (required). Showing every ticker with "
    f"**RS Rating > {rs_rating_display_min}**, ranked by RS Rating. First run fetches price history for "
    f"every ticker (a few minutes); each is cached for 6 hours after that."
)

with st.spinner(f"Scanning {len(scan_pool)} tickers — first run can take a few minutes, then it's cached..."):
    results = scan_universe(scan_pool, cfg)

passes_liquidity = results["liquidity_passed"] != False if "liquidity_passed" in results.columns else True
eligible = results[passes_liquidity]
if eligible.empty:
    st.warning("No tickers currently pass Stage 1 liquidity. Showing full ranked list instead.")
    eligible = results

passes_rs = eligible["rs_rating"] > rs_rating_display_min
display_df = eligible[passes_rs].sort_values("rs_rating", ascending=False, na_position="last")
if display_df.empty:
    st.warning(f"No tickers currently pass Stage 1 liquidity and RS Rating > {rs_rating_display_min}. "
               f"Showing the full liquidity-eligible list instead, ranked by RS Rating.")
    display_df = eligible.sort_values("rs_rating", ascending=False, na_position="last")

search_query = st.text_input(
    "Search ticker",
    placeholder="e.g. NVDA",
    help="Looks up any ticker — not just the pre-scanned watchlist — and runs it through the same "
         "Stage 1/2/4 criteria and RS Rating.",
).strip().upper()
if search_query:
    with st.spinner(f"Scanning {search_query}..."):
        search_result = scan_universe([search_query], cfg)
    row = search_result.iloc[0] if not search_result.empty else None
    if row is None or row.get("error"):
        st.warning(f"Could not find price data for \"{search_query}\" — check the ticker symbol. "
                   f"Showing the watchlist scan instead.")
    else:
        display_df = search_result
        st.info(f"Showing the live scan result for {search_query} against the same criteria as the watchlist above.")

def _check_mark(v):
    if v is True:
        return "✓"
    if v is False:
        return "✗"
    return "–"

display_table = display_df[[
    "ticker", "match_pct", "rs_rating", "breakout", "ema_trend", "last_close",
    "liquidity_passed", "vdu_passed",
]].copy()
display_table["match_pct"] = display_table["match_pct"].map(lambda v: fmt_pct(v, 2))
display_table["rs_rating"] = display_table["rs_rating"].map(lambda v: fmt(v, 2))
display_table["last_close"] = display_table["last_close"].map(lambda v: fmt(v, 2))
display_table["liquidity_passed"] = display_table["liquidity_passed"].map(_check_mark)
display_table["vdu_passed"] = display_table["vdu_passed"].map(_check_mark)
display_table = display_table.rename(columns={"liquidity_passed": "Liquidity", "vdu_passed": "VDU"})

def _color_check(v):
    if v == "✓":
        return "color: #8FD19E; font-weight: 700;"
    if v == "✗":
        return "color: #E38B8B;"
    return ""

styled = display_table.style.map(_color_check, subset=["Liquidity", "VDU"])
st.dataframe(styled, width='stretch', hide_index=True)

st.divider()
st.subheader("Stock detail")

ticker_list = display_df["ticker"].dropna().tolist() if "ticker" in display_df.columns else []
if not ticker_list:
    st.info("No tickers to inspect.")
else:
    query_ticker = st.query_params.get("ticker")
    default_idx = ticker_list.index(query_ticker) if query_ticker in ticker_list else 0
    selected = st.selectbox("Choose a stock", ticker_list, index=default_idx)

    detail = stock_detail(selected, cfg)
    if detail.get("error"):
        st.warning(detail["error"])
    else:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.plotly_chart(price_chart(detail["price_history"], selected, detail["pivot"]), width='stretch')
        with col2:
            liquidity = detail.get("stage1_liquidity", {})
            st.markdown("**Stage 1 — Liquidity Filter**")
            st.metric(
                "10-day avg volume", fmt(liquidity.get("avg_volume_10d"), 0),
                "Pass" if liquidity.get("passed") else ("Fail" if liquidity.get("passed") is False else "n/a"),
            )
            st.caption(f"Required: > {fmt(liquidity.get('min_required'), 0)} shares")

            st.markdown("**Stage 2 — Uptrend (Trend Template)**")
            render_trend_template_checklist(detail["trend_template"]["results"])
            st.metric("Match %", fmt_pct(detail['trend_template']['match_pct'], 2))

            st.markdown("**Stage 4 — Entry Trigger**")
            entry = detail.get("stage4_entry_trigger", {})
            pivot = detail["pivot"]
            if pivot.get("pivot_price"):
                st.metric("Pivot / entry level", fmt(pivot['pivot_price'], 2),
                           "Breakout" if pivot.get("breakout") else "Not broken out yet")
            vdu = entry.get("volume_dry_up", {})
            vdu_status = "Pass" if vdu.get("is_vdu") else ("Fail" if vdu.get("is_vdu") is False else "n/a")
            st.metric("Volume Dry-Up (VDU)", fmt_pct(vdu.get("ratio_pct"), 2), vdu_status)
            st.caption("VDU = recent avg volume vs. 50-day avg volume; pass at ≤ 70%, confirming supply "
                       "has dried up ahead of a breakout/pocket pivot.")
            pv_confirmed = entry.get("pocket_pivot_volume_confirmed")
            st.caption(f"Pocket-pivot / up-on-volume confirmed: {fmt_mixed(pv_confirmed)}")

            if st.button(f"View Health Scorecard for {selected}"):
                st.query_params["ticker"] = selected
                st.switch_page("pages/3_Health_Scorecard.py")

        with st.expander("CANSLIM detail (best-effort — see CLAUDE.md on data limits)"):
            render_kv_rows([
                (k.replace("_", " ").title(), fmt_mixed(v))
                for k, v in detail["canslim"].items()
            ])
