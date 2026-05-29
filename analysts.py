"""Analyst consensus for underlying stocks (via yfinance)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import streamlit as st
import yfinance as yf


DOMAIN_BY_TICKER: dict[str, str] = {
    "GOOGL":  "google.com",
    "AMZN":   "amazon.com",
    "AAPL":   "apple.com",
    "AVGO":   "broadcom.com",
    "CAT":    "caterpillar.com",
    "NFLX":   "netflix.com",
    "NVDA":   "nvidia.com",
    "ENR.DE": "siemens-energy.com",
    "TSM":    "tsmc.com",
    "IBM":    "ibm.com",
    "CSCO":   "cisco.com",
}


def logo_url(ticker: str, size: int = 64) -> str | None:
    domain = DOMAIN_BY_TICKER.get(ticker)
    if not domain:
        return None
    return f"https://www.google.com/s2/favicons?domain={domain}&sz={size}"


@dataclass
class Consensus:
    ticker: str
    name: str
    recommendation: str          # strong_buy | buy | hold | sell | strong_sell | none
    mean_rating: float | None    # 1.0–5.0, lower is better
    target_price: float | None
    current_price: float | None
    previous_close: float | None
    day_change_pct: float | None
    upside_pct: float | None
    num_analysts: int | None

    @property
    def label(self) -> str:
        return {
            "strong_buy":  "STRONG BUY",
            "buy":         "BUY",
            "hold":        "HOLD",
            "sell":        "SELL",
            "strong_sell": "STRONG SELL",
            "underperform": "SELL",
            "outperform":  "BUY",
            "none":        "—",
        }.get(self.recommendation, self.recommendation.upper())

    @property
    def color(self) -> str:
        return {
            "strong_buy":   "#1f8a3b",
            "buy":          "#3fa860",
            "outperform":   "#3fa860",
            "hold":         "#b3892a",
            "sell":         "#c44e4e",
            "underperform": "#c44e4e",
            "strong_sell":  "#a0231f",
        }.get(self.recommendation, "#666666")


def _fetch_one(ticker: str, name: str) -> Consensus:
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        info = {}
    target = info.get("targetMeanPrice")
    current = info.get("currentPrice") or info.get("regularMarketPrice")
    prev = info.get("previousClose") or info.get("regularMarketPreviousClose")
    upside = ((target / current) - 1) * 100 if (target and current) else None
    day_change = ((current / prev) - 1) * 100 if (current and prev) else None
    return Consensus(
        ticker=ticker,
        name=name,
        recommendation=info.get("recommendationKey", "none") or "none",
        mean_rating=info.get("recommendationMean"),
        target_price=target,
        current_price=current,
        previous_close=prev,
        day_change_pct=day_change,
        upside_pct=upside,
        num_analysts=info.get("numberOfAnalystOpinions"),
    )


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_all(underlyings: tuple[tuple[str, str], ...]) -> dict[str, Consensus]:
    """Fetch consensus for many tickers in parallel. Cached 30 min."""
    out: dict[str, Consensus] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = {pool.submit(_fetch_one, t, n): t for t, n in underlyings}
        for fut in as_completed(futs):
            c = fut.result()
            out[c.ticker] = c
    return out
