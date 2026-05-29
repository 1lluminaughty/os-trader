"""Streamlit dashboard: 10 warrants with 6-month charts + live entry signals."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from analysts import fetch_all as fetch_analyst_consensus, logo_url
from charts import build_chart, build_mini_chart
from data import fetch_expiry, fetch_history, fetch_live_batch
from signals import evaluate, opportunity_score, score_reasons
from trend_signals import (
    evaluate_trend,
    fetch_all_underlyings,
    trend_reasons,
    trend_score,
)
from warrants import WARRANTS, unique_underlyings

REFRESH_MS = 30_000
CET = ZoneInfo("Europe/Berlin")

st.set_page_config(page_title="OS-Dashboard", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    .warrant-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 0.75rem 1rem 0.25rem 1rem;
        margin-bottom: 0.5rem;
    }
    .mini-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        padding: 0.4rem 0.55rem 0.2rem 0.55rem;
        margin-bottom: 0.4rem;
        position: relative;
    }
    .mini-card.hot {
        border: 1px solid #2faa55;
        box-shadow: 0 0 14px rgba(47,170,85,0.35), inset 0 0 8px rgba(47,170,85,0.08);
    }
    .mini-card.warm {
        border: 1px solid #b48a2c;
        box-shadow: 0 0 8px rgba(180,138,44,0.20);
    }
    .score-badge {
        position: absolute;
        top: 6px; right: 8px;
        font-size: 11px; font-weight: 700;
        padding: 1px 7px;
        border-radius: 999px;
        background: rgba(0,0,0,0.35);
        border: 1px solid rgba(255,255,255,0.10);
    }
    .score-hot     { color: #c8f7c8; border-color: #2faa55; }
    .score-warm    { color: #f5d68a; border-color: #b48a2c; }
    .score-neutral { color: #aaa; }
    .signal-chips { margin-top: -4px; margin-bottom: 4px; font-size: 9.5px; line-height: 1.4; }
    .chip {
        display: inline-block;
        padding: 1px 6px;
        margin-right: 3px;
        border-radius: 3px;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .chip-on  { background: #1f6f3b; color: #c8f7c8; }
    .chip-off { background: rgba(255,255,255,0.03); color: #555; }
    .spotlight-card {
        background: linear-gradient(135deg, rgba(47,170,85,0.10), rgba(47,170,85,0.02));
        border: 1px solid #2faa55;
        border-radius: 10px;
        padding: 0.7rem 0.9rem;
        margin-bottom: 0.6rem;
        height: 100%;
    }
    .spotlight-rank { font-size: 11px; color: #7ee787; letter-spacing: 1px; font-weight: 700; }
    .spotlight-name { font-size: 16px; font-weight: 700; color: #fff; margin: 2px 0; }
    .spotlight-score { font-size: 28px; font-weight: 800; color: #7ee787; line-height: 1; float: right; margin-top: -2px; }
    .spotlight-reasons { font-size: 11px; color: #cfe6cf; line-height: 1.5; }
    .mini-title { font-size: 12px; font-weight: 600; color: #ddd; line-height: 1.2; }
    .mini-sub   { font-size: 10px; color: #888; font-family: monospace; }
    .analyst-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        padding: 0.55rem 0.7rem;
        margin-bottom: 0.4rem;
        height: 100%;
    }
    .rec-chip {
        display: inline-block;
        padding: 2px 9px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.5px;
        color: white;
    }
    .signal-badge {
        display: inline-block;
        padding: 2px 10px;
        margin-right: 6px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .badge-on  { background: #1f6f3b; color: #c8f7c8; border: 1px solid #2faa55; }
    .badge-off { background: rgba(255,255,255,0.04); color: #777; border: 1px solid rgba(255,255,255,0.08); }
    .price-up   { color: #7ee787; }
    .price-down { color: #ff7b7b; }
    .price-flat { color: #ddd; }
    .wkn { font-size: 11px; color: #888; font-family: monospace; }
    .section-title { margin-top: 1.2rem; margin-bottom: 0.6rem; font-size: 14px; color: #aaa; letter-spacing: 0.5px; text-transform: uppercase; }
    </style>
    """,
    unsafe_allow_html=True,
)


def is_market_open(now: datetime | None = None) -> bool:
    """EUWAX/Stuttgart warrant trading hours: Mon-Fri 8:00-22:00 CET."""
    now = now or datetime.now(CET)
    return now.weekday() < 5 and 8 <= now.hour < 22


def market_status_label() -> str:
    return "🟢 Markt offen" if is_market_open() else "🔴 Markt geschlossen"


