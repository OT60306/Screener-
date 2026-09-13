from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.trading import indicators as ind

DISPLAY_DAYS = 252  # ~1 trading year — the chart shows this window even though
                     # indicators are computed over the full fetched history so
                     # long-lookback EMAs/SMAs stay accurate at the window's edge

# Passed to st.plotly_chart via render_price_chart: no pan/zoom/box-select/
# toolbar/hover-driven interaction — a fixed, read-only view.
PLOTLY_CONFIG = {"staticPlot": True, "displayModeBar": False}

# Solid, high-contrast up/down colors — shared by the candlesticks and the
# volume bars so an up/down day reads the same color in both panels.
UP_COLOR = "#089981"
DOWN_COLOR = "#F23645"


def price_chart(
    df: pd.DataFrame, ticker: str, pivot_info: dict | None = None,
    ema_spans: tuple[int, int, int] = (50, 150, 200), display_bars: int = DISPLAY_DAYS,
    timeframe_label: str = "1Y",
) -> go.Figure:
    """One chart component used on Page 1 (index), Page 2 (scanner detail),
    and Page 3 (health report) — a single TradingView-style panel: candlestick
    + EMA overlay + pivot/breakout marker on top, volume synced underneath.
    White background, no pan/zoom/click interaction — render with
    render_price_chart() below, not st.plotly_chart() directly, so every
    caller gets the same static, fixed-window behavior. `ema_spans`/
    `display_bars`/`timeframe_label` let a weekly-timeframe caller pass
    week-scaled EMA spans and a shorter visible bar count (see the Trading
    Scanner's Day/Week toggle) instead of the daily 50/150/200-day defaults —
    matched to the Trend Template's own 50/150/200-day SMA windows so the
    overlay lines up with what Stage 2's checklist is actually checking."""
    emas = {span: ind.ema(df, span) for span in ema_spans}  # computed on full history for accuracy...
    display_df = df.tail(display_bars)                       # ...then trimmed to the visible window

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.03,
    )

    fig.add_trace(
        go.Candlestick(
            x=display_df.index, open=display_df["Open"], high=display_df["High"],
            low=display_df["Low"], close=display_df["Close"], name=ticker, showlegend=False,
            increasing_line_color=UP_COLOR, increasing_fillcolor=UP_COLOR,
            decreasing_line_color=DOWN_COLOR, decreasing_fillcolor=DOWN_COLOR,
        ),
        row=1, col=1,
    )

    for span, color in zip(ema_spans, ("#f2a900", "#4c78a8", "#54a24b")):
        e = emas[span]
        if e is not None:
            e = e.tail(display_bars)
            fig.add_trace(
                go.Scatter(x=e.index, y=e, mode="lines", name=f"EMA{span}", line=dict(width=1.3, color=color)),
                row=1, col=1,
            )

    if pivot_info and pivot_info.get("pivot_price"):
        fig.add_hline(
            y=pivot_info["pivot_price"],
            line_dash="dash",
            line_color="orange",
            annotation_text=f"Pivot {pivot_info['pivot_price']:.2f}"
            + (" — breakout" if pivot_info.get("breakout") else ""),
            row=1, col=1,
        )

    up = display_df["Close"] >= display_df["Open"]
    vol_colors = [UP_COLOR if u else DOWN_COLOR for u in up]
    fig.add_trace(
        go.Bar(x=display_df.index, y=display_df["Volume"], marker_color=vol_colors, name="Volume", showlegend=False),
        row=2, col=1,
    )

    fig.update_layout(
        title=dict(text=f"{ticker} — price / EMA / volume ({timeframe_label})", y=0.99, yanchor="top", x=0, xanchor="left",
                    font=dict(color="#000000")),
        xaxis_rangeslider_visible=False,
        height=560,
        margin=dict(l=10, r=10, t=60, b=10),
        dragmode=False,
        # legend sits inside the top-left of the price panel (not in the
        # margin) so it never competes with the title above it for space
        legend=dict(
            orientation="h", yanchor="top", y=0.97, xanchor="left", x=0.01,
            bgcolor="rgba(255,255,255,0.75)", bordercolor="rgba(27,25,49,0.15)", borderwidth=1,
            font=dict(color="#000000"),
        ),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(color="#000000"),
    )
    fig.update_xaxes(gridcolor="rgba(27,25,49,0.10)", fixedrange=True, tickfont=dict(color="#000000"),
                      title_font=dict(color="#000000"))
    fig.update_yaxes(gridcolor="rgba(27,25,49,0.10)", fixedrange=True, tickfont=dict(color="#000000"),
                      title_font=dict(color="#000000"))
    return fig


def render_price_chart(
    df: pd.DataFrame, ticker: str, pivot_info: dict | None = None,
    ema_spans: tuple[int, int, int] = (50, 150, 200), display_bars: int = DISPLAY_DAYS,
    timeframe_label: str = "1Y",
) -> None:
    """Builds and renders price_chart() with the fixed, non-interactive,
    white-background config every page should use — call this instead of
    st.plotly_chart(price_chart(...)) directly."""
    st.plotly_chart(
        price_chart(df, ticker, pivot_info, ema_spans, display_bars, timeframe_label),
        width="stretch", config=PLOTLY_CONFIG,
    )
