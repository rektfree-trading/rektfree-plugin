"""
Pure-Python ETH Profile / Previous-VA-POC test (vendored from the backend).

DB-free port of the backend's ``app/services/eth_profile_stats.py``. For each
RTH trading day the hosted product builds an RTH-bounded TPO profile, captures
that day's POC / VAH / VAL, then walks the NEXT day's intraday candles to detect
whether price touched the PRIOR day's POC / VAH / VAL (and at what time). It
PERSISTS one ``eth_profile_test`` row per day and aggregates with the
``/stats/eth-profile`` router. The plugin has no database — so the tool layer
feeds in-memory candles to these detectors and walks the days chronologically in
Python, chaining each day's profile forward as the next day's ``prev_*`` levels.

The daily profile is built by REUSING the vendored ``engines.market_profile``
``compute_profiles`` engine **unchanged** — calling it with ``timeframe="1H"``
groups candles by UTC date, so feeding it a single day's RTH-window 15m candles
yields exactly one profile (the one we want). We do NOT pass ``"15m"`` because
that triggers per-hour sub-sessions which would slice the RTH window.

Only the pure parts are vendored. RTH conventions come from the shared
``engines.rth_conventions`` module. Nothing here imports from ``app.*`` or
sqlalchemy / numpy / pandas.

CANDLE SHAPE: detectors expect a candle dict with a tz-aware UTC ``datetime`` at
``c["timestamp"]`` plus float ``open/high/low/close``. The tool layer adapts the
fetcher's float-unix-second candles before calling these functions.
"""

from __future__ import annotations

from datetime import date, datetime

from engines import market_profile as profile_engine
from engines.rth_conventions import convention_for, window_for_symbol

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Confidence + distribution primitives (vendored from app.utils.stat_primitives)
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
    from statistics import mean, median
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
    if total_minutes is None:
        return None
    m = int(round(total_minutes))
    if m < 0:
        m = 0
    if m >= 24 * 60:
        m = 24 * 60 - 1
    return f"{m // 60:02d}:{m % 60:02d}"


def _hhmm_to_minutes(s: str | None) -> int | None:
    if not s or not isinstance(s, str) or ":" not in s:
        return None
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Slice helper (pure)
# ---------------------------------------------------------------------------

def _slice_window(candles: list[dict], start: datetime, end: datetime) -> list[dict]:
    """Inclusive-start, exclusive-end UTC window slice."""
    out: list[dict] = []
    for c in candles:
        ts = c["timestamp"]
        if start <= ts < end:
            out.append(c)
    return out


# ---------------------------------------------------------------------------
# Daily profile (reuses the vendored market_profile engine, unchanged)
# ---------------------------------------------------------------------------

def compute_today_profile(
    rth_15m: list[dict],
) -> tuple[float | None, float | None, float | None, int]:
    """Run TPO on a single RTH window worth of 15m candles via the shared
    ``market_profile`` engine. Returns (poc, vah, val, tpo_total); all-None / 0
    if a profile couldn't be built."""
    if len(rth_15m) < 2:
        return None, None, None, 0

    highs = [float(c["high"]) for c in rth_15m]
    lows = [float(c["low"]) for c in rth_15m]
    closes = [float(c["close"]) for c in rth_15m]
    times = [c["timestamp"].timestamp() for c in rth_15m]

    # timeframe="1H" groups by UTC date; since all candles are within a single
    # date's RTH window, we get exactly one TPOProfile back.
    profiles = profile_engine.compute_profiles(
        highs=highs,
        lows=lows,
        closes=closes,
        times=times,
        timeframe="1H",
        max_sessions=1,
    )
    if not profiles:
        return None, None, None, 0
    p = profiles[-1]
    return p.poc, p.vah, p.val, p.total_tpos


# ---------------------------------------------------------------------------
# Per-day computation (body of backend's compute_eth_profile loop, no DB)
# ---------------------------------------------------------------------------

