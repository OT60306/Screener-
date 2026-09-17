import streamlit as st

from src.common.config import load_config
from src.common.universe import load_universe
from src.common.market_index import get_broad_market_universe
from src.common.charts import render_price_chart
from src.common.checklist import render_trend_template_checklist
from src.common.format import fmt, fmt_pct, fmt_mixed, render_kv_rows, stage_header, status_badge_html, verdict_badge
from src.trading.report import scan_universe, stock_detail


def _pattern_count(patterns_str) -> int:
    if not patterns_str or patterns_str == "-":
        return 0
    return len(str(patterns_str).split(","))


def _rank_sorted(df):
    """Ranks the scan table by Match % > VDU (pass beats fail beats n/a) >
    number of patterns detected, each descending — ties within a level fall
    through to the next, via a stable sort so any remaining ties keep the
    scanner's own original order."""
    df = df.copy()
    vdu_rank = df["vdu_passed"].map({True: 1, False: 0}) if "vdu_passed" in df.columns else 0
    df["_vdu_rank"] = vdu_rank.fillna(-1) if hasattr(vdu_rank, "fillna") else vdu_rank
    df["_pattern_rank"] = df["patterns"].map(_pattern_count) if "patterns" in df.columns else 0
    ranked = df.sort_values(
        ["match_pct", "_vdu_rank", "_pattern_rank"],
        ascending=[False, False, False],
        na_position="last",
        kind="mergesort",
    )
    return ranked.drop(columns=["_vdu_rank", "_pattern_rank"])


st.title("Trading Scanner — Minervini Trend Template + O'Neil CANSLIM")

cfg = load_config()

timeframe_choice = st.radio(
    "Timeframe", ["Day", "Week"], horizontal=True,
    help="Day = standard daily-bar Trend Template/VCP (50/150/200-day SMAs). "
         "Week = the same rules re-expressed on weekly bars (10/30/40-week SMAs) — "
         "Minervini/O'Neil's own base-reading examples are weekly charts, so this "
         "view tends to filter out daily noise and show cleaner base structure. "
         "RS Rating is unaffected either way — it's a fixed 12-month performance rank.",
)
timeframe = "week" if timeframe_choice == "Week" else "day"

universe = load_universe(cfg.get("universe_file", "data/universe.csv"))
broad_market = get_broad_market_universe()  # full S&P 500 + NASDAQ-100, cached ~30 days
# Scan the watchlist merged with the full S&P 500 + NASDAQ-100 constituent
# list — the broadest free cross-section this project can pull without a
# paid data feed (see src/common/market_index.py). RS Rating is ranked
# against this same broad pool (see _rs_ratings_for in src/trading/report.py).
scan_pool = sorted(set(universe) | set(broad_market))
rs_rating_display_min = 89
min_avg_volume_10d = cfg.get("trading", {}).get("liquidity", {}).get("min_avg_volume_10d", 350_000)

vol_window_label = "2-week" if timeframe == "week" else "10-day"
st.caption(
    f"Scanning {len(scan_pool)} tickers — {len(universe)}-ticker watchlist merged with the full "
    f"S&P 500 + NASDAQ-100 ({len(broad_market)} tickers, deduplicated). **Stage 1 — Liquidity Filter:** "
    f"{vol_window_label} avg volume > {min_avg_volume_10d:,.0f} shares (required). Showing every ticker with "
    f"**RS Rating > {rs_rating_display_min}**, ranked by Match % > VDU > Patterns detected. First run fetches price history for "
    f"every ticker (a few minutes); each is cached for 6 hours after that."
)

with st.spinner(f"Scanning {len(scan_pool)} tickers ({timeframe_choice} timeframe) — first run can take a few minutes, then it's cached..."):
    results = scan_universe(scan_pool, cfg, timeframe)

passes_liquidity = results["liquidity_passed"] != False if "liquidity_passed" in results.columns else True
eligible = results[passes_liquidity]
if eligible.empty:
    st.warning("No tickers currently pass Stage 1 liquidity. Showing full ranked list instead.")
    eligible = results

passes_rs = eligible["rs_rating"] > rs_rating_display_min
display_df = _rank_sorted(eligible[passes_rs])
if display_df.empty:
    st.warning(f"No tickers currently pass Stage 1 liquidity and RS Rating > {rs_rating_display_min}. "
               f"Showing the full liquidity-eligible list instead, ranked by Match % > VDU > Patterns.")
    display_df = _rank_sorted(eligible)

