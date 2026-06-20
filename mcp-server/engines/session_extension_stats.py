"""
Pure-Python session-extension detectors (vendored from the backend).

DB-free port of the backend's ``app/services/session_extension_stats.py`` (the
"Session Potential" aggregators) plus the shared primitives from
``app/utils/stat_primitives.py``. The hosted product reads ``session_range``
rows out of ``session_events`` and re-fetches 1H candles from the DB to sequence
breakouts; the plugin has no database, so the tool layer feeds in-memory
session-range dicts (built by :mod:`engines.session_stats`) and 1H candle lists
to the SAME pure helpers vendored here.

"Session extension" = how far / how often a session pushes BEYOND the prior
intraday session's range. The core questions:

- Does London extend past Asia's high/low? Does NY extend past London's?
  (``_classify_breakout_with_sequencing`` — only_h / only_l / both / neither,
  plus h_then_l / l_then_h ordering.)
- How big is each session's own range, distributed? (``extension_block`` —
  median / mean / min / max / p25 / p75.)
- Which session prints the day's high or low, and is the day long or short?
  (``_compute_day_summary`` — the same up_leg/down_leg definition the backend
  uses across all five session-potential views.)

Only the **pure** parts are vendored:

- ``confidence_label``                  — sample-size → label
- ``_percentile`` / ``extension_block`` — numeric distribution shape
- ``_compute_day_summary``              — per-day H/L/open/direction + HOD/LOD session
- ``_classify_breakout_with_sequencing``— first-H-break vs first-L-break ordering
- ``SESSIONS`` / ``PREV_SESSION`` / ``SESSION_HOURS`` / ``DOW_ORDER`` constants

DROPPED (DB-coupled, replaced by the tool layer): ``_fetch_session_rows``,
``_fetch_h1_candles``, ``_group_by_day``, and the async ``daily_direction`` /
``hod_lod_potential`` / ``session_timing`` / ``session_breakouts`` /
``per_session_card`` orchestrators. Nothing here imports from ``app.*`` or
sqlalchemy.

CANDLE SHAPE: ``_classify_breakout_with_sequencing`` reads ``c["timestamp"]`` as
a (comparable) timezone-aware UTC ``datetime`` and float ``high``/``low``. The
plugin's Binance fetcher returns a float unix-second ``time``; the tool layer
adapts each candle before calling this function.
"""

from __future__ import annotations

from statistics import mean, median

SESSIONS = ("asia", "london", "new_york")
DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Session UTC hour windows — kept in sync with engines/session_stats.py.
SESSION_HOURS = {
    "asia":     (0, 8),
    "london":   (8, 13),
    "new_york": (13, 21),
}

# For breakouts: which prior intraday session each session "follows".
# Asia has no intraday previous, so it's omitted from the breakouts response.
PREV_SESSION = {
    "london":   "asia",
    "new_york": "london",
}


# ---------------------------------------------------------------------------
# Statistical primitives (vendored from app/utils/stat_primitives.py)
# ---------------------------------------------------------------------------

def confidence_label(n: int) -> str:
    if n < 10:
        return "insufficient"
    if n < 30:
        return "low"
    if n < 100:
        return "normal"
    return "high"


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return float(sorted_values[f])
    return float(sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f))


def extension_block(values: list[float], *, decimals: int = 6) -> dict:
    """Median / mean / min / max / p25 / p75 + sample_size + confidence."""
    n = len(values)
    if n == 0:
        return {
            "median": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0,
            "p25": 0.0, "p75": 0.0,
            "sample_size": 0, "confidence": "insufficient",
        }
    floats = [float(v) for v in values]
    sorted_vals = sorted(floats)
    return {
        "median": round(float(median(floats)), decimals),
        "mean": round(float(mean(floats)), decimals),
        "min": round(float(min(floats)), decimals),
        "max": round(float(max(floats)), decimals),
        "p25": round(_percentile(sorted_vals, 0.25), decimals),
        "p75": round(_percentile(sorted_vals, 0.75), decimals),
        "sample_size": n,
        "confidence": confidence_label(n),
    }


# ---------------------------------------------------------------------------
# Per-day summary (vendored from session_extension_stats._compute_day_summary)
# ---------------------------------------------------------------------------

def _compute_day_summary(day_rows: dict[str, dict]) -> dict | None:
    """Per-day high/low/open/direction + which session printed HOD / LOD.

    ``day_rows`` maps session name → session_range data dict (from the
    session_stats engine). Returns None if the day has no usable session rows.

    Day-direction definition (identical to the backend, used across every view):
        day_open  = asia.open (fallback: earliest session open available)
        day_high  = max(session.high)
        day_low   = min(session.low)
        up_leg    = day_high - day_open
        down_leg  = day_open  - day_low
        direction = "long" if up_leg >= down_leg else "short"
    """
    if not day_rows:
        return None

    # Choose day open in priority order: asia → london → new_york
    day_open = None
    for s in SESSIONS:
        if s in day_rows and day_rows[s].get("open") is not None:
            day_open = float(day_rows[s]["open"])
            break
    if day_open is None:
        return None

    highs = {s: float(r["high"]) for s, r in day_rows.items() if r.get("high") is not None}
    lows = {s: float(r["low"]) for s, r in day_rows.items() if r.get("low") is not None}
    if not highs or not lows:
        return None

    day_high = max(highs.values())
    day_low = min(lows.values())
    # The session that produced the daily extreme (first match if tied)
    hod_session = next(s for s, h in highs.items() if h == day_high)
    lod_session = next(s for s, l in lows.items() if l == day_low)

    up_leg = max(day_high - day_open, 0.0)
    down_leg = max(day_open - day_low, 0.0)
    direction = "long" if up_leg >= down_leg else "short"

    # day_of_week — pick the first available row's value
    dow = None
    for r in day_rows.values():
        if r.get("day_of_week"):
            dow = r["day_of_week"]
            break

    return {
        "day_open": day_open,
        "day_high": day_high,
        "day_low": day_low,
        "up_leg": up_leg,
        "down_leg": down_leg,
        "direction": direction,
        "hod_session": hod_session,
        "lod_session": lod_session,
        "day_of_week": dow,
    }


# ---------------------------------------------------------------------------
# Breakout sequencing (vendored from
# session_extension_stats._classify_breakout_with_sequencing)
# ---------------------------------------------------------------------------

def _classify_breakout_with_sequencing(
    session_candles: list[dict],
    prev_high: float,
    prev_low: float,
) -> tuple[str, str | None]:
    """Walk the current session's 1H candles; return (cell, sequence).

    cell ∈ {only_h, only_l, both, neither} — did the session extend beyond the
    prior session's high, low, both, or neither?
    sequence ∈ {h_then_l, l_then_h, None} — only set when cell == 'both', the
    order the two extensions happened.

    ``session_candles`` each carry ``timestamp`` (comparable datetime) +
    ``high``/``low``.
    """
    first_h_ts = None
    first_l_ts = None
    for c in session_candles:
        if first_h_ts is None and c["high"] > prev_high:
            first_h_ts = c["timestamp"]
        if first_l_ts is None and c["low"] < prev_low:
            first_l_ts = c["timestamp"]
        if first_h_ts is not None and first_l_ts is not None:
            break

    if first_h_ts is None and first_l_ts is None:
        return "neither", None
    if first_h_ts is not None and first_l_ts is None:
        return "only_h", None
    if first_h_ts is None and first_l_ts is not None:
        return "only_l", None
    # both — order by which timestamp came first
    if first_h_ts <= first_l_ts:
        return "both", "h_then_l"
    return "both", "l_then_h"