def compute_day(
    symbol: str,
    today: date,
    rth_15m: list[dict],
    rth_1h: list[dict],
    prev_poc: float | None,
    prev_vah: float | None,
    prev_val: float | None,
    convention_name: str,
    rth_window_label: str,
) -> dict | None:
    """Compute one ETH-profile day. Returns the ``data`` dict the backend would
    persist, or ``None`` if today's profile couldn't be built (caller leaves the
    prev_* chain intact)."""
    if not rth_15m:
        return None

    today_poc, today_vah, today_val, tpo_total = compute_today_profile(rth_15m)
    if today_poc is None or today_vah is None or today_val is None:
        return None

    rth_high = max(float(c["high"]) for c in rth_15m)
    rth_low = min(float(c["low"]) for c in rth_15m)
    rth_open = float(rth_15m[0]["open"])
    rth_close = float(rth_15m[-1]["close"])
    rth_range = rth_high - rth_low

    touched_prev_poc = False
    touched_prev_vah = False
    touched_prev_val = False
    prev_poc_touch_time: str | None = None
    prev_vah_touch_time: str | None = None
    prev_val_touch_time: str | None = None

    if prev_poc is not None and prev_vah is not None and prev_val is not None:
        for c in rth_1h:
            h = float(c["high"])
            l = float(c["low"])
            ts = c["timestamp"]
            tlabel = f"{ts.hour:02d}:{ts.minute:02d}"
            if not touched_prev_poc and l <= prev_poc <= h:
                touched_prev_poc = True
                prev_poc_touch_time = tlabel
            if not touched_prev_vah and l <= prev_vah <= h:
                touched_prev_vah = True
                prev_vah_touch_time = tlabel
            if not touched_prev_val and l <= prev_val <= h:
                touched_prev_val = True
                prev_val_touch_time = tlabel
            if touched_prev_poc and touched_prev_vah and touched_prev_val:
                break

    return {
        "rth_convention": convention_name,
        "rth_window_utc": rth_window_label,
        "rth_high": round(rth_high, 6),
        "rth_low": round(rth_low, 6),
        "rth_range": round(rth_range, 6),
        "rth_open": round(rth_open, 6),
        "rth_close": round(rth_close, 6),
        "today_poc": round(float(today_poc), 6),
        "today_vah": round(float(today_vah), 6),
        "today_val": round(float(today_val), 6),
        "prev_poc": round(float(prev_poc), 6) if prev_poc is not None else None,
        "prev_vah": round(float(prev_vah), 6) if prev_vah is not None else None,
        "prev_val": round(float(prev_val), 6) if prev_val is not None else None,
        "touched_prev_poc": touched_prev_poc,
        "touched_prev_vah": touched_prev_vah,
        "touched_prev_val": touched_prev_val,
        "prev_poc_touch_time": prev_poc_touch_time,
        "prev_vah_touch_time": prev_vah_touch_time,
        "prev_val_touch_time": prev_val_touch_time,
        "tpo_total": int(tpo_total),
        "tpo_sample_label": confidence_label(int(tpo_total)),
        "candle_source": "1H",
        "day_of_week": WEEKDAYS[today.weekday()],
    }


