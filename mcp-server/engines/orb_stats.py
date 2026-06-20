"""
Pure-Python Opening Range Breakout (ORB) detectors (vendored from the backend).

DB-free port of the backend's ``app/services/orb_stats.py``. The hosted product
streams full 1m (fallback 5m) history, records per-day ORB-window high/low (the
first ``orb_minutes`` of the RTH session), the post-ORB extremes, the first-break
side, the two-side-break flag and the outcome category, PERSISTS one
``orb_period`` row per day, then aggregates with the ``/stats/orb`` router. The
plugin has no database — so the tool layer feeds in-memory 5m candles to these
detectors and aggregates the events in Python.

Only the **pure** math is vendored, keeping the ORB definitions identical to
production:

- ``_slice_window``      — candles whose timestamp is in ``[start, end)``
- ``compute_orb_for_day``— body of the backend's per-day loop (no DB save)
- ``agg_breakouts`` / ``agg_extension`` — mirror the ``/stats/orb/breakouts``
  and ``/stats/orb/extension`` router aggregations (counts + percentages +
  distributions + confidence), plus an ORB-size-relative extension distribution
  (extensions expressed as multiples of the opening range).

The backend prefers 1m candles (15 fit cleanly in a 15-minute ORB) with a 5m
fallback. The plugin's keyless Binance fetcher does not page 1m deeply enough for
a useful window, so the tool layer feeds **5m** candles only (3 candles span a
15-minute ORB). The ``orb_minutes`` argument lets the window differ from 15;
``compute_orb_for_day`` derives the ORB-end from ``orb_minutes`` rather than the
convention's ``orb`` window so the caller controls resolution.

RTH conventions are imported from the shared ``engines.rth_conventions`` module.
Nothing here imports from ``app.*`` or sqlalchemy.

CANDLE SHAPE: each detector expects a candle dict with a timezone-aware UTC
``datetime`` at ``c["timestamp"]`` plus float ``open/high/low/close``. The
plugin's Binance fetcher returns float unix-second ``time`` + ohlc, so the tool
layer adapts each candle before calling these functions.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import mean, median

from engines.rth_conventions import convention_for, window_for_symbol

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Confidence + distribution primitives (vendored from app.utils.stat_primitives)
# ---------------------------------------------------------------------------

def confidence_label(n: int) -> str:
    """Four-rung sample-size label (matches the backend, >=100/>=30/>=10/else)."""
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
    """median / mean / min / max / p25 / p75 + sample_size + confidence —
    mirrors ``app.utils.stat_primitives.extension_block``."""
    n = len(values)
    if n == 0:
        return {
            "median": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0,
            "p25": 0.0, "p75": 0.0,
            "sample_size": 0, "confidence": "insufficient",
        }
    floats = [float(v) for v in values]
    sv = sorted(floats)
    return {
        "median": round(float(median(floats)), decimals),
        "mean": round(float(mean(floats)), decimals),
        "min": round(float(min(floats)), decimals),
        "max": round(float(max(floats)), decimals),
        "p25": round(_percentile(sv, 0.25), decimals),
        "p75": round(_percentile(sv, 0.75), decimals),
        "sample_size": n,
        "confidence": confidence_label(n),
    }


def _format_avg_minute(total_minutes: float | None) -> str | None:
    """Average minute-of-day (0-1439 float) → HH:MM (matches the router)."""
    if total_minutes is None:
        return None
    m = int(round(total_minutes))
    if m < 0:
        m = 0
    if m >= 24 * 60:
        m = 24 * 60 - 1
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------------------------------------------------------------------------
# Slice helper (pure)
# ---------------------------------------------------------------------------

def _slice_window(candles: list[dict], start: datetime, end: datetime) -> list[dict]:
    """Return candles whose timestamp falls inside ``[start, end)`` (UTC)."""
    out: list[dict] = []
    for c in candles:
        ts = c["timestamp"]
        if start <= ts < end:
            out.append(c)
    return out


def _hhmm(dt: datetime) -> str:
    return f"{dt.hour:02d}:{dt.minute:02d}"


# ---------------------------------------------------------------------------
# Per-day ORB computation (body of backend's compute_orb loop, no DB save)
# ---------------------------------------------------------------------------

def compute_orb_for_day(
    symbol: str,
    day: date,
    candles_today: list[dict],
    convention_name: str,
    windows: dict,
    orb_minutes: int = 15,
) -> dict | None:
    """Compute ORB stats for a single trading day from fine (5m) candles.

    Returns the ``data`` dict the backend would persist, or ``None`` if the day
    has no ORB-window candles (skipped). The ORB window starts at the RTH open
    and is ``orb_minutes`` long; the post-ORB observation window runs from
    ORB-end through RTH-end.
    """
    orb_start, _conv_orb_end = window_for_symbol(symbol, day, "orb")
    orb_end = orb_start + timedelta(minutes=orb_minutes)
    _, rth_end = window_for_symbol(symbol, day, "rth")
    orb_window_label = f"{_hhmm(orb_start)}-{_hhmm(orb_end)}"

    orb_candles = _slice_window(candles_today, orb_start, orb_end)
    if not orb_candles:
        return None
    post_orb_candles = _slice_window(candles_today, orb_end, rth_end)

    orb_high = max(float(c["high"]) for c in orb_candles)
    orb_low = min(float(c["low"]) for c in orb_candles)
    orb_size = orb_high - orb_low

    # Walk post-ORB candles in chronological order; record the FIRST candle that
    # crosses orb_high or orb_low, then keep scanning to see if BOTH sides break.
    first_break_side: str | None = None
    first_break_time: str | None = None
    broke_high = False
    broke_low = False
    post_orb_high = orb_high
    post_orb_low = orb_low

    for c in post_orb_candles:
        ch = float(c["high"])
        cl = float(c["low"])
        if ch > post_orb_high:
            post_orb_high = ch
        if cl < post_orb_low:
            post_orb_low = cl

        crossed_high = ch >= orb_high
        crossed_low = cl <= orb_low

        if first_break_side is None:
            if crossed_high and crossed_low:
                # Same candle straddles both — default to high to stay
                # deterministic (matches the backend best-effort).
                first_break_side = "high"
                first_break_time = _hhmm(c["timestamp"])
                broke_high = True
                broke_low = True
            elif crossed_high:
                first_break_side = "high"
                first_break_time = _hhmm(c["timestamp"])
                broke_high = True
            elif crossed_low:
                first_break_side = "low"
                first_break_time = _hhmm(c["timestamp"])
                broke_low = True
        else:
            if crossed_high:
                broke_high = True
            if crossed_low:
                broke_low = True

    if broke_high and broke_low:
        outcome = "both"
    elif broke_high:
        outcome = "only_h"
    elif broke_low:
        outcome = "only_l"
    else:
        outcome = "neither"

    orb_up_extension = max(post_orb_high - orb_high, 0.0)
    orb_down_extension = max(orb_low - post_orb_low, 0.0)

    return {
        "rth_convention": convention_name,
        "orb_window_utc": orb_window_label,
        "orb_high": round(orb_high, 6),
        "orb_low": round(orb_low, 6),
        "orb_size": round(orb_size, 6),
        "post_orb_high": round(post_orb_high, 6),
        "post_orb_low": round(post_orb_low, 6),
        "orb_up_extension": round(orb_up_extension, 6),
        "orb_down_extension": round(orb_down_extension, 6),
        "first_break_side": first_break_side,
        "first_break_time": first_break_time,
        "outcome": outcome,
        "two_side_broken": outcome == "both",
        "candle_source": "5m",
        "candle_count_orb": len(orb_candles),
        "day_of_week": WEEKDAYS[day.weekday()],
    }


# ---------------------------------------------------------------------------
# Aggregations (mirror the /stats/orb router endpoints)
# ---------------------------------------------------------------------------

def agg_breakouts(events: list[dict]) -> dict:
    """Outcome distribution + first-break-side distribution + two-side-break
    rate + avg first-break time, mirroring ``/stats/orb/breakouts``."""
    n = len(events)
    counts = {"only_h": 0, "only_l": 0, "both": 0, "neither": 0}
    side_counts = {"high": 0, "low": 0, "none": 0}
    break_minutes: list[int] = []

    for r in events:
        outcome = r.get("outcome")
        if outcome in counts:
            counts[outcome] += 1
        side = r.get("first_break_side")
        if side == "high":
            side_counts["high"] += 1
        elif side == "low":
            side_counts["low"] += 1
        else:
            side_counts["none"] += 1
        t = r.get("first_break_time")
        if t:
            try:
                hh, mm = t.split(":")
                break_minutes.append(int(hh) * 60 + int(mm))
            except (ValueError, AttributeError):
                pass

    if n > 0:
        outcomes = {
            "only_h_pct":  round(counts["only_h"] / n * 100, 1),
            "only_l_pct":  round(counts["only_l"] / n * 100, 1),
            "both_pct":    round(counts["both"] / n * 100, 1),
            "neither_pct": round(counts["neither"] / n * 100, 1),
        }
        first_break = {
            "high_pct": round(side_counts["high"] / n * 100, 1),
            "low_pct":  round(side_counts["low"] / n * 100, 1),
            "none_pct": round(side_counts["none"] / n * 100, 1),
        }
    else:
        outcomes = {"only_h_pct": 0.0, "only_l_pct": 0.0, "both_pct": 0.0, "neither_pct": 0.0}
        first_break = {"high_pct": 0.0, "low_pct": 0.0, "none_pct": 0.0}

    avg_break_minute = sum(break_minutes) / len(break_minutes) if break_minutes else None

    return {
        "n": n,
        "confidence": confidence_label(n),
        "outcomes": outcomes,
        "two_side_pct": outcomes["both_pct"],
        # breakout_rate = any side broke; orb_hold_rate = neither side broke
        "breakout_rate": round((n - counts["neither"]) / n * 100, 1) if n else 0.0,
        "orb_hold_rate": outcomes["neither_pct"],
        "first_break_side": first_break,
        "avg_first_break_time": _format_avg_minute(avg_break_minute),
    }


def agg_extension(events: list[dict]) -> dict:
    """ORB-size + up/down extension distributions, plus the up/down extension
    expressed as MULTIPLES of the opening range, mirroring
    ``/stats/orb/extension`` (with the ratio block added)."""
    sizes: list[float] = []
    ups: list[float] = []
    downs: list[float] = []
    up_mult: list[float] = []
    down_mult: list[float] = []
    for r in events:
        size = r.get("orb_size")
        up = r.get("orb_up_extension")
        down = r.get("orb_down_extension")
        if size is not None:
            sizes.append(float(size))
        if up is not None:
            ups.append(float(up))
        if down is not None:
            downs.append(float(down))
        # Extension as a multiple of the opening range (size>0 only).
        if size is not None and float(size) > 0:
            if up is not None:
                up_mult.append(float(up) / float(size))
            if down is not None:
                down_mult.append(float(down) / float(size))

    return {
        "n": len(events),
        "confidence": confidence_label(len(events)),
        "orb_size": extension_block(sizes),
        "orb_up_extension": extension_block(ups),
        "orb_down_extension": extension_block(downs),
        "orb_up_extension_x_size": extension_block(up_mult, decimals=3),
        "orb_down_extension_x_size": extension_block(down_mult, decimals=3),
    }