def render_badge(label: str, active: bool) -> str:
    cls = "badge-on" if active else "badge-off"
    return f'<span class="signal-badge {cls}">{label}</span>'


def build_analyst_table(consensus_data: dict) -> pd.DataFrame:
    """Build a sortable DataFrame from the consensus dict, ordered by strongest rating."""
    rows = []
    for c in consensus_data.values():
        rows.append({
            "Logo": logo_url(c.ticker),
            "Basiswert": c.name,
            "Ticker": c.ticker,
            "Empfehlung": c.label,
            "Ø Rating": c.mean_rating,
            "Kurs": c.current_price,
            "Δ Vortag %": c.day_change_pct,
            "Kursziel": c.target_price,
            "Potenzial %": c.upside_pct,
            "Analysten": c.num_analysts,
        })
    df = pd.DataFrame(rows)
    df = df.sort_values(
        by="Ø Rating", ascending=True, na_position="last"
    ).reset_index(drop=True)
    return df


def _color_delta(val):
    if pd.isna(val):
        return ""
    if val > 0:
        return "color: #7ee787; font-weight: 600;"
    if val < 0:
        return "color: #ff7b7b; font-weight: 600;"
    return "color: #ddd;"


def compute_opportunity(warrant, history, live_price, expiry, consensus_data):
    """Return (score, signals, reasons) — MEAN-REVERSION setup."""
    if history.empty:
        return 0.0, None, []
    sig = evaluate(history["close"], current=live_price)
    cons = consensus_data.get(warrant.underlying_ticker) if consensus_data else None
    mean = cons.mean_rating if cons else None
    upside = cons.upside_pct if cons else None
    days_left = (expiry - datetime.now(CET).date()).days if expiry else None
    score = opportunity_score(sig, mean, upside, days_left)
    reasons = score_reasons(sig, mean, upside, days_left)
    return score, sig, reasons


def compute_trend(warrant, underlying_df, expiry):
    """Return (score, signals, reasons) — TREND-FOLLOWING setup, on underlying."""
    if underlying_df is None or underlying_df.empty:
        return 0.0, None, []
    sig = evaluate_trend(underlying_df)
    days_left = (expiry - datetime.now(CET).date()).days if expiry else None
    score = trend_score(sig, days_left)
    reasons = trend_reasons(sig, days_left)
    return score, sig, reasons


def render_trend_chips(sig) -> str:
    """Render 5 compact trend-following signal chips."""
    if sig is None:
        return '<div class="signal-chips">&nbsp;</div>'
    chips = [
        ("200MA", sig.above_200ma, f"200MA +{sig.price_vs_200ma_pct:.0f}%" if sig.price_vs_200ma_pct is not None and sig.price_vs_200ma_pct >= 0 else "200MA ↓"),
        ("GC", sig.golden_cross_recent, f"GC -{sig.days_since_cross}T" if sig.days_since_cross is not None else "GC"),
        ("DCN", sig.donchian55_breakout, "Breakout↑"),
        ("ADX", sig.adx_strong, f"ADX {sig.adx_value:.0f}" if sig.adx_value is not None else "ADX"),
        ("HH", sig.higher_highs, "Higher Highs"),
    ]
    html = ""
    for short, active, full in chips:
        cls = "chip-on" if active else "chip-off"
        label = full if active else short
        html += f'<span class="chip {cls}">{label}</span>'
    return f'<div class="signal-chips">{html}</div>'


def score_class(score: float) -> tuple[str, str]:
    """Return (card_class_suffix, badge_class_suffix) based on score."""
    if score >= 6.0:
        return "hot", "score-hot"
    if score >= 3.0:
        return "warm", "score-warm"
    return "", "score-neutral"


def render_signal_chips(sig) -> str:
    """Render 4 compact signal chips. Active ones colored, inactive grey."""
    if sig is None:
        return '<div class="signal-chips">&nbsp;</div>'
    chips = [
        ("RSI", sig.rsi_oversold, f"RSI {sig.rsi_value:.0f}"),
        ("BB", sig.below_bb, "BB↓"),
        ("6M", sig.near_low, f"6M+{sig.distance_from_low_pct:.0f}%"),
        ("EMA", sig.ema_bull_cross, "EMA↑"),
    ]
    html = ""
    for short, active, full in chips:
        cls = "chip-on" if active else "chip-off"
        label = full if active else short
        html += f'<span class="chip {cls}">{label}</span>'
    return f'<div class="signal-chips">{html}</div>'


