import streamlit as st

from src.common.config import load_config
from src.common.universe import load_universe
from src.common.market_index import get_broad_market_universe
from src.common.charts import render_price_chart
from src.common.checklist import render_trend_template_checklist
from src.common.format import fmt, fmt_pct, fmt_mixed, render_kv_rows, stage_header, status_badge_html
from src.trading.report import scan_universe, stock_detail

st.title("Trading Scanner — Minervini Trend Template + O'Neil CANSLIM")

cfg = load_config()
universe = load_universe(cfg.get("universe_file", "data/universe.csv"))
broad_market = get_broad_market_universe()  # full S&P 500 + NASDAQ-100, cached ~30 days
# Scan the watchlist merged with the full S&P 500 + NASDAQ-100 constituent
# list — the broadest free cross-section this project can pull without a
# paid data feed (see src/common/market_index.py). RS Rating is ranked
# against this same broad pool (see _rs_ratings_for in src/trading/report.py).
scan_pool = sorted(set(universe) | set(broad_market))
rs_rating_display_min = 89
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
    "ticker", "match_pct", "rs_rating", "breakout", "last_close",
    "liquidity_passed", "vdu_passed", "vcp_contractions",
]].copy()
display_table["match_pct"] = display_table["match_pct"].map(lambda v: fmt_pct(v, 2))
display_table["rs_rating"] = display_table["rs_rating"].map(lambda v: fmt(v, 2))
display_table["last_close"] = display_table["last_close"].map(lambda v: fmt(v, 2))
display_table["breakout"] = display_table["breakout"].map(_check_mark)
display_table["liquidity_passed"] = display_table["liquidity_passed"].map(_check_mark)
display_table["vdu_passed"] = display_table["vdu_passed"].map(_check_mark)
display_table = display_table.rename(columns={
    "ticker": "Ticker", "match_pct": "Match %", "rs_rating": "RS Rating", "breakout": "Breakout",
    "last_close": "Last Close",
    "liquidity_passed": "Liquidity", "vdu_passed": "VDU", "vcp_contractions": "VCP Waves",
})

def _color_check(v):
    if v == "✓":
        return "color: #8FD19E; font-weight: 700;"
    if v == "✗":
        return "color: #E38B8B;"
    return ""

styled = display_table.style.map(_color_check, subset=["Breakout", "Liquidity", "VDU"])
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
            render_price_chart(detail["price_history"], selected, detail["pivot"])
        with col2:
            min_match = cfg.get("trading", {}).get("match_score_display_min", 80)

            liquidity = detail.get("stage1_liquidity", {})
            stage_header("Stage 1 — Liquidity Filter", liquidity.get("passed"))
            st.metric("10-day avg volume", fmt(liquidity.get("avg_volume_10d"), 0))
            st.caption(f"Required: > {fmt(liquidity.get('min_required'), 0)} shares")

            stage2_pass = detail["trend_template"]["match_pct"] >= min_match
            stage_header("Stage 2 — Uptrend (Trend Template)", stage2_pass)
            render_trend_template_checklist(detail["trend_template"]["results"])
            st.metric("Match %", fmt_pct(detail['trend_template']['match_pct'], 2))

            entry = detail.get("stage4_entry_trigger", {})
            pivot = detail["pivot"]
            stage_header("Stage 4 — Entry Trigger", pivot.get("breakout"))
            if pivot.get("pivot_price"):
                st.metric("Pivot / entry level", fmt(pivot['pivot_price'], 2))
                st.markdown(status_badge_html(pivot.get("breakout"), "Breakout", "Not broken out yet", "n/a"),
                            unsafe_allow_html=True)
            vdu = entry.get("volume_dry_up", {})
            st.metric("Volume Dry-Up (VDU)", fmt_pct(vdu.get("ratio_pct"), 2))
            st.markdown(status_badge_html(vdu.get("is_vdu")), unsafe_allow_html=True)
            st.caption("VDU = recent avg volume vs. 50-day avg volume; pass at ≤ 70%, confirming supply "
                       "has dried up ahead of a breakout/pocket pivot.")
            pv_confirmed = entry.get("pocket_pivot_volume_confirmed")
            st.caption(f"Pocket-pivot / up-on-volume confirmed: {fmt_mixed(pv_confirmed)}")

            vcp = detail.get("vcp", {})
            contractions = vcp.get("contractions", [])
            stage_header("Stage 4 — VCP (Volatility Contraction Pattern) Quality", vcp.get("progressive_tightening"))
            if contractions:
                m1, m2 = st.columns(2)
                m1.metric("Contractions", vcp.get("contraction_count_label", "n/a"))
                with m2:
                    st.markdown("Progressive tightening")
                    st.markdown(status_badge_html(vcp.get("progressive_tightening"), "Yes", "No", "n/a"),
                                unsafe_allow_html=True)

                with st.expander(f"Wave-by-wave detail ({len(contractions)} waves)", expanded=True):
                    render_kv_rows([
                        (f"Wave {c['wave']} — {c['high_date']} to {c['low_date']}",
                         f"{fmt(c['high'], 2)} → {fmt(c['low'], 2)}  ({fmt_pct(c['depth_pct'], 2)} depth)")
                        for c in contractions
                    ])

                final_vdu = vcp.get("final_contraction_vdu", {})
                st.metric("Final-contraction VDU", fmt_pct(final_vdu.get("ratio_pct"), 2))
                st.markdown(status_badge_html(final_vdu.get("is_vdu")), unsafe_allow_html=True)
                st.caption("Volume during the LAST wave specifically vs. 50-day average — pass at ≤ 50% "
                           "(stricter than the general Stage 4 VDU above, which uses a fixed trailing window).")

                vcp_pivot = vcp.get("pivot_price")
                if vcp_pivot is not None:
                    st.metric("VCP pivot (final contraction's high)", fmt(vcp_pivot, 2))
                    st.markdown(status_badge_html(vcp.get("breakout"), "Breakout", "Not broken out yet", "n/a"),
                                unsafe_allow_html=True)
                if vcp.get("breakout"):
                    bv = vcp.get("breakout_volume_confirmed")
                    st.caption(f"Breakout-day volume > 1.5x 50-day average: {fmt_mixed(bv)}")

                rs_line_status = fmt_mixed(vcp.get("rs_line_new_high"))
                leader_status = fmt_mixed(vcp.get("market_leader"))
                st.caption(f"RS Line at/near new high (price vs. SPY, distinct from RS Rating): {rs_line_status} · "
                           f"Market leader (RS Rating ≥ {cfg.get('trading', {}).get('vcp', {}).get('market_leader_rs_min', 90)}): {leader_status}")
                st.caption("VCP wave detection is a best-effort geometric approximation (ZigZag swing detection), "
                           "not a reproduction of any charting tool — treat wave counts/depths as directional.")
            else:
                st.caption("No clear contraction structure detected in the recent price history.")

            if st.button(f"View Health Scorecard for {selected}"):
                st.query_params["ticker"] = selected
                st.switch_page("pages/3_Health_Scorecard.py")

        with st.expander("CANSLIM detail (best-effort — see CLAUDE.md on data limits)"):
            render_kv_rows([
                (k.replace("_", " ").title(), fmt_mixed(v))
                for k, v in detail["canslim"].items()
            ])
