"""Trend-following indicators for the underlying stocks.

Pulls 2 years of daily OHLC data from yfinance and computes:
- 200-day MA regime filter
- 50/200 EMA Golden Cross (recent, within 30 trading days)
- Donchian 55-day breakout
- ADX(14) trend-strength filter
- Higher-Highs swing structure (last 3 swing highs ascending)

Combines them into a 0–10 trend score with a hard floor when remaining
warrant lifetime is too short (trend following needs runway).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


# ─── Data fetching ─────────────────────────────────────────────────────


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_underlying_history(ticker: str) -> pd.DataFrame:
    """Return 2y daily OHLC for a yfinance ticker, or empty DataFrame on failure."""
    try:
        df = yf.Ticker(ticker).history(period="2y", interval="1d", auto_adjust=False)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.reset_index()
    df.columns = [str(c).lower() for c in df.columns]
    keep = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
    return df[keep].copy()


def fetch_all_underlyings(tickers: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    """Fetch underlying history for many tickers in parallel."""
    out: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = {pool.submit(fetch_underlying_history, t): t for t in tickers}
        for fut in as_completed(futs):
            out[futs[fut]] = fut.result()
    return out


# ─── Indicator math ────────────────────────────────────────────────────


def _wilder_smooth(s: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing = EMA with alpha = 1/period."""
    return s.ewm(alpha=1 / period, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index (Wilder). Returns the ADX series."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(),
         (high - prev_close).abs(),
         (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move.clip(lower=0)
    minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move.clip(lower=0)

    atr = _wilder_smooth(tr, period)
    plus_di = 100 * _wilder_smooth(plus_dm, period) / atr.replace(0, np.nan)
    minus_di = 100 * _wilder_smooth(minus_dm, period) / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return _wilder_smooth(dx.fillna(0), period)


def _swing_highs(high: pd.Series, window: int = 5) -> list[float]:
    """Return list of local-maximum prices (a swing high = strict max of ±window bars)."""
    vals = high.values
    out: list[float] = []
    for i in range(window, len(vals) - window):
        if vals[i] == max(vals[i - window : i + window + 1]):
            out.append(float(vals[i]))
    return out


def higher_highs(high: pd.Series, count: int = 3, window: int = 5) -> bool:
    """Are the last `count` swing-highs strictly ascending?"""
    sh = _swing_highs(high, window=window)
    if len(sh) < count:
        return False
    tail = sh[-count:]
    return all(tail[i] < tail[i + 1] for i in range(count - 1))


# ─── Signal dataclass + scoring ────────────────────────────────────────


@dataclass
class TrendSignals:
    above_200ma: bool
    golden_cross_recent: bool   # 50/200 EMA cross in last 30 trading days
    donchian55_breakout: bool   # close > 55-day high (exclusive of today)
    adx_strong: bool            # ADX > 25
    higher_highs: bool          # last 3 swing-highs ascending

    # Diagnostic values (for display)
    price_vs_200ma_pct: float | None    # +5.2% above, -3.1% below
    adx_value: float | None
    days_since_cross: int | None        # how many trading days ago the last GC happened

    @property
    def any_active(self) -> bool:
        return (
            self.above_200ma or self.golden_cross_recent or
            self.donchian55_breakout or self.adx_strong or self.higher_highs
        )


def evaluate_trend(df: pd.DataFrame) -> TrendSignals | None:
    """Compute trend signals from 2y daily OHLC. Returns None if too little data."""
    if df.empty or len(df) < 220:  # need 200-day MA + buffer
        return None

    high = df["high"]
    low = df["low"]
    close = df["close"]

    # 200-day SMA
    ma200 = close.rolling(200).mean()
    above_200 = bool(close.iloc[-1] > ma200.iloc[-1])
    price_vs_200_pct = float((close.iloc[-1] / ma200.iloc[-1] - 1) * 100)

    # 50/200 EMA Golden Cross within last 30 trading days
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    diff = ema50 - ema200
    cross_up = (diff > 0) & (diff.shift(1) <= 0)
    recent_window = cross_up.iloc[-30:]
    gc_recent = bool(recent_window.any())
    if gc_recent:
        # how many bars ago
        last_idx_in_recent = recent_window[recent_window].index[-1]
        days_since = int(len(close) - 1 - close.index.get_loc(last_idx_in_recent))
    else:
        days_since = None

    # Donchian 55-day breakout: close > previous 55-day rolling high
    donchian_high = high.rolling(55).max().shift(1)
    donchian_break = bool(close.iloc[-1] > donchian_high.iloc[-1])

    # ADX > 25
    adx_series = adx(high, low, close, period=14)
    adx_last = float(adx_series.iloc[-1]) if not pd.isna(adx_series.iloc[-1]) else None
    adx_strong = bool(adx_last is not None and adx_last > 25)

    # Higher-Highs structure
    hh = higher_highs(high, count=3, window=5)

    return TrendSignals(
        above_200ma=above_200,
        golden_cross_recent=gc_recent,
        donchian55_breakout=donchian_break,
        adx_strong=adx_strong,
        higher_highs=hh,
        price_vs_200ma_pct=price_vs_200_pct,
        adx_value=adx_last,
        days_since_cross=days_since,
    )


def trend_score(sig: "TrendSignals | None", days_to_expiry: int | None) -> float:
    """Combined 0–10 trend-following score.

    Hard gate: warrant must have >60 days lifetime, otherwise trend-following
    is pointless (theta-decay outpaces typical trend swings). Below that the
    score is heavily capped.
    """
    if sig is None:
        return 0.0

    # Time-decay gate
    if days_to_expiry is not None and days_to_expiry < 60:
        return 0.0
    runway_bonus = 0.0
    if days_to_expiry is not None and days_to_expiry >= 90:
        runway_bonus = 0.5  # comfortable runway

    score = 0.0
    if sig.above_200ma:
        score += 3.0
    if sig.golden_cross_recent:
        score += 2.0
    if sig.donchian55_breakout:
        score += 3.0
    if sig.adx_strong:
        score += 1.5
    if sig.higher_highs:
        score += 1.0
    score += runway_bonus

    return max(0.0, min(10.0, score))


def trend_reasons(sig: "TrendSignals | None", days_to_expiry: int | None) -> list[str]:
    """Human-readable reasons explaining a high trend score."""
    out: list[str] = []
    if sig is None:
        return out
    if sig.above_200ma:
        out.append(f"über 200d-MA (+{sig.price_vs_200ma_pct:.1f}%)")
    if sig.golden_cross_recent:
        out.append(f"Golden Cross vor {sig.days_since_cross}T")
    if sig.donchian55_breakout:
        out.append("55-Tage-Breakout")
    if sig.adx_strong and sig.adx_value is not None:
        out.append(f"ADX {sig.adx_value:.0f} (starker Trend)")
    if sig.higher_highs:
        out.append("Higher Highs")
    if days_to_expiry is not None and days_to_expiry < 90:
        out.append(f"⚠ nur {days_to_expiry}T Laufzeit")
    return out
