"""
Pure-Python session-statistics detectors (vendored from the backend).

This is a DB-free port of the backend's ``app/services/session_stats.py``
detectors. The hosted product scans full 1H candle history, detects per-session
events, PERSISTS them as ``SessionEvent`` rows, then aggregates with SQL in the
``/stats/sessions`` router. The plugin has no database — so the tool layer feeds
in-memory candles to these same detectors and aggregates the events in Python.

Only the **pure** parts are vendored, byte-for-byte where it matters so the
detector math stays identical to production:

- ``_group_by_day_and_session``  — bucket candles by date → session
- ``_compute_session_range``     — H/L/range/direction/timing for one session
- ``_detect_sweep``              — did a session sweep the prior session's H/L?
- ``_detect_ny_continuation``    — did NY continue or reverse London?
- ``_detect_power_of_3``         — Accumulation→Manipulation→Distribution
- ``SESSIONS`` / ``WEEKDAYS``    — session-time + weekday constants

DROPPED (DB-coupled, replaced by the tool layer): ``_fetch_candles_from_db``,
``_save_event``, ``compute_session_stats`` (the async orchestrator), and
``compute_all_stats``. Nothing here imports from ``app.*`` or sqlalchemy.

CANDLE SHAPE: each detector expects a candle dict with a timezone-aware UTC
``datetime`` at ``c["timestamp"]`` (they call ``.strftime("%H:%M")`` and read
``.hour``/``.weekday()``) plus float ``high/low/open/close``. The plugin's
Binance fetcher returns float unix-second ``time`` + ohlc, so the tool layer
adapts each candle before calling these functions.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

# Session definitions (UTC hours) — identical to the backend.
# Asia 00:00–08:00, London 08:00–13:00, New York 13:00–21:00.
SESSIONS = {
    "asia":     (0, 8),
    "london":   (8, 13),
    "new_york": (13, 21),
}

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _group_by_day_and_session(candles: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """Group candles by date → session.

    Each candle is placed in the first session whose ``[start_h, end_h)`` hour
    window contains ``c["timestamp"].hour``. Candles outside all sessions
    (21:00–24:00 UTC) are ignored, mirroring the backend.
    """
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for c in candles:
        ts = c["timestamp"]
        day_key = ts.strftime("%Y-%m-%d")
        hour = ts.hour
        for sess_name, (start_h, end_h) in SESSIONS.items():
            if start_h <= hour < end_h:
                grouped[day_key][sess_name].append(c)
                break
    return grouped


def _compute_session_range(candles: list[dict], session: str, day_key: str, symbol: str) -> dict | None:
    """Compute range stats for a single session."""
    if not candles:
        return None

    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]

    session_high = max(highs)
    session_low = min(lows)
    session_open = float(candles[0]["open"])
    session_close = float(candles[-1]["close"])
    session_range = session_high - session_low
    range_pct = (session_range / session_low * 100) if session_low > 0 else 0

    # Find timing of high and low
    high_idx = highs.index(session_high)
    low_idx = lows.index(session_low)
    high_time = candles[high_idx]["timestamp"].strftime("%H:%M")
    low_time = candles[low_idx]["timestamp"].strftime("%H:%M")

    direction = "bullish" if session_close > session_open else "bearish"
    dt = datetime.strptime(day_key, "%Y-%m-%d")
    dow = WEEKDAYS[dt.weekday()]

    return {
        "event_type": "session_range",
        "data": {
            "high": round(session_high, 6),
            "low": round(session_low, 6),
            "open": round(session_open, 6),
            "close": round(session_close, 6),
            "range": round(session_range, 6),
            "range_pct": round(range_pct, 3),
            "direction": direction,
            "high_time": high_time,
            "low_time": low_time,
            "day_of_week": dow,
            "candle_count": len(candles),
        },
    }


def _detect_sweep(
    prior_session_candles: list[dict],
    current_session_candles: list[dict],
    prior_session: str,
    current_session: str,
    day_key: str,
) -> dict | None:
    """Detect if current session swept the prior session's H or L."""
    if not prior_session_candles or not current_session_candles:
        return None

    prior_high = max(float(c["high"]) for c in prior_session_candles)
    prior_low = min(float(c["low"]) for c in prior_session_candles)

    swept_high = False
    swept_low = False
    sweep_price = 0.0
    sweep_time = ""
    reversed_after = False
    reversal_distance = 0.0

    for c in current_session_candles:
        h, l, close = float(c["high"]), float(c["low"]), float(c["close"])

        # Swept high: wick above prior high
        if h > prior_high and not swept_high:
            swept_high = True
            sweep_price = h
            sweep_time = c["timestamp"].strftime("%H:%M")
            # Check if it reversed (closed below prior high)
            if close < prior_high:
                reversed_after = True
                reversal_distance = sweep_price - close

        # Swept low: wick below prior low
        if l < prior_low and not swept_low:
            swept_low = True
            sweep_price = l
            sweep_time = c["timestamp"].strftime("%H:%M")
            if close > prior_low:
                reversed_after = True
                reversal_distance = close - sweep_price

    if not swept_high and not swept_low:
        return None

    dt = datetime.strptime(day_key, "%Y-%m-%d")
    dow = WEEKDAYS[dt.weekday()]

    swept_side = "high" if swept_high else "low"
    if swept_high and swept_low:
        swept_side = "both"

    return {
        "event_type": f"{prior_session}_sweep",
        "session": current_session,
        "data": {
            "swept_side": swept_side,
            "prior_high": round(prior_high, 6),
            "prior_low": round(prior_low, 6),
            "sweep_price": round(sweep_price, 6),
            "sweep_time": sweep_time,
            "reversal": reversed_after,
            "reversal_distance": round(reversal_distance, 6),
            "day_of_week": dow,
            "prior_session": prior_session,
        },
    }