def render_mini_card(warrant, history, live_price, expiry, score, sig, strategy="mean_reversion"):
    price, ref, _ = _resolve_price_delta(history, live_price)
    if price is not None and ref:
        delta_pct = (price - ref) / ref * 100
        cls = "price-up" if delta_pct > 0 else ("price-down" if delta_pct < 0 else "price-flat")
        head_right = f'<span class="{cls}" style="font-size:11px;">{price:.2f} € ({delta_pct:+.1f}%)</span>'
    elif price is not None:
        head_right = f'<span class="price-flat" style="font-size:11px;">{price:.2f} €</span>'
    else:
        head_right = '<span class="price-flat" style="font-size:11px;">—</span>'

    if expiry is not None:
        days_left = (expiry - datetime.now(CET).date()).days
        if days_left < 30:
            color = "#ff7b7b"
        elif days_left < 90:
            color = "#f0b400"
        else:
            color = "#888"
        expiry_str = (
            f'<span style="color:{color}; font-size:10px;">'
            f'Ende {expiry.strftime("%d.%m.%y")} · {days_left}T'
            f"</span>"
        )
    else:
        expiry_str = '<span class="mini-sub">Ende —</span>'

    logo = logo_url(warrant.underlying_ticker, size=32)
    logo_html = (
        f'<img src="{logo}" style="width:14px;height:14px;vertical-align:middle;'
        f'margin-right:5px;border-radius:2px;">'
        if logo else ""
    )
    short_name = (
        warrant.name.replace("-OS", "")
        .replace(" (MN02EY)", "")
        .replace(" (MN1GHD)", "")
    )

    card_cls, badge_cls = score_class(score)

    st.markdown(
        f"""
        <div class="mini-card {card_cls}">
            <span class="score-badge {badge_cls}">{score:.1f}</span>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="mini-title">{logo_html}{short_name}</span>
                {head_right}
            </div>
            <div style="display:flex; justify-content:space-between; align-items:baseline;">
                <span class="mini-sub">{warrant.wkn}</span>
                {expiry_str}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    fig = build_mini_chart(history, live_price)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    if strategy == "trend_following":
        st.markdown(render_trend_chips(sig), unsafe_allow_html=True)
    else:
        st.markdown(render_signal_chips(sig), unsafe_allow_html=True)


def _resolve_price_delta(history, live_price) -> tuple[float | None, float | None, bool]:
    """Return (price, prev_close, is_live).

    If live_price is given → compare against last historical close (intraday delta).
    Else → use last close as price, compare against penultimate close (daily delta).
    """
    if history.empty:
        return None, None, False
    last = float(history["close"].iloc[-1])
    if live_price is not None:
        return live_price, last, True
    if len(history) >= 2:
        return last, float(history["close"].iloc[-2]), False
    return last, None, False


def render_card(warrant, history, live_price):
    with st.container():
        st.markdown('<div class="warrant-card">', unsafe_allow_html=True)

        price, ref, is_live = _resolve_price_delta(history, live_price)
        if price is not None and ref:
            delta = price - ref
            delta_pct = delta / ref * 100
            cls = "price-up" if delta > 0 else ("price-down" if delta < 0 else "price-flat")
            tag = "" if is_live else ' <span style="font-size:10px;color:#888;">(letzter Schluss)</span>'
            delta_str = f'<span class="{cls}">{delta:+.3f} € ({delta_pct:+.2f}%)</span>{tag}'
            price_str = f"{price:.3f} €"
        elif price is not None:
            price_str = f"{price:.3f} €"
            delta_str = '<span class="price-flat">—</span>'
        else:
            price_str = "—"
            delta_str = '<span class="price-flat">keine Daten</span>'

        st.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; align-items:baseline;">
              <div>
                <strong style="font-size:16px;">{warrant.name}</strong>
                <span class="wkn">  {warrant.isin}</span>
              </div>
              <div style="text-align:right;">
                <span style="font-size:22px; font-weight:700;">{price_str}</span><br>
                <span style="font-size:12px;">{delta_str}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if not history.empty:
            sig = evaluate(history["close"], current=live_price)
            if sig is not None:
                badges = (
                    render_badge(f"RSI {sig.rsi_value:.0f}", sig.rsi_oversold)
                    + render_badge("BB unten", sig.below_bb)
                    + render_badge(f"6M-Tief +{sig.distance_from_low_pct:.1f}%", sig.near_low)
                    + render_badge("EMA 20/50 ↑", sig.ema_bull_cross)
                )
                st.markdown(f'<div style="margin-top:6px;">{badges}</div>', unsafe_allow_html=True)

        fig = build_chart(history, live_price, warrant.name)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- Layout

market_open = is_market_open()
if market_open:
    st_autorefresh(interval=REFRESH_MS, key="auto-refresh")

col_title, col_status = st.columns([3, 1])
with col_title:
    st.markdown("## 📈 Optionsschein-Dashboard")
with col_status:
    now = datetime.now(CET).strftime("%d.%m.%Y %H:%M:%S")
    refresh_note = (
        f"Auto-Refresh {REFRESH_MS // 1000}s" if market_open else "Auto-Refresh pausiert"
    )
    st.markdown(
        f"<div style='text-align:right; padding-top:18px;'>"
        f"<span style='font-size:13px; color:#999;'>{market_status_label()} · "
        f"{refresh_note} · {now} CET</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

force_live = st.session_state.pop("force_live", False)

if not market_open:
    btn_col, _ = st.columns([2, 5])
    with btn_col:
        if st.button("🔄 Jetzt manuell aktualisieren", use_container_width=True):
            fetch_history.clear()
            fetch_analyst_consensus.clear()
            st.session_state["force_live"] = True
            st.rerun()

with st.spinner("Lade Kurse..."):
    histories = {w.wkn: fetch_history(w.wkn) for w in WARRANTS}
    expiries = {w.wkn: fetch_expiry(w.wkn) for w in WARRANTS}
    if market_open or force_live:
        live_prices = fetch_live_batch([w.wkn for w in WARRANTS])
    else:
        # Market closed: don't hit ariva. Render functions fall back to last historical close.
        live_prices = {w.wkn: None for w in WARRANTS}
    consensus_data = fetch_analyst_consensus(tuple(unique_underlyings()))
    underlying_hist = fetch_all_underlyings(tuple(t for t, _ in unique_underlyings()))

# ─── Strategy mode toggle ──────────────────────────────────────────────
strategy_col, _ = st.columns([3, 4])
with strategy_col:
    strategy = st.radio(
        "Strategie",
        options=["mean_reversion", "trend_following"],
        format_func=lambda v: (
            "🔻 Mean Reversion · Dip-Buying" if v == "mean_reversion"
            else "📈 Trendfolge · Breakout"
        ),
        index=0,
        horizontal=True,
        key="strategy_mode",
    )

# Compute BOTH score sets — toggle just picks which one is active
mr_opportunities = {
    w.wkn: compute_opportunity(
        w, histories[w.wkn], live_prices.get(w.wkn), expiries.get(w.wkn), consensus_data
    )
    for w in WARRANTS
}
tf_opportunities = {
    w.wkn: compute_trend(w, underlying_hist.get(w.underlying_ticker), expiries.get(w.wkn))
    for w in WARRANTS
}
opportunities = mr_opportunities if strategy == "mean_reversion" else tf_opportunities

# ─── Spotlight banner: Top 3 chances ───────────────────────────────────
top3 = sorted(WARRANTS, key=lambda w: opportunities[w.wkn][0], reverse=True)[:3]
strategy_label = (
    "Mean Reversion · überverkauft + bullishe Analysten"
    if strategy == "mean_reversion"
    else "Trendfolge · etablierter Aufwärtstrend im Basiswert"
)
st.markdown(
    f'<div class="section-title" style="margin-top:0;">🎯 Top Chancen jetzt <span style="font-size:11px;color:#666;text-transform:none;letter-spacing:0;">({strategy_label})</span></div>',
    unsafe_allow_html=True,
)
spotlight_cols = st.columns(3)
for rank, w in enumerate(top3, 1):
    score, sig, reasons = opportunities[w.wkn]
    short_name = (
        w.name.replace("-OS", "")
        .replace(" (MN02EY)", "")
        .replace(" (MN1GHD)", "")
    )
    reasons_html = " · ".join(reasons) if reasons else "Keine starken Signale aktiv"
    if score < 3.0:
        # Render a muted card if even the top-3 are weak
        with spotlight_cols[rank - 1]:
            st.markdown(
                f"""
                <div class="spotlight-card" style="background:rgba(255,255,255,0.02); border-color:rgba(255,255,255,0.1);">
                    <span class="spotlight-score" style="color:#888;">{score:.1f}</span>
                    <div class="spotlight-rank" style="color:#888;">#{rank}</div>
                    <div class="spotlight-name">{short_name}</div>
                    <div class="spotlight-reasons">{reasons_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        with spotlight_cols[rank - 1]:
            st.markdown(
                f"""
                <div class="spotlight-card">
                    <span class="spotlight-score">{score:.1f}</span>
                    <div class="spotlight-rank">#{rank} CHANCE</div>
                    <div class="spotlight-name">{short_name} <span style="font-size:11px;color:#888;font-family:monospace;">{w.wkn}</span></div>
                    <div class="spotlight-reasons">{reasons_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ─── Section 1: Analyst recommendations table ──────────────────────────
st.markdown(
    '<div class="section-title">Aktuelle Analysten-Einschätzungen (Basiswerte, sortiert nach stärkster Empfehlung)</div>',
    unsafe_allow_html=True,
)
analyst_df = build_analyst_table(consensus_data)
styled_df = (
    analyst_df.style
    .map(_color_delta, subset=["Δ Vortag %", "Potenzial %"])
    .format(
        {
            "Ø Rating":    "{:.2f}",
            "Kurs":        "{:.2f}",
            "Δ Vortag %":  "{:+.2f} %",
            "Kursziel":    "{:.2f}",
            "Potenzial %": "{:+.1f} %",
            "Analysten":   "{:.0f}",
        },
        na_rep="—",
    )
)
st.dataframe(
    styled_df,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Logo": st.column_config.ImageColumn(label="", width="small"),
        "Basiswert": st.column_config.TextColumn(width="medium"),
        "Ticker": st.column_config.TextColumn(width="small"),
        "Empfehlung": st.column_config.TextColumn(
            help="Konsens-Empfehlung (yfinance recommendationKey)",
            width="small",
        ),
        "Ø Rating": st.column_config.NumberColumn(
            help="1 = Strong Buy, 5 = Strong Sell", width="small",
        ),
        "Kurs": st.column_config.NumberColumn(width="small"),
        "Δ Vortag %": st.column_config.NumberColumn(width="small"),
        "Kursziel": st.column_config.NumberColumn(width="small"),
        "Potenzial %": st.column_config.NumberColumn(
            help="Mittleres Kursziel ggü. aktuellem Kurs", width="small",
        ),
        "Analysten": st.column_config.NumberColumn(width="small"),
    },
)
st.markdown(
    "<div style='font-size:10px; color:#666; margin-top:-8px;'>"
    "Kurse in Handelswährung (US-Werte USD, ENR.DE EUR) · "
    "Spaltenköpfe klicken zum Neu-Sortieren · Quelle: yfinance (Cache 30 min)"
    "</div>",
    unsafe_allow_html=True,
)

# ─── Section 2: Mini-chart overview ────────────────────────────────────
st.markdown(
    f'<div class="section-title">Übersicht — alle {len(WARRANTS)} Scheine auf einen Blick</div>',
    unsafe_allow_html=True,
)

sort_col, _ = st.columns([3, 4])
with sort_col:
    sort_mode = st.radio(
        "Sortierung",
        options=["score", "expiry", "wkn"],
        format_func=lambda v: {
            "score":  "🎯 Beste Chance zuerst",
            "expiry": "📅 Kürzeste Restlaufzeit zuerst",
            "wkn":    "🔤 Original-Reihenfolge",
        }[v],
        index=0,
        horizontal=True,
        key="mini_sort_mode",
    )

if sort_mode == "score":
    ordered_warrants = sorted(
        WARRANTS, key=lambda w: opportunities[w.wkn][0], reverse=True
    )
elif sort_mode == "expiry":
    from datetime import date as _date
    far_future = _date(9999, 12, 31)
    ordered_warrants = sorted(
        WARRANTS, key=lambda w: expiries.get(w.wkn) or far_future
    )
else:
    ordered_warrants = list(WARRANTS)

MINI_COLS = 4
mini_cols = st.columns(MINI_COLS)
for idx, warrant in enumerate(ordered_warrants):
    score, sig, _ = opportunities[warrant.wkn]
    with mini_cols[idx % MINI_COLS]:
        render_mini_card(
            warrant,
            histories[warrant.wkn],
            live_prices.get(warrant.wkn),
            expiries.get(warrant.wkn),
            score,
            sig,
            strategy=strategy,
        )

# ─── Section 3: Detailed cards ─────────────────────────────────────────
st.markdown('<div class="section-title">Detailansicht mit Indikatoren und Signalen</div>', unsafe_allow_html=True)
cols = st.columns(2)
for idx, warrant in enumerate(WARRANTS):
    with cols[idx % 2]:
        render_card(warrant, histories[warrant.wkn], live_prices.get(warrant.wkn))

st.markdown(
    "<div style='margin-top:1rem; font-size:11px; color:#666; text-align:center;'>"
    f"Daten: ariva.de (Kurse) · yfinance (Analystenkonsens) · Auto-Refresh alle {REFRESH_MS // 1000}s · "
    "Signale & Einschätzungen sind technische Hinweise, keine Anlageberatung."
    "</div>",
    unsafe_allow_html=True,
)