search_query = st.text_input(
    "Search ticker",
    placeholder="e.g. NVDA",
    help="Looks up any ticker — not just the pre-scanned watchlist — and runs it through the same "
         "Stage 1/2/4 criteria and RS Rating.",
).strip().upper()
if search_query:
    with st.spinner(f"Scanning {search_query}..."):
        search_result = scan_universe([search_query], cfg, timeframe)
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

display_cols = [
    "ticker", "match_pct", "rs_rating", "breakout", "last_close",
    "vdu_passed", "vcp_contractions", "patterns",
]
for _col in display_cols:
    if _col not in display_df.columns:
        display_df[_col] = None  # defensive: a fully-empty/error-only scan result can lack any of these
display_table = display_df[display_cols].copy()
display_table["match_pct"] = display_table["match_pct"].map(lambda v: fmt_pct(v, 2))
display_table["rs_rating"] = display_table["rs_rating"].map(lambda v: fmt(v, 2))
display_table["last_close"] = display_table["last_close"].map(lambda v: fmt(v, 2))
display_table["breakout"] = display_table["breakout"].map(_check_mark)
display_table["vdu_passed"] = display_table["vdu_passed"].map(_check_mark)
display_table["patterns"] = display_table["patterns"].fillna("-")
display_table = display_table.rename(columns={
    "ticker": "Ticker", "match_pct": "Match %", "rs_rating": "RS Rating", "breakout": "Breakout",
    "last_close": "Last Close",
    "vdu_passed": "VDU", "vcp_contractions": "VCP Waves", "patterns": "Patterns",
})

def _color_check(v):
    if v == "✓":
        return "color: #8FD19E; font-weight: 700;"
    if v == "✗":
        return "color: #E38B8B;"
    return ""

styled = display_table.style.map(_color_check, subset=["Breakout", "VDU"])
st.dataframe(styled, width='stretch', hide_index=True)
st.caption(
    "**Patterns** = classic O'Neil base shapes currently detected (Cup with Handle, Double Bottom, Ascending "
    "Base, Flat Base, High Tight Flag) — supplementary context only, backtested separately (see the stock "
    "detail view below for each pattern's historical win rate); it does not filter or affect this ranking."
)

st.divider()
st.subheader("Stock detail")

ticker_list = display_df["ticker"].dropna().tolist() if "ticker" in display_df.columns else []
if not ticker_list:
    st.info("No tickers to inspect.")