def _detect_ny_continuation(
    london_candles: list[dict],
    ny_candles: list[dict],
    day_key: str,
) -> dict | None:
    """Detect whether NY continued or reversed London's move."""
    if not london_candles or not ny_candles:
        return None

    london_open = float(london_candles[0]["open"])
    london_close = float(london_candles[-1]["close"])
    london_dir = "bullish" if london_close > london_open else "bearish"

    ny_open = float(ny_candles[0]["open"])
    ny_close = float(ny_candles[-1]["close"])
    ny_dir = "bullish" if ny_close > ny_open else "bearish"

    continuation = london_dir == ny_dir
    dt = datetime.strptime(day_key, "%Y-%m-%d")

    return {
        "event_type": "ny_continuation",
        "data": {
            "london_direction": london_dir,
            "ny_direction": ny_dir,
            "continuation": continuation,
            "london_range": round(max(float(c["high"]) for c in london_candles) -
                                  min(float(c["low"]) for c in london_candles), 6),
            "ny_range": round(max(float(c["high"]) for c in ny_candles) -
                              min(float(c["low"]) for c in ny_candles), 6),
            "day_of_week": WEEKDAYS[dt.weekday()],
        },
    }


def _detect_power_of_3(
    asia_candles: list[dict],
    london_candles: list[dict],
    ny_candles: list[dict],
    avg_daily_range: float,
    day_key: str,
) -> dict | None:
    """Detect Power of 3 (Accumulation → Manipulation → Distribution).

    Conditions:
    - Accumulation: Asia range is tight (< 50% of ADR)
    - Manipulation: London sweeps one side of Asia range
    - Distribution: Price trends away from the sweep in the opposite direction
      (London + NY combined move > Asia range)

    Success = distribution move was at least 1.5x the Asia range.
    """
    if not asia_candles or not london_candles or avg_daily_range <= 0:
        return None

    asia_high = max(float(c["high"]) for c in asia_candles)
    asia_low = min(float(c["low"]) for c in asia_candles)
    asia_range = asia_high - asia_low

    # Check accumulation: Asia range < 50% of ADR
    if asia_range >= avg_daily_range * 0.5:
        return None  # not tight enough

    # Check manipulation: did London sweep Asia H or L?
    swept_high = False
    swept_low = False
    for c in london_candles:
        if float(c["high"]) > asia_high:
            swept_high = True
        if float(c["low"]) < asia_low:
            swept_low = True

    if not swept_high and not swept_low:
        return None  # no manipulation

    # Check distribution: combine London + NY candles for the move
    all_after = london_candles + (ny_candles or [])
    if not all_after:
        return None

    day_high = max(float(c["high"]) for c in all_after)
    day_low = min(float(c["low"]) for c in all_after)
    day_close = float(all_after[-1]["close"])

    # If swept high → expect bearish distribution (down)
    # If swept low → expect bullish distribution (up)
    if swept_high and not swept_low:
        manipulation_side = "high"
        # Distribution = how far price dropped from Asia low
        distribution_distance = asia_low - day_low
        distribution_success = distribution_distance > asia_range * 1.5
        distribution_direction = "bearish"
    elif swept_low and not swept_high:
        manipulation_side = "low"
        distribution_distance = day_high - asia_high
        distribution_success = distribution_distance > asia_range * 1.5
        distribution_direction = "bullish"
    else:
        manipulation_side = "both"
        # Both swept — use close direction
        if day_close > (asia_high + asia_low) / 2:
            distribution_distance = day_high - asia_high
            distribution_direction = "bullish"
        else:
            distribution_distance = asia_low - day_low
            distribution_direction = "bearish"
        distribution_success = distribution_distance > asia_range * 1.5

    dt = datetime.strptime(day_key, "%Y-%m-%d")

    return {
        "event_type": "power_of_3",
        "data": {
            "asia_range": round(asia_range, 6),
            "asia_range_pct_of_adr": round(asia_range / avg_daily_range * 100, 1),
            "manipulation_side": manipulation_side,
            "distribution_direction": distribution_direction,
            "distribution_distance": round(distribution_distance, 6),
            "distribution_success": distribution_success,
            "asia_high": round(asia_high, 6),
            "asia_low": round(asia_low, 6),
            "day_high": round(day_high, 6),
            "day_low": round(day_low, 6),
            "day_close": round(day_close, 6),
            "day_of_week": WEEKDAYS[dt.weekday()],
        },
    }
