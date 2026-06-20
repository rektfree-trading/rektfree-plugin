"""
Pure-Python Initial Balance (IB) detectors (vendored from the backend).

DB-free port of the backend's ``app/services/ib_stats.py``. The hosted product
streams full M5 (fallback 1H) history, computes per-day IB-window high/low,
post-IB extensions, breakout outcome and timing, PERSISTS one ``ib_period`` row
per day, then aggregates with SQL/helpers in the ``/stats/ib`` router. The
plugin has no database — so the tool layer feeds in-memory candles to these same
detectors and aggregates the events in Python.

Only the **pure** parts are vendored, keeping the IB math identical to
production:

- ``_slice``             — candles whose timestamp is in ``[start, end)``
- ``_hl_with_times``     — (high, low, high_time, low_time) for a candle list
- ``compute_ib_for_day`` — full per-day IB computation (the body of the
                            backend's ``_compute_ib_for_day``, minus the DB save)
- ``convention_for`` / ``window_for_symbol`` — a trimmed copy of the RTH
  conventions table (vendored from ``app.services.rth_conventions``) so the IB /
  RTH UTC windows match production. Crypto symbols use ``synthetic_ny``:
  IB 13:30-14:30 UTC, RTH 13:30-20:00 UTC.

DROPPED (DB-coupled, replaced by the tool layer): ``_get_asset``,
``_fetch_candles*``, ``_group_by_day`` (ORM variant), ``_save_event``,
``compute_ib`` (the async chunked orchestrator), and ``compute_all_ib``.
Nothing here imports from ``app.*`` or sqlalchemy.

CANDLE SHAPE: each detector expects a candle dict with a timezone-aware UTC
``datetime`` at ``c["timestamp"]`` plus float ``open/high/low/close``. The
plugin's Binance fetcher returns float unix-second ``time`` + ohlc, so the tool
layer adapts each candle before calling these functions.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# RTH conventions (vendored from app.services.rth_conventions — pure data)
# ---------------------------------------------------------------------------

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
}

# Crypto symbols all use the synthetic NY clock (volume concentrates around the
# US equities open). Unknown symbols default to synthetic_ny, matching backend.
CONVENTION_BY_SYMBOL: dict[str, str] = {
    "BTCUSDT": "synthetic_ny",
    "ETHUSDT": "synthetic_ny",
    "SOLUSDT": "synthetic_ny",
}


def _parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def convention_for(symbol: str) -> tuple[str, dict[str, tuple[str, str]]]:
    """Return (convention_name, windows) for a symbol. Defaults to synthetic_ny."""
    name = CONVENTION_BY_SYMBOL.get(symbol.upper(), "synthetic_ny")
    return name, RTH_CONVENTIONS[name]


def _utc_window_for(day: date, hhmm_start: str, hhmm_end: str) -> tuple[datetime, datetime]:
    sh, sm = _parse_hhmm(hhmm_start)
    eh, em = _parse_hhmm(hhmm_end)
    start = datetime.combine(day, time(sh, sm), tzinfo=timezone.utc)
    end = datetime.combine(day, time(eh, em), tzinfo=timezone.utc)
    return start, end


def window_for_symbol(symbol: str, day: date, kind: str) -> tuple[datetime, datetime]:
    """UTC window for ``symbol`` on ``day`` for kind in {'ib','rth','orb'}."""
    _, windows = convention_for(symbol)
    start_str, end_str = windows[kind]
    return _utc_window_for(day, start_str, end_str)


# ---------------------------------------------------------------------------
# Slice helpers (pure — vendored byte-for-byte where it matters)
# ---------------------------------------------------------------------------

def _slice(candles: list[dict], start: datetime, end: datetime) -> list[dict]:
    """Return candles whose timestamp is in ``[start, end)``. Assumes ascending."""
    out: list[dict] = []
    for c in candles:
        ts = c["timestamp"]
        if ts < start:
            continue
        if ts >= end:
            break
        out.append(c)
    return out


def _hl_with_times(candles: list[dict]) -> tuple[float, float, str | None, str | None]:
    """Return (high, low, high_time, low_time); times are HH:MM UTC of the candle
    that held the extreme. (0.0, 0.0, None, None) if the list is empty.
    """
    if not candles:
        return 0.0, 0.0, None, None
    high = float("-inf")
    low = float("inf")
    high_ts: datetime | None = None
    low_ts: datetime | None = None
    for c in candles:
        h = float(c["high"])
        l = float(c["low"])
        if h > high:
            high = h
            high_ts = c["timestamp"]
        if l < low:
            low = l
            low_ts = c["timestamp"]

    def _fmt(ts: datetime | None) -> str | None:
        if ts is None:
            return None
        return f"{ts.hour:02d}:{ts.minute:02d}"

    return high, low, _fmt(high_ts), _fmt(low_ts)


# ---------------------------------------------------------------------------
# Per-day IB computation (body of backend's _compute_ib_for_day, no DB save)
# ---------------------------------------------------------------------------

def compute_ib_for_day(
    symbol: str,
    day: date,
    m5_today: list[dict],
    h1_today: list[dict],
    convention_name: str,
    windows: dict,
) -> dict | None:
    """Compute IB stats for a single trading day.

    Returns the ``data`` dict the backend would persist, or ``None`` if the day
    has no IB-window candles (skipped). M5 is preferred; 1H is the fallback.
    """
    ib_window_hhmm = f"{windows['ib'][0]}-{windows['ib'][1]}"

    ib_start, ib_end = window_for_symbol(symbol, day, "ib")
    rth_start, rth_end = window_for_symbol(symbol, day, "rth")

    # Try 5m first, fall back to 1H.
    ib_candles = _slice(m5_today, ib_start, ib_end)
    rth_candles = _slice(m5_today, rth_start, rth_end)
    post_ib_candles = _slice(m5_today, ib_end, rth_end)
    candle_source = "5m"

    if not ib_candles:
        ib_candles = _slice(h1_today, ib_start, ib_end)
        rth_candles = _slice(h1_today, rth_start, rth_end)
        post_ib_candles = _slice(h1_today, ib_end, rth_end)
        candle_source = "1H"

    if not ib_candles:
        return None

    ib_high, ib_low, ib_high_time, ib_low_time = _hl_with_times(ib_candles)
    ib_size = ib_high - ib_low
    ib_size_pct = (ib_size / ib_low * 100) if ib_low > 0 else 0.0

    if post_ib_candles:
        post_ib_high, post_ib_low, _, _ = _hl_with_times(post_ib_candles)
    else:
        post_ib_high = ib_high
        post_ib_low = ib_low

    ib_up_extension = max(post_ib_high - ib_high, 0.0)
    ib_down_extension = max(ib_low - post_ib_low, 0.0)
    max_extension = max(ib_up_extension, ib_down_extension)
    size_to_extension_ratio = (ib_size / max_extension) if max_extension > 0 else None

    broke_high = False
    broke_low = False
    first_break_side: str | None = None
    first_break_time: str | None = None
    for c in post_ib_candles:
        h = float(c["high"])
        l = float(c["low"])
        ts = c["timestamp"]
        hit_high_now = (not broke_high) and h > ib_high
        hit_low_now = (not broke_low) and l < ib_low
        if hit_high_now and hit_low_now:
            if first_break_side is None:
                if float(c["close"]) >= float(c["open"]):
                    first_break_side = "high"
                else:
                    first_break_side = "low"
                first_break_time = f"{ts.hour:02d}:{ts.minute:02d}"
            broke_high = True
            broke_low = True
        elif hit_high_now:
            if first_break_side is None:
                first_break_side = "high"
                first_break_time = f"{ts.hour:02d}:{ts.minute:02d}"
            broke_high = True
        elif hit_low_now:
            if first_break_side is None:
                first_break_side = "low"
                first_break_time = f"{ts.hour:02d}:{ts.minute:02d}"
            broke_low = True
        if broke_high and broke_low:
            break

    if broke_high and broke_low:
        outcome = "both"
    elif broke_high:
        outcome = "only_h"
    elif broke_low:
        outcome = "only_l"
    else:
        outcome = "neither"

    if rth_candles:
        _, _, high_time, low_time = _hl_with_times(rth_candles)
        rth_open = float(rth_candles[0]["open"])
        rth_close = float(rth_candles[-1]["close"])
        day_direction = "long" if rth_close >= rth_open else "short"
    else:
        high_time = None
        low_time = None
        day_direction = "long"

    return {
        "rth_convention": convention_name,
        "ib_window_utc": ib_window_hhmm,
        "ib_high": round(ib_high, 6),
        "ib_low": round(ib_low, 6),
        "ib_size": round(ib_size, 6),
        "ib_size_pct": round(ib_size_pct, 3),
        "post_ib_high": round(post_ib_high, 6),
        "post_ib_low": round(post_ib_low, 6),
        "ib_up_extension": round(ib_up_extension, 6),
        "ib_down_extension": round(ib_down_extension, 6),
        "max_extension": round(max_extension, 6),
        "size_to_extension_ratio": (
            round(size_to_extension_ratio, 3)
            if size_to_extension_ratio is not None
            else None
        ),
        "outcome": outcome,
        "first_break_side": first_break_side,
        "first_break_time": first_break_time,
        "high_time": high_time,
        "low_time": low_time,
        "ib_high_time": ib_high_time,
        "ib_low_time": ib_low_time,
        "day_direction": day_direction,
        "day_of_week": WEEKDAYS[day.weekday()],
        "candle_source": candle_source,
        "candle_count_ib": len(ib_candles),
        "candle_count_post_ib": len(post_ib_candles),
    }
