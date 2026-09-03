import streamlit as st

from src.common.config import load_config
from src.common.charts import price_chart
from src.common.theme import apply_theme
from src.common.checklist import render_trend_template_checklist
from src.common.format import fmt, fmt_pct, render_kv_rows, verdict_badge
from src.market.overview import build_market_pulse

st.set_page_config(page_title="Market Pulse", layout="wide")
apply_theme()
st.title("Market Pulse")

cfg = load_config()

index_options = ["SPY", "QQQ", "IWM", "DIA"]
selected_index = st.pills(
    "Index to track — price chart and market health are shown for it",
    index_options,
    selection_mode="single",
    default="SPY",
)

with st.spinner("Loading market data..."):
    pulse = build_market_pulse(cfg, [selected_index or "SPY"])

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Fear & Greed (proxy)")
    fg = pulse["fear_greed"]
    if fg["composite"] is None:
        st.warning("Fear & Greed proxy unavailable right now.")
    else:
        st.metric("Composite", fmt(fg["composite"], 2), fg["label"])
        if not fg.get("is_fresh", True):
            st.caption("Showing cached value — live fetch failed.")
        with st.expander("Components"):
            render_kv_rows([
                (k.replace("_", " ").title(), fmt(v, 2))
                for k, v in fg["components"].items()
            ])
        st.caption(
            "In-house proxy (momentum, price strength, breadth, volatility, safe-haven "
            "demand, junk-bond demand) — directionally similar to CNN's index but not a "
            "reproduction of it. Two gaps are structural: this project has no free source "
            "for options put/call data (one of CNN's 7 inputs), and CNN's breadth signal is "
            "built from true NYSE advance/decline volume, which this proxy approximates from "
            "a small ETF/sector sample. Treat the composite as a rough read, not a match for "
            "the official number."
        )

with col2:
    st.subheader("Market Health — Minervini Trend Template")
    market_health = pulse["market_health"]
    for ticker, mh in market_health.items():
        if mh.get("error"):
            st.warning(f"{ticker}: market health unavailable — {mh['error']}")
            continue
        st.metric(f"{ticker} Trend Template match", fmt_pct(mh["match_pct"], 2))
        verdict = "Confirmed uptrend" if mh["match_pct"] >= 70 else "Mixed / not confirmed"
        kind = "good" if mh["match_pct"] >= 70 else "neutral"
        verdict_badge(verdict, kind)
        with st.expander(f"{ticker} — per-criterion detail"):
            render_trend_template_checklist(mh["results"])

st.divider()
st.subheader("Index charts")
for ticker, df in pulse["index_charts"].items():
    if df is None or df.empty:
        st.warning(f"{ticker}: price data unavailable.")
        continue
    st.plotly_chart(price_chart(df, ticker), width='stretch')

st.divider()
st.subheader("Macro Calendar")
for ev in pulse["macro_events"]:
    header = f"**{ev['name']}** — {ev['frequency']}"
    if ev.get("date"):
        header += f" · next: {ev['date']}"
    st.markdown(header)
    if ev.get("is_event_day") and ev.get("consensus"):
        st.info(ev["consensus"])
st.caption("Static/maintained list in config.yaml — swap for a live economic-calendar source later.")
