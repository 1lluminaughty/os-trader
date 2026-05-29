"""Technical indicators and entry signals."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def bollinger(
    close: pd.Series, period: int = 20, std_mult: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return mid, mid + std_mult * std, mid - std_mult * std


def ema_pair(close: pd.Series, fast: int = 20, slow: int = 50) -> tuple[pd.Series, pd.Series]:
    return (
        close.ewm(span=fast, adjust=False).mean(),
        close.ewm(span=slow, adjust=False).mean(),
    )


@dataclass
class Signals:
    rsi_oversold: bool
    below_bb: bool
    near_low: bool
    ema_bull_cross: bool
    rsi_value: float
    six_month_low: float
    distance_from_low_pct: float

    @property
    def any_active(self) -> bool:
        return self.rsi_oversold or self.below_bb or self.near_low or self.ema_bull_cross


def opportunity_score(
    sig: "Signals | None",
    consensus_mean: float | None,
    upside_pct: float | None,
    days_to_expiry: int | None,
) -> float:
    """Combined 0-10 opportunity score. Higher = better entry candidate.

    Technical signals dominate (~max 9.5 pts), analyst data adds confirmation
    (~max 3 pts), short remaining lifetime is penalised (-1 / -3 pts).
    Result is clamped to [0, 10].
    """
    if sig is None:
        return 0.0

    score = 0.0
    # ── Technical signals ─────────────────────────────────────────
    if sig.rsi_oversold:
        score += 3.0
    elif sig.rsi_value < 40:
        score += 1.5
    if sig.below_bb:
        score += 2.5
    if sig.near_low:
        score += 2.0
    if sig.ema_bull_cross:
        score += 2.0

    # ── Analyst sentiment ─────────────────────────────────────────
    if consensus_mean is not None:
        if consensus_mean < 1.5:
            score += 1.5
        elif consensus_mean < 2.0:
            score += 0.75
    if upside_pct is not None:
        if upside_pct > 20:
            score += 1.5
        elif upside_pct > 10:
            score += 0.75

    # ── Time-decay penalty ────────────────────────────────────────
    if days_to_expiry is not None:
        if days_to_expiry < 30:
            score -= 3.0
        elif days_to_expiry < 90:
            score -= 1.0

    return max(0.0, min(10.0, score))


def score_reasons(
    sig: "Signals | None",
    consensus_mean: float | None,
    upside_pct: float | None,
    days_to_expiry: int | None,
) -> list[str]:
    """Return a list of short reason strings explaining why a score is high.

    Used to build the Spotlight tooltip / banner.
    """
    out: list[str] = []
    if sig is not None:
        if sig.rsi_oversold:
            out.append(f"RSI {sig.rsi_value:.0f} (überverkauft)")
        if sig.below_bb:
            out.append("Bollinger unten")
        if sig.near_low:
            out.append(f"6M-Tief +{sig.distance_from_low_pct:.1f}%")
        if sig.ema_bull_cross:
            out.append("EMA 20/50 ↑")
    if consensus_mean is not None and consensus_mean < 1.5:
        out.append(f"Analyst Ø {consensus_mean:.2f}")
    if upside_pct is not None and upside_pct > 10:
        out.append(f"Ziel +{upside_pct:.0f}%")
    if days_to_expiry is not None and days_to_expiry < 90:
        out.append(f"⚠ nur {days_to_expiry}T Laufzeit")
    return out


def evaluate(close: pd.Series, current: float | None = None) -> Signals | None:
    """Compute current entry-signal state. Returns None if not enough history."""
    if len(close) < 21:
        return None

    price = float(current) if current is not None else float(close.iloc[-1])

    rsi_series = rsi(close)
    rsi_val = float(rsi_series.iloc[-1])

    _, _, bb_lower = bollinger(close)
    bb_low_last = float(bb_lower.iloc[-1]) if not pd.isna(bb_lower.iloc[-1]) else np.nan

    low_6m = float(close.min())
    dist_pct = (price - low_6m) / low_6m * 100 if low_6m > 0 else float("inf")

    if len(close) >= 51:
        fast, slow = ema_pair(close)
        cross_window = fast.iloc[-5:] - slow.iloc[-5:]
        prev_window = fast.iloc[-6:-1] - slow.iloc[-6:-1]
        bull_cross = bool(((prev_window.values < 0) & (cross_window.values > 0)).any())
    else:
        bull_cross = False

    return Signals(
        rsi_oversold=rsi_val < 30,
        below_bb=not np.isnan(bb_low_last) and price <= bb_low_last,
        near_low=dist_pct <= 5,
        ema_bull_cross=bull_cross,
        rsi_value=rsi_val,
        six_month_low=low_6m,
        distance_from_low_pct=dist_pct,
    )