def build_events(
    symbol: str,
    m15_by_day: dict,
    h1_by_day: dict,
) -> list[dict]:
    """Walk days chronologically, chaining each day's profile forward as the
    next day's prev_* levels. Mirrors the backend's chronological loop."""
    convention_name, windows = convention_for(symbol)
    rth_start_str, rth_end_str = windows["rth"]
    rth_window_label = f"{rth_start_str}-{rth_end_str}"

    days = sorted(set(m15_by_day.keys()) & set(h1_by_day.keys()))

    prev_poc: float | None = None
    prev_vah: float | None = None
    prev_val: float | None = None

    events: list[dict] = []
    for today in days:
        rth_start, rth_end = window_for_symbol(symbol, today, "rth")
        rth_15m = _slice_window(m15_by_day.get(today, []), rth_start, rth_end)
        rth_1h = _slice_window(h1_by_day.get(today, []), rth_start, rth_end)

        data = compute_day(
            symbol=symbol,
            today=today,
            rth_15m=rth_15m,
            rth_1h=rth_1h,
            prev_poc=prev_poc,
            prev_vah=prev_vah,
            prev_val=prev_val,
            convention_name=convention_name,
            rth_window_label=rth_window_label,
        )
        if data is None:
            # Preserve the chain (last known good prev_*) for the next day.
            continue

        events.append(data)
        prev_poc = data["today_poc"]
        prev_vah = data["today_vah"]
        prev_val = data["today_val"]

    return events


# ---------------------------------------------------------------------------
# Aggregations (mirror the /stats/eth-profile router endpoints)
# ---------------------------------------------------------------------------

def agg_touch(events: list[dict]) -> dict:
    """Previous-day POC / VAH / VAL touch frequencies + average touch times.
    Only days that HAD prior levels (prev_poc not null) count toward the rate —
    this mirrors the backend, where the first day has prev_*=null and all
    touched_*=false (it counts as a non-touch over the full sample)."""
    n = len(events)
    poc_hits = vah_hits = val_hits = 0
    poc_minutes: list[int] = []
    vah_minutes: list[int] = []
    val_minutes: list[int] = []
    quality_normal = 0

    for r in events:
        if r.get("touched_prev_poc"):
            poc_hits += 1
            m = _hhmm_to_minutes(r.get("prev_poc_touch_time"))
            if m is not None:
                poc_minutes.append(m)
        if r.get("touched_prev_vah"):
            vah_hits += 1
            m = _hhmm_to_minutes(r.get("prev_vah_touch_time"))
            if m is not None:
                vah_minutes.append(m)
        if r.get("touched_prev_val"):
            val_hits += 1
            m = _hhmm_to_minutes(r.get("prev_val_touch_time"))
            if m is not None:
                val_minutes.append(m)
        if r.get("tpo_sample_label") and r.get("tpo_sample_label") != "insufficient":
            quality_normal += 1

    if n > 0:
        prev_poc_pct = round(poc_hits / n * 100, 1)
        prev_vah_pct = round(vah_hits / n * 100, 1)
        prev_val_pct = round(val_hits / n * 100, 1)
        tpo_quality_normal_pct = round(quality_normal / n * 100, 1)
    else:
        prev_poc_pct = prev_vah_pct = prev_val_pct = tpo_quality_normal_pct = 0.0

    avg_poc = sum(poc_minutes) / len(poc_minutes) if poc_minutes else None
    avg_vah = sum(vah_minutes) / len(vah_minutes) if vah_minutes else None
    avg_val = sum(val_minutes) / len(val_minutes) if val_minutes else None

    return {
        "n": n,
        "confidence": confidence_label(n),
        "prev_poc_pct": prev_poc_pct,
        "prev_vah_pct": prev_vah_pct,
        "prev_val_pct": prev_val_pct,
        "tpo_quality_normal_pct": tpo_quality_normal_pct,
        "avg_prev_poc_touch_time": _format_avg_minute(avg_poc),
        "avg_prev_vah_touch_time": _format_avg_minute(avg_vah),
        "avg_prev_val_touch_time": _format_avg_minute(avg_val),
    }


def agg_extension(events: list[dict]) -> dict:
    """Distribution of RTH range across the events, mirroring
    ``/stats/eth-profile/extension``."""
    ranges: list[float] = []
    for r in events:
        v = r.get("rth_range")
        if v is None:
            continue
        try:
            ranges.append(float(v))
        except (TypeError, ValueError):
            continue
    return {
        "n": len(ranges),
        "confidence": confidence_label(len(ranges)),
        "rth_extension": extension_block(ranges),
    }