else:
    query_ticker = st.query_params.get("ticker")
    default_idx = ticker_list.index(query_ticker) if query_ticker in ticker_list else 0
    selected = st.selectbox("Choose a stock", ticker_list, index=default_idx)

    detail = stock_detail(selected, cfg, timeframe)
    if detail.get("error"):
        st.warning(detail["error"])
    else:
        col1, col2 = st.columns([2, 1])
        with col1:
            if timeframe == "week":
                render_price_chart(
                    detail["price_history"], selected, detail["pivot"],
                    ema_spans=(10, 30, 40), display_bars=104, timeframe_label="2Y, weekly",
                )
            else:
                render_price_chart(detail["price_history"], selected, detail["pivot"])
        with col2:
            min_match = cfg.get("trading", {}).get("match_score_display_min", 80)

            liquidity = detail.get("stage1_liquidity", {})
            stage_header("Stage 1 — Liquidity Filter", liquidity.get("passed"))
            vol_window_label = "2-week" if timeframe == "week" else "10-day"
            st.metric(f"{vol_window_label} avg volume", fmt(liquidity.get("avg_volume_10d"), 0))
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
            count_validation = vcp.get("count_validation", {})
            stage_header("Stage 4 — VCP (Volatility Contraction Pattern) Quality", vcp.get("progressive_tightening"))
            if contractions:
                m1, m2 = st.columns(2)
                m1.metric("Contractions", vcp.get("contraction_count_label", "n/a"))
                with m2:
                    st.markdown("Progressive tightening")
                    st.markdown(status_badge_html(vcp.get("progressive_tightening"), "Yes", "No", "n/a"),
                                unsafe_allow_html=True)

                classification = count_validation.get("classification")
                classification_copy = {
                    "pullback_only": ("Just a pullback (1T) — not yet a VCP base", "bad"),
                    "valid_vcp": ("Standard VCP wave count (2T-4T)", "good"),
                    "long_base": ("Long base (5T) — still usable, but running long", "neutral"),
                    "too_loose": ("Too many waves (6T+) — base too loose to trust, skip", "bad"),
                    "no_contraction": ("No contraction structure detected", "neutral"),
                }
                label, kind = classification_copy.get(classification, ("n/a", "neutral"))
                verdict_badge(label, kind)

                with st.expander(f"Wave-by-wave detail ({len(contractions)} waves)", expanded=True):
                    render_kv_rows([
                        (f"Wave {c['wave']} — {c['high_date']} to {c['low_date']}",
                         f"{fmt(c['high'], 2)} → {fmt(c['low'], 2)}  ({fmt_pct(c['depth_pct'], 2)} depth)")
                        for c in contractions
                    ])
                st.caption("Each wave's Low must sit above the prior wave's Low (Higher Low) and its High must be "
                           "at or below the prior wave's High (Equal High or Lower High) to count as the next "
                           "contraction of this base — a Lower Low, or a Higher High that fails and rolls over, "
                           "resets the count to a fresh Wave 1 instead of extending it.")

                tightness = vcp.get("final_contraction_tightness", {})
                t1, t2 = st.columns(2)
                t1.metric("Final-contraction depth", fmt_pct(tightness.get("depth_pct"), 2))
                with t2:
                    st.markdown("Tight enough (≤ 12%, ideal ≤ 5%)")
                    if tightness.get("depth_pct") is not None:
                        badge_text = "Ideal" if tightness.get("is_ideal") else ("Pass" if tightness.get("is_tight_enough") else "Fail")
                        st.markdown(status_badge_html(tightness.get("is_tight_enough"), badge_text, "Fail", "n/a"),
                                    unsafe_allow_html=True)
                    else:
                        st.markdown(status_badge_html(None), unsafe_allow_html=True)

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

        patterns = detail.get("patterns", {})
        if patterns:
            with st.expander("Historical pattern signals (supplementary — not a filter)", expanded=False):
                st.caption(
                    "Best-effort geometric detectors for five classic O'Neil base patterns, backtested on "
                    "519 tickers over 10 years of weekly bars. None cleared a 60-70% win rate — four settled "
                    "around 31-36% (High Tight Flag is too rare to score reliably — see below), with wins "
                    "running several times larger than the fixed 8% stop-loss (a trend-following payoff shape, "
                    "not a high-hit-rate one). Shown here as supplementary context only — they do NOT filter "
                    "or reorder the ranked scan table above."
                )
                pattern_labels = {
                    "cup_with_handle": "Cup with Handle", "double_bottom": "Double Bottom",
                    "ascending_base": "Ascending Base", "flat_base": "Flat Base",
                    "high_tight_flag": "High Tight Flag",
                }
                for key, label in pattern_labels.items():
                    result = patterns.get(key, {})
                    ref = result.get("backtest_reference", {}) or {}
                    found = result.get("found")
                    st.markdown(f"**{label}** &nbsp; {status_badge_html(found, 'Detected', 'Not detected', 'n/a')}",
                                unsafe_allow_html=True)
                    if ref.get("insufficient_sample"):
                        st.caption(
                            f"Backtest reference: only {ref.get('trades')} trades market-wide in the 10-year "
                            "sample — too rare to reliably score (the PDF itself notes this pattern shows up "
                            "\"usually only 1 or 2 occurring in a bull market year\")."
                        )
                    elif ref:
                        st.caption(
                            f"Backtest reference: {ref.get('win_rate_pct')}% win rate, "
                            f"{ref.get('profit_factor')} profit factor over {ref.get('trades')} trades "
                            f"(avg win {ref.get('avg_win_pct')}% / avg loss {ref.get('avg_loss_pct')}%)."
                        )
                    if found:
                        pivot = result.get("pivot_price")
                        breakout = result.get("breakout")
                        final_leg_ready = result.get("final_leg_ready")
                        c1, c2, c3 = st.columns(3)
                        if pivot is not None:
                            c1.metric("Pivot", fmt(pivot, 2))
                        with c2:
                            st.markdown("Breakout")
                            st.markdown(status_badge_html(breakout, "Yes", "Not yet", "n/a"), unsafe_allow_html=True)
                        with c3:
                            st.markdown("Final leg tight + VDU")
                            st.markdown(status_badge_html(final_leg_ready, "Yes", "Not yet", "n/a"), unsafe_allow_html=True)
                        flags = result.get("quality_flags") or []
                        if flags:
                            st.caption("Flags: " + "; ".join(flags))
                    st.divider()

        with st.expander("CANSLIM detail (best-effort — see CLAUDE.md on data limits)"):
            render_kv_rows([
                (k.replace("_", " ").title(), fmt_mixed(v))
                for k, v in detail["canslim"].items()
            ])
