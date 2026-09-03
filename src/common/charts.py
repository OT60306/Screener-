from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.trading import indicators as ind


def price_chart(df: pd.DataFrame, ticker: str, pivot_info: dict | None = None) -> go.Figure:
    """One chart component used on Page 1 (index), Page 2 (scanner detail),
    and Page 3 (health report) — a single TradingView-style panel: candlestick
    + 21/50/200 EMA + pivot/breakout marker on top, volume synced underneath."""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.03,
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            name=ticker, showlegend=False,
        ),
        row=1, col=1,
    )

    for span, color in [(21, "#f2a900"), (50, "#4c78a8"), (200, "#54a24b")]:
        e = ind.ema(df, span)
        if e is not None:
            fig.add_trace(
                go.Scatter(x=df.index, y=e, mode="lines", name=f"EMA{span}", line=dict(width=1.3, color=color)),
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

    up = df["Close"] >= df["Open"]
    vol_colors = ["#5fb47a" if u else "#c46a6a" for u in up]
    fig.add_trace(
        go.Bar(x=df.index, y=df["Volume"], marker_color=vol_colors, name="Volume", showlegend=False),
        row=2, col=1,
    )

    fig.update_layout(
        title=dict(text=f"{ticker} — price / EMA / volume", y=0.99, yanchor="top", x=0, xanchor="left"),
        xaxis_rangeslider_visible=False,
        height=560,
        margin=dict(l=10, r=10, t=60, b=10),
        # legend sits inside the top-left of the price panel (not in the
        # margin) so it never competes with the title above it for space
        legend=dict(
            orientation="h", yanchor="top", y=0.97, xanchor="left", x=0.01,
            bgcolor="rgba(27,25,49,0.45)", bordercolor="rgba(255,255,255,0.15)", borderwidth=1,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#F7F1EC"),
    )
    fig.update_xaxes(gridcolor="rgba(247,241,236,0.08)")
    fig.update_yaxes(gridcolor="rgba(247,241,236,0.08)")
    return fig
