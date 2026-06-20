"""
Pure-Python PDH / PDL touch detectors (vendored from the backend).

DB-free port of the backend's ``app/services/pdh_pdl_stats.py``. The hosted
product scans full D1 + 1H candle history, detects whether each day touched the
*previous day's* high (PDH) / low (PDL), PERSISTS one ``pdh_pdl_touch`` row per
day, then aggregates with SQL in the ``/stats/pdh-pdl`` router. The plugin has
no database — so the tool layer feeds in-memory candles to these same detectors
and aggregates the events in Python.

Only the **pure** parts are vendored, keeping the detection math identical to
production:

- ``_group_h1_by_day``       — bucket 1H candles by UTC calendar day
- ``_build_pdh_pdl_lookup``  — map each D1 candle's date → (high, low)
- ``_prior_d1_levels``       — most-recent D1 H/L strictly before a given day
- ``detect_pdh_pdl_touch``   — for one day, did intraday price touch PDH / PDL?
                                (plus a hold/reversal read on the close, added
                                here for the sweep-vs-hold aggregation)
- ``WEEKDAYS``               — weekday constants

DROPPED (DB-coupled, replaced by the tool layer): ``_fetch_d1_candles``,
``_fetch_h1_candles``, ``_save_event``, ``compute_pdh_pdl`` (the async
orchestrator), and ``compute_all_pdh_pdl``. Nothing here imports from ``app.*``
or sqlalchemy.

CANDLE SHAPE: each detector expects a candle dict with a timezone-aware UTC
``datetime`` at ``c["timestamp"]`` (it reads ``.date()``/``.hour``/``.minute``/
``.weekday()``) plus float ``high/low/open/close``. The plugin's Binance fetcher
returns float unix-second ``time`` + ohlc, so the tool layer adapts each candle
before calling these functions.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _group_h1_by_day(candles: list[dict]) -> dict[date, list[dict]]:
    """Group 1H candles by their UTC calendar day (``c["timestamp"].date()``)."""
    grouped: dict[date, list[dict]] = defaultdict(list)
    for c in candles:
        grouped[c["timestamp"].date()].append(c)
    return grouped


def _build_pdh_pdl_lookup(d1_candles: list[dict]) -> dict[date, tuple[float, float]]:
    """Map every D1 candle's date to its (high, low). Used as 'yesterday' levels."""
    lookup: dict[date, tuple[float, float]] = {}
    for c in d1_candles:
        d = c["timestamp"].date()
        lookup[d] = (float(c["high"]), float(c["low"]))
    return lookup


def _prior_d1_levels(
    today: date,
    d1_dates_sorted: list[date],
    pdh_pdl_lookup: dict[date, tuple[float, float]],
) -> tuple[float, float] | None:
    """Return (PDH, PDL) from the most recent D1 candle strictly before ``today``.

    Walks back through the sorted D1 dates — for crypto every calendar day has a
    D1 candle, so this is simply yesterday; the linear walk keeps the forex
    weekend-gap behaviour of the backend intact.
    """
    candidate: date | None = None
    for d in d1_dates_sorted:
        if d < today:
            candidate = d
        else:
            break
    if candidate is None:
        return None
    return pdh_pdl_lookup[candidate]


def detect_pdh_pdl_touch(
    today: date,
    today_h1: list[dict],
    pdh: float,
    pdl: float,
) -> dict | None:
    """Did ``today``'s intraday price touch the previous day's high / low?

    Iterates today's 1H candles and records the FIRST candle whose high crossed
    PDH (``h >= pdh``) or whose low crossed PDL (``l <= pdl``) — byte-for-byte
    the backend's touch rule.

    Adds a **hold / reversal** read (not persisted by the backend, but needed
    for the plugin's sweep-vs-hold aggregation): after a PDH touch, did the day
    *close* back below PDH (reversal/rejection) or above it (acceptance/hold of
    the breakout)? Symmetric for PDL.

    Returns ``None`` only when there are no candles for the day.
    """
    if not today_h1:
        return None

    touched_pdh = False
    touched_pdl = False
    pdh_touch_time: str | None = None
    pdl_touch_time: str | None = None

    for c in today_h1:
        h = float(c["high"])
        l = float(c["low"])
        ts = c["timestamp"]
        if not touched_pdh and h >= pdh:
            touched_pdh = True
            pdh_touch_time = f"{ts.hour:02d}:{ts.minute:02d}"
        if not touched_pdl and l <= pdl:
            touched_pdl = True
            pdl_touch_time = f"{ts.hour:02d}:{ts.minute:02d}"
        if touched_pdh and touched_pdl:
            break

    if touched_pdh and touched_pdl:
        outcome = "both"
    elif touched_pdh:
        outcome = "pdh_only"
    elif touched_pdl:
        outcome = "pdl_only"
    else:
        outcome = "neither"

    # Hold / reversal read on the day's close.
    #   PDH swept then closed BELOW pdh  => rejection / reversal (failed breakout)
    #   PDH swept then closed ABOVE pdh  => acceptance / hold above the level
    day_close = float(today_h1[-1]["close"])
    pdh_reversal = touched_pdh and day_close < pdh   # swept high, came back in
    pdh_held = touched_pdh and day_close >= pdh      # swept high, accepted above
    pdl_reversal = touched_pdl and day_close > pdl   # swept low, came back in
    pdl_held = touched_pdl and day_close <= pdl      # swept low, accepted below

    return {
        "pdh": round(pdh, 6),
        "pdl": round(pdl, 6),
        "touched_pdh": touched_pdh,
        "touched_pdl": touched_pdl,
        "outcome": outcome,
        "pdh_touch_time": pdh_touch_time,
        "pdl_touch_time": pdl_touch_time,
        "day_close": round(day_close, 6),
        "pdh_reversal": pdh_reversal,
        "pdh_held": pdh_held,
        "pdl_reversal": pdl_reversal,
        "pdl_held": pdl_held,
        "rth_convention": "utc_day",
        "day_of_week": WEEKDAYS[today.weekday()],
    }
