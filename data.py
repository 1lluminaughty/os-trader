"""ariva.de scraping for warrant prices.

Two endpoints are used:

* Live price → `https://www.ariva.de/{wkn}/` (HTML, `.instrument-header-quote`)
* Historical → `https://www.ariva.de/hebelprodukte/{wkn}/kurse/historische-kurse?boerse_id=39&month=YYYY-MM-DD`
  Returns one calendar month per request → we iterate over 7 month-ends to cover ~6 months.
"""

from __future__ import annotations

import io
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
BASE = "https://www.ariva.de"
BOERSE_FRANKFURT_ZERTIFIKATE = 39
BOERSE_STUTTGART_EUWAX = 47
TIMEOUT = 10


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"})
    return s


def _parse_german_number(text: str) -> float | None:
    cleaned = text.replace("\xa0", " ").replace("€", "").replace("EUR", "").strip()
    cleaned = cleaned.replace(".", "").replace(",", ".")
    match = re.search(r"-?\d+\.\d+|-?\d+", cleaned)
    return float(match.group()) if match else None


def _month_ends_for_six_months(today: date | None = None) -> list[str]:
    """Return month-end strings (YYYY-MM-DD) covering the last ~6 months + current."""
    today = today or date.today()
    out = []
    cursor = date(today.year, today.month, 1)
    for _ in range(7):
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month - timedelta(days=1)
        out.append(month_end.strftime("%Y-%m-%d"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return out


def _fetch_month(
    session: requests.Session, wkn: str, month_end: str, boerse_id: int
) -> pd.DataFrame:
    url = (
        f"{BASE}/hebelprodukte/{wkn}/kurse/historische-kurse"
        f"?boerse_id={boerse_id}&month={month_end}"
    )
    resp = session.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    rows = []
    for tr in soup.find_all("tr", class_=re.compile(r"^arrow[01]$")):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 5:
            continue
        try:
            d = datetime.strptime(cells[0], "%d.%m.%y").date()
        except ValueError:
            continue
        opn = _parse_german_number(cells[1])
        high = _parse_german_number(cells[2])
        low = _parse_german_number(cells[3])
        close = _parse_german_number(cells[4])
        if close is None:
            continue
        rows.append(
            {"date": d, "open": opn, "high": high, "low": low, "close": close}
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_history(wkn: str) -> pd.DataFrame:
    """Return ~6 months of OHLC data for the given WKN, sorted ascending by date.

    Tries Frankfurt Zertifikate first, falls back to Stuttgart EUWAX.
    Returns empty DataFrame on total failure (caller renders 'no data').
    """
    sess = _session()
    for boerse_id in (BOERSE_FRANKFURT_ZERTIFIKATE, BOERSE_STUTTGART_EUWAX):
        frames: list[pd.DataFrame] = []
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [
                    pool.submit(_fetch_month, sess, wkn, m, boerse_id)
                    for m in _month_ends_for_six_months()
                ]
                for fut in as_completed(futures):
                    df = fut.result()
                    if not df.empty:
                        frames.append(df)
        except Exception:
            continue

        if not frames:
            continue

        merged = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset="date")
            .sort_values("date")
            .reset_index(drop=True)
        )
        cutoff = pd.Timestamp(date.today() - timedelta(days=183))
        merged = merged[pd.to_datetime(merged["date"]) >= cutoff].reset_index(drop=True)
        if not merged.empty:
            return merged

    return pd.DataFrame(columns=["date", "open", "high", "low", "close"])


def fetch_live(wkn: str) -> float | None:
    """Return the current price for the given WKN, or None on failure."""
    try:
        resp = _session().get(f"{BASE}/{wkn}/", timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for div in soup.select(".instrument-header-quote"):
            price = _parse_german_number(div.get_text())
            if price is not None:
                return price
        return None
    except Exception:
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_expiry(wkn: str) -> date | None:
    """Return the warrant's end date.

    Tries "Letzter Handelstag" (HSBC/SG style) first, falls back to
    "Bewertungstag" (Morgan Stanley/BNP/Goldman style — typically 1 day later).
    """
    try:
        resp = _session().get(f"{BASE}/{wkn}/", timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception:
        return None

    # Label cell + immediately following td containing a date.
    for label in ("Letzter Handelstag", "Bewertungstag"):
        match = re.search(
            label + r"[^<]*</td>\s*<td[^>]*>\s*(\d{2}\.\d{2}\.\d{4})\s*</td>",
            resp.text,
        )
        if match:
            try:
                return datetime.strptime(match.group(1), "%d.%m.%Y").date()
            except ValueError:
                continue
    return None


def fetch_live_batch(wkns: list[str]) -> dict[str, float | None]:
    """Fetch live prices for many WKNs concurrently."""
    result: dict[str, float | None] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch_live, w): w for w in wkns}
        for fut in as_completed(futures):
            result[futures[fut]] = fut.result()
    return result
