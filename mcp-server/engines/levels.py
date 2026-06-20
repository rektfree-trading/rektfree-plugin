"""
Key price levels computation: Daily/Weekly/Monthly H/L/O, Session H/L.

All times are in UTC.
Sessions: Asia 00:00-08:00, London 08:00-13:00, New York 13:00-21:00.
"""

import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LevelPair:
    high: float = 0.0
    low: float = float("inf")
    open: float = 0.0
    high_time: float = 0.0
    low_time: float = 0.0


@dataclass
class SessionLevel:
    name: str
    high: float = 0.0
    low: float = float("inf")
    high_time: float = 0.0
    low_time: float = 0.0


@dataclass
class LevelsResult:
    # Current period
    daily: LevelPair = field(default_factory=LevelPair)
    weekly: LevelPair = field(default_factory=LevelPair)
    monthly: LevelPair = field(default_factory=LevelPair)
    # Previous period
    prev_daily: LevelPair = field(default_factory=LevelPair)
    prev_weekly: LevelPair = field(default_factory=LevelPair)
    prev_monthly: LevelPair = field(default_factory=LevelPair)
    # Special opens
    daily_open: float = 0.0
    monday_open: float = 0.0
    # Session levels (current day)
    sessions: list[SessionLevel] = field(default_factory=list)
    # Previous session levels
    prev_sessions: list[SessionLevel] = field(default_factory=list)


# Session definitions: (name, start_hour_utc, end_hour_utc)
SESSIONS = [
    ("Asia", 0, 8),
    ("London", 8, 13),
    ("New York", 13, 21),
]


def compute_levels(
    highs: list[float],
    lows: list[float],
    opens: list[float],
    closes: list[float],
    times: list[float],
) -> LevelsResult:
    """Compute key price levels from OHLC data."""
    if not times:
        return LevelsResult()

    result = LevelsResult()
    now = datetime.fromtimestamp(times[-1], tz=timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    # Find start of current week (Monday 00:00 UTC)
    days_since_monday = now.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    prev_monday = this_monday - timedelta(weeks=1)

    # Find start of current month
    this_month_start = today.replace(day=1)
    prev_month_end = this_month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)

    # Convert to unix for comparison
    today_ts = today.timestamp()
    yesterday_ts = yesterday.timestamp()
    this_monday_ts = this_monday.timestamp()
    prev_monday_ts = prev_monday.timestamp()
    this_month_ts = this_month_start.timestamp()
    prev_month_ts = prev_month_start.timestamp()

    # Scan all candles and bucket them
    for i in range(len(times)):
        ts = times[i]
        h = highs[i]
        l = lows[i]
        o = opens[i]
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        hour = dt.hour

        # ─── Daily ───
        if ts >= today_ts:
            _update_level(result.daily, h, l, o, ts, is_first=(result.daily.open == 0))
        elif ts >= yesterday_ts:
            _update_level(result.prev_daily, h, l, o, ts, is_first=(result.prev_daily.open == 0))

        # ─── Weekly ───
        if ts >= this_monday_ts:
            _update_level(result.weekly, h, l, o, ts, is_first=(result.weekly.open == 0))
        elif ts >= prev_monday_ts:
            _update_level(result.prev_weekly, h, l, o, ts, is_first=(result.prev_weekly.open == 0))

        # ─── Monthly ───
        if ts >= this_month_ts:
            _update_level(result.monthly, h, l, o, ts, is_first=(result.monthly.open == 0))
        elif ts >= prev_month_ts:
            _update_level(result.prev_monthly, h, l, o, ts, is_first=(result.prev_monthly.open == 0))

        # ─── Sessions (today only) ───
        if ts >= today_ts:
            for sess_name, sess_start, sess_end in SESSIONS:
                if sess_start <= hour < sess_end:
                    sess = _get_or_create_session(result.sessions, sess_name)
                    if sess.high < h:
                        sess.high = h
                        sess.high_time = ts
                    if sess.low > l:
                        sess.low = l
                        sess.low_time = ts
                    break

        # ─── Sessions (yesterday) ───
        if yesterday_ts <= ts < today_ts:
            for sess_name, sess_start, sess_end in SESSIONS:
                if sess_start <= hour < sess_end:
                    sess = _get_or_create_session(result.prev_sessions, sess_name)
                    if sess.high < h:
                        sess.high = h
                        sess.high_time = ts
                    if sess.low > l:
                        sess.low = l
                        sess.low_time = ts
                    break

    # Set opens
    result.daily_open = result.daily.open
    result.monday_open = result.weekly.open

    # Clean up inf lows
    for level in [result.daily, result.weekly, result.monthly,
                  result.prev_daily, result.prev_weekly, result.prev_monthly]:
        if level.low == float("inf"):
            level.low = 0.0

    for sess in result.sessions + result.prev_sessions:
        if sess.low == float("inf"):
            sess.low = 0.0

    return result


def _update_level(level: LevelPair, h: float, l: float, o: float, ts: float, is_first: bool):
    if is_first:
        level.open = o
    if h > level.high:
        level.high = h
        level.high_time = ts
    if l < level.low:
        level.low = l
        level.low_time = ts


def _get_or_create_session(sessions: list[SessionLevel], name: str) -> SessionLevel:
    for s in sessions:
        if s.name == name:
            return s
    sess = SessionLevel(name=name)
    sessions.append(sess)
    return sess
