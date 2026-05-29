"""Hard-coded list of warrants tracked by the dashboard."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Warrant:
    wkn: str
    isin: str
    name: str
    underlying_ticker: str
    underlying_name: str


WARRANTS: list[Warrant] = [
    Warrant("HT7BZS", "DE000HT7BZS1", "Alphabet-OS",          "GOOGL",  "Alphabet"),
    Warrant("HS541H", "DE000HS541H0", "Apple-OS",             "AAPL",   "Apple"),
    Warrant("MK8U55", "DE000MK8U558", "Broadcom-OS",          "AVGO",   "Broadcom"),
    Warrant("MN02EY", "DE000MN02EY1", "Caterpillar-OS (MN02EY)", "CAT", "Caterpillar"),
    Warrant("MN1GHD", "DE000MN1GHD2", "Caterpillar-OS (MN1GHD)", "CAT", "Caterpillar"),
    Warrant("SX8B21", "DE000SX8B219", "Netflix-OS",           "NFLX",   "Netflix"),
    Warrant("HT1HJW", "DE000HT1HJW7", "Nvidia-OS",            "NVDA",   "Nvidia"),
    Warrant("HT2UQ7", "DE000HT2UQ79", "Siemens Energy-OS",    "ENR.DE", "Siemens Energy"),
    Warrant("GW17V3", "DE000GW17V36", "TSMC-OS",              "TSM",    "TSMC"),
    Warrant("HT753K", "DE000HT753K4", "IBM-OS",               "IBM",    "IBM"),
    Warrant("HM5ZFS", "DE000HM5ZFS3", "Cisco-OS",             "CSCO",   "Cisco"),
]


def unique_underlyings() -> list[tuple[str, str]]:
    """Return (ticker, name) pairs, deduped, in WARRANTS order."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for w in WARRANTS:
        if w.underlying_ticker not in seen:
            seen.add(w.underlying_ticker)
            out.append((w.underlying_ticker, w.underlying_name))
    return out
