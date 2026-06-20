"""
RTH (Regular Trading Hours) conventions per asset — pure, stdlib-only.

DB-free port of the backend's ``app/services/rth_conventions.py``. This is the
single source of truth for the IB / RTH / ORB UTC windows used by the plugin's
Bucket-2 stats tools (``compute_orb_stats`` and ``compute_eth_profile_stats``).
``ib_stats.py`` keeps its own inlined trimmed copy (left untouched on purpose),
so this module is shared only by the two new tools.

Convention strings are stable identifiers and match production byte-for-byte.
Crypto symbols and forex majors use ``synthetic_ny`` (IB 13:30-14:30 UTC, RTH
13:30-20:00 UTC, ORB 13:30-13:45 UTC) — for 24/7 crypto this is a *synthetic*
RTH-open convention pinned to the US equities open, where volume concentrates.
US index symbols use ``nyse`` (identical windows); regional indices use
``frankfurt`` / ``london`` / ``tokyo``.

Only the pure parts are vendored — nothing here imports from ``app.*`` or
sqlalchemy.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone


RTH_CONVENTIONS: dict[str, dict[str, tuple[str, str]]] = {
    "synthetic_ny": {
        "ib":  ("13:30", "14:30"),
        "rth": ("13:30", "20:00"),
        "orb": ("13:30", "13:45"),
    },
    "nyse": {
        "ib":  ("13:30", "14:30"),
        "rth": ("13:30", "20:00"),
        "orb": ("13:30", "13:45"),
    },
    "frankfurt": {
        "ib":  ("07:00", "08:00"),
        "rth": ("07:00", "15:30"),
        "orb": ("07:00", "07:15"),
    },
    "london": {
        "ib":  ("08:00", "09:00"),
        "rth": ("08:00", "16:30"),
        "orb": ("08:00", "08:15"),
    },
    "tokyo": {
        "ib":  ("00:00", "01:00"),
        "rth": ("00:00", "06:00"),
        "orb": ("00:00", "00:15"),
    },
}


CONVENTION_BY_SYMBOL: dict[str, str] = {
    # Crypto — synthetic NY clock (volume concentrates around US equities open)
    "BTCUSDT": "synthetic_ny",
    "ETHUSDT": "synthetic_ny",
    "SOLUSDT": "synthetic_ny",
    # Forex majors + gold — NY open
    "EUR_USD": "synthetic_ny",
    "GBP_USD": "synthetic_ny",
    "USD_JPY": "synthetic_ny",
    "XAU_USD": "synthetic_ny",
    # US equity indices
    "SPX500_USD": "nyse",
    "NAS100_USD": "nyse",
    "US30_USD":   "nyse",
    # Regional indices
    "DE30_EUR":   "frankfurt",
    "UK100_GBP":  "london",
    "JP225_USD":  "tokyo",
}


def parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def convention_for(symbol: str) -> tuple[str, dict[str, tuple[str, str]]]:
    """Return (convention_name, windows) for a symbol. Defaults to synthetic_ny."""
    name = CONVENTION_BY_SYMBOL.get(symbol.upper(), "synthetic_ny")
    return name, RTH_CONVENTIONS[name]


def utc_window_for(day: date, hhmm_start: str, hhmm_end: str) -> tuple[datetime, datetime]:
    """Build inclusive-start/exclusive-end UTC datetimes for a window on `day`."""
    sh, sm = parse_hhmm(hhmm_start)
    eh, em = parse_hhmm(hhmm_end)
    start = datetime.combine(day, time(sh, sm), tzinfo=timezone.utc)
    end = datetime.combine(day, time(eh, em), tzinfo=timezone.utc)
    return start, end


def window_for_symbol(symbol: str, day: date, kind: str) -> tuple[datetime, datetime]:
    """UTC window for `symbol` on `day` for kind in {'ib','rth','orb'}."""
    _, windows = convention_for(symbol)
    start_str, end_str = windows[kind]
    return utc_window_for(day, start_str, end_str)
