import html
from datetime import datetime, timezone

import streamlit as st

from src.common.config import load_config
from src.common.universe import load_universe
from src.common.market_index import get_broad_market_universe
from src.common.charts import render_price_chart
from src.common.format import fmt, fmt_pct, fmt_money, render_kv_rows, render_series_table, verdict_badge
from src.value.report import build_stock_health_report, scan_leaderboard

st.title("Stock Health Scorecard")

cfg = load_config()
universe = load_universe(cfg.get("universe_file", "data/universe.csv"))
# Same broad-market pool as the Trading Scanner (Page 2) — a leaderboard
# scoped to only the small hand-picked watchlist isn't really "healthiest in
# the market."
broad_market = get_broad_market_universe()
leaderboard_pool = sorted(set(universe) | set(broad_market))

default_ticker = st.query_params.get("ticker", universe[0] if universe else "AAPL")
ticker = st.text_input("Ticker", value=default_ticker).strip().upper()

if ticker:
    with st.spinner(f"Building health report for {ticker}..."):
        report = build_stock_health_report(ticker, cfg)

    st.header(f"{report['company_name']} ({ticker})")

    hs = report["health_score"]
    if hs["health_score"] is not None:
        st.metric("Health Score", f"{fmt(hs['health_score'], 2)} / 100", f"{fmt_pct(hs['coverage_pct'], 2)} data coverage")
        st.caption("Circle of competence, catalysts, and governance are excluded from this score by design — see below.")
    else:
        st.warning("Not enough data to compute a Health Score for this ticker.")

    if report.get("price_history") is not None and not report["price_history"].empty:
        render_price_chart(report["price_history"], ticker, report.get("entry_timing"))

    st.divider()
    st.subheader("3.1 — Fundamental")
    f = report["3.1_fundamental"]

    st.markdown(f"**What this business does:** {f.get('business_description', 'Not available.')}")

    st.markdown("**Circle of competence — flagship products**")
    coc = f.get("circle_of_competence_products") or {}
    products = coc.get("items") or []
    if products:
        st.markdown(" · ".join(products))
        if coc.get("source") == "auto":
            st.caption("Auto-extracted from the company's business summary — best effort, verify manually. "
                       "Add a curated entry to config.yaml (value.circle_of_competence_products) to override.")
    else:
        st.caption(f"No flagship products could be determined for {ticker} — add a curated entry to "
                   f"config.yaml (value.circle_of_competence_products).")
    st.markdown("**Revenue model**")
    gm = f.get("gross_margin_pct")
    gm_text = f" · latest gross margin {fmt_pct(gm, 2)}" if gm is not None else ""
    st.markdown(f"{f['revenue_model']}{gm_text}")
    st.markdown("**Moat verification (ROIC vs. WACC)**")
    st.markdown(f.get("moat_narrative", "Not available."))

    st.subheader("3.2 — Historical Health")
    h = report["3.2_historical_health"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Piotroski F-Score (short-term, YoY)", fmt(h["piotroski_f_score"], 0) if h["piotroski_f_score"] is not None else "n/a", "out of 9")
    jitta = h.get("jitta_score_proxy", {})
    if jitta.get("jitta_score_proxy") is not None:
        c2.metric("Jitta Score proxy (long-term)", f"{fmt(jitta['jitta_score_proxy'], 2)} / 10", jitta.get("label"))
    else:
        c2.metric("Jitta Score proxy (long-term)", "n/a")
    c3.metric("CFO/Net Income (latest)", fmt(h["cfo_to_net_income_series"][0], 2) if h.get("cfo_to_net_income_series") else "n/a")
    c4.metric("Red-flag proxy", h["beneish_proxy_flag"]["flag"])

    if jitta.get("jitta_score_proxy") is not None:
        with st.expander("Jitta Score proxy — breakdown"):
            sub = jitta.get("subscores", {})
            render_kv_rows([
                ("Growth consistency", fmt_pct(sub.get("growth_consistency"), 2)),
                ("Profitability durability (ROIC vs. WACC persistence)", fmt_pct(sub.get("profitability_durability"), 2)),
                ("Cash generation strength (FCF-positive years)", fmt_pct(sub.get("cash_generation_strength"), 2)),
                ("Financial strength trend (debt/equity)", fmt_pct(sub.get("financial_strength_trend"), 2)),
            ])
            st.caption("Sub-scores are internal 0-100% component reads; the headline score above is rescaled to 0-10.")
            st.caption(
                f"Based on {jitta.get('years_used', 0)} year(s) of statement history — the real Jitta Score "
                "looks back up to 10 years, but yfinance's free annual statements only expose ~4. There is no "
                "free data source in this project's stack that goes deeper, so treat this as directional, not "
                "a reproduction of the official score. Not included in the numeric Health Score / leaderboard."
            )

    with st.expander("Margins, growth, FCF, D/E — by period (most recent first)", expanded=True):
        margins = h.get("margins_and_growth", {})
        series = {
            "Revenue growth %": margins.get("revenue_growth_pct_by_period"),
            "Gross margin %": margins.get("gross_margin_pct"),
            "Operating margin %": margins.get("operating_margin_pct"),
            "Net margin %": margins.get("net_margin_pct"),
            "FCF": h.get("fcf_series"),
            "CFO / Net Income": h.get("cfo_to_net_income_series"),
            "Debt / Equity": h.get("debt_to_equity_series"),
        }
        max_len = max((len(v) for v in series.values() if v), default=0)
        periods = ["Latest" if i == 0 else f"-{i} yr" for i in range(max_len)]
        render_series_table(periods, series, decimals=2, formatters={"FCF": lambda v: fmt_money(v, 2)})

    st.subheader("3.3 — Reverse DCF & Catalysts")
    rd = report["3.3_reverse_dcf_and_catalysts"]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Reverse DCF**")
        m1, m2 = st.columns(2)
        m1.metric("Implied growth rate", fmt_pct(rd["implied_growth_rate_pct"], 2))
        m2.metric("Historical revenue CAGR (5Y or available)", fmt_pct(rd["historical_revenue_cagr_pct"], 2))
        st.markdown(
            f"**Industry / TAM growth (analyst forward-estimate proxy):** "
            f"{fmt_pct(rd.get('industry_growth_pct'), 2)}"
        )
        st.caption("No free industry/TAM data source is wired in — this uses the company's own analyst forward "
                    "revenue-growth estimate as a documented proxy, same pattern as the RS Rating proxy.")

        fv = rd.get("fair_value_at_historical_cagr")
        if fv is not None:
            st.metric(
                "Fair value @ historical CAGR",
                fmt_money(fv, 2),
                f"{fmt_pct(rd.get('fair_value_upside_pct'), 2)} vs. current price {fmt_money(rd.get('current_price'), 2)}",
            )
        else:
            st.caption("Fair value @ historical CAGR: not enough data (needs positive FCF and shares outstanding).")

        with st.expander("Assumptions"):
            a = rd["assumptions"]
            render_kv_rows([
                ("Discount rate", fmt_pct(a["discount_rate_pct"], 2)),
                ("Terminal growth", fmt_pct(a["terminal_growth_pct"], 2)),
                ("Projection years", fmt(a["years"], 0)),
            ])
        gap_pct = rd["assessment"].get("gap_pct")
        if gap_pct is None:
            badge_kind = "neutral"
        elif gap_pct > 5:
            badge_kind = "good"   # market pricing LESS than historical growth — potentially undervalued
        elif gap_pct < -5:
            badge_kind = "bad"    # market pricing MORE than historical growth — priced for acceleration, higher risk
        else:
            badge_kind = "neutral"  # roughly matches
        verdict_badge(rd["assessment"]["verdict"], badge_kind)
    with c2:
        st.markdown("**Catalysts** — recent news (product launches, litigation, regulatory, macro)")
        cat = rd["catalysts"]
        if cat.get("items"):
            for item in cat["items"]:
                published = item.get("published")
                date_str = ""
                if published:
                    try:
                        date_str = f" — {datetime.fromtimestamp(int(published), tz=timezone.utc).strftime('%Y-%m-%d')}"
                    except (TypeError, ValueError, OSError):
                        date_str = ""
                title = html.escape(item.get("title", ""))
                publisher = html.escape(item.get("publisher", ""))
                link = item.get("link")
                line = f"[{title}]({link})" if link else title
                st.markdown(f"- {line}  \n  <span style='color:rgba(247,241,236,0.65);font-size:0.85rem;'>{publisher}{date_str}</span>", unsafe_allow_html=True)
        else:
            st.caption(cat["status"])

        st.markdown("**Governance**")
        gov = rd["governance"]
        if gov.get("status") == "ok":
            render_kv_rows([
                ("Insider ownership", fmt_pct(gov.get("insider_ownership_pct"), 2)),
                ("Institutional ownership", fmt_pct(gov.get("institutional_ownership_pct"), 2)),
                ("Payout ratio", fmt(gov.get("payout_ratio"), 2)),
            ])
        else:
            st.caption("Governance data unavailable.")

st.divider()
st.subheader(f"Top {cfg.get('value', {}).get('top_leaderboard_size', 15)} Healthiest Stocks")
st.caption(
    f"Scores the {len(leaderboard_pool)}-ticker pool ({len(universe)}-ticker watchlist + full S&P 500 + "
    f"NASDAQ-100). This fetches full financial statements per ticker (heavier than the Trading Scanner's "
    f"price-only scan) — a cold run across the full pool can take a long while; each ticker is cached "
    f"afterward."
)
if st.button(f"Run leaderboard scan across {len(leaderboard_pool)} tickers (can take a while)"):
    with st.spinner(f"Scoring {len(leaderboard_pool)} tickers..."):
        board = scan_leaderboard(leaderboard_pool, cfg)
    board_display = board.copy()
    board_display = board_display.drop(columns=["coverage_pct", "moat_verdict"], errors="ignore")
    if "health_score" in board_display.columns:
        board_display["health_score"] = board_display["health_score"].map(lambda v: fmt(v, 2))
    if "jitta_score_proxy" in board_display.columns:
        board_display["jitta_score_proxy"] = board_display["jitta_score_proxy"].map(lambda v: fmt(v, 2))
    board_display = board_display.rename(columns={
        "ticker": "Ticker", "company_name": "Company", "health_score": "Health Score",
        "piotroski_f_score": "Piotroski F-Score", "jitta_score_proxy": "Jitta Score Proxy",
        "error": "Error",
    })
    st.dataframe(board_display, width='stretch', hide_index=True)
else:
    st.caption("Click to score the full universe — not run automatically, since it fetches full "
               "financial statements per ticker.")
