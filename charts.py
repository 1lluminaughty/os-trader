"""Plotly chart builder for a single warrant."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from signals import bollinger, ema_pair


def build_chart(history: pd.DataFrame, live_price: float | None, name: str) -> go.Figure:
    fig = go.Figure()

    if history.empty:
        fig.add_annotation(
            text="Keine Daten",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="#999"),
        )
        fig.update_layout(height=240, margin=dict(l=10, r=10, t=10, b=10))
        return fig

    close = history["close"]
    dates = pd.to_datetime(history["date"])

    _, bb_upper, bb_lower = bollinger(close)
    fig.add_trace(go.Scatter(
        x=dates, y=bb_upper, mode="lines",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=bb_lower, mode="lines",
        line=dict(width=0), fill="tonexty",
        fillcolor="rgba(99, 132, 255, 0.10)",
        name="Bollinger 20/2σ", hoverinfo="skip",
    ))

    if len(close) >= 51:
        ema_fast, ema_slow = ema_pair(close)
        fig.add_trace(go.Scatter(
            x=dates, y=ema_fast, mode="lines",
            line=dict(color="#f0b400", width=1, dash="dot"),
            name="EMA 20",
        ))
        fig.add_trace(go.Scatter(
            x=dates, y=ema_slow, mode="lines",
            line=dict(color="#ff6b9d", width=1, dash="dot"),
            name="EMA 50",
        ))

    fig.add_trace(go.Scatter(
        x=dates, y=close, mode="lines",
        line=dict(color="#5fb3ff", width=2),
        name=name,
        hovertemplate="%{x|%d.%m.%Y}<br>%{y:.3f} €<extra></extra>",
    ))

    if live_price is not None:
        fig.add_hline(
            y=live_price, line_dash="dash", line_color="#7ee787",
            annotation_text=f"Live {live_price:.3f} €",
            annotation_position="top right",
            annotation_font=dict(size=10, color="#7ee787"),
        )

    fig.update_layout(
        height=260,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.02)",
        xaxis=dict(showgrid=False, color="#999"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#999", tickformat=".2f"),
        hovermode="x unified",
    )
    return fig


def build_mini_chart(history: pd.DataFrame, live_price: float | None) -> go.Figure:
    """Compact line-only chart for the overview grid (no indicators, no axes labels)."""
    fig = go.Figure()
    if history.empty:
        fig.add_annotation(
            text="—", xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=10, color="#666"),
        )
        fig.update_layout(height=110, margin=dict(l=4, r=4, t=4, b=4),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.02)")
        return fig

    close = history["close"]
    dates = pd.to_datetime(history["date"])

    trend_up = close.iloc[-1] >= close.iloc[0]
    line_color = "#7ee787" if trend_up else "#ff7b7b"

    fig.add_trace(go.Scatter(
        x=dates, y=close, mode="lines",
        line=dict(color=line_color, width=1.8),
        hovertemplate="%{x|%d.%m.}<br>%{y:.2f} €<extra></extra>",
    ))

    if live_price is not None:
        fig.add_hline(y=live_price, line_dash="dot", line_color="#888", line_width=1)

    fig.update_layout(
        height=110,
        margin=dict(l=4, r=4, t=4, b=4),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.02)",
        xaxis=dict(visible=False, showgrid=False),
        yaxis=dict(visible=False, showgrid=False),
        hovermode="x",
    )
    return fig
