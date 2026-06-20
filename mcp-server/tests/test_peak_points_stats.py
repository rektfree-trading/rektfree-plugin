"""Offline deterministic tests for the Peak Points engine + tool helpers.

We synthesize 1H candle sets where we KNOW which session prints the day's high
and low, then assert the HOD/LOD classification, the joint matrix and its
percentages, the confidence buckets, and the history capping — all without
touching the network or the MCP decorator.
"""

from datetime import datetime, timezone

from engines import peak_points_stats as engine
from engines import session_stats as sess_engine
from tools import peak_points_stats as tool


# --- helpers --------------------------------------------------------------

def _ts(day: str, hour: int) -> float:
    """Unix seconds for `day` (YYYY-MM-DD) at `hour`:30 UTC."""
    y, m, d = (int(x) for x in day.split("-"))
    return datetime(y, m, d, hour, 30, tzinfo=timezone.utc).timestamp()


def _candle(day: str, hour: int, *, base: float, hi: float, lo: float) -> dict:
    return {
        "time": _ts(day, hour),
        "open": base,
        "close": base,
        "high": hi,
        "low": lo,
        "volume": 1.0,
    }


def _day_candles(day: str, *, asia_hl, london_hl, ny_hl) -> list[dict]:
    """One candle per session for `day`, each with explicit (high, low).

    Asia hour 2 (00:00-08:00), London hour 10 (08:00-13:00),
    NY hour 16 (13:00-21:00).
    """
    out = []
    for (lo, hi), hour in ((asia_hl, 2), (london_hl, 10), (ny_hl, 16)):
        base = (hi + lo) / 2
        out.append(_candle(day, hour, base=base, hi=hi, lo=lo))
    return out


# --- engine: classify a single known day ----------------------------------

def test_classify_day_picks_correct_hod_lod_sessions():
    # NY has the highest high; London has the lowest low.
    candles = _day_candles(
        "2026-01-05",
        asia_hl=(100.0, 110.0),
        london_hl=(95.0, 108.0),    # lowest low = 95 (london)
        ny_hl=(102.0, 120.0),       # highest high = 120 (ny)
    )
    grouped = sess_engine._group_by_day_and_session(tool._adapt_candles(candles))
    rows = tool._classify_days(grouped)
    assert len(rows) == 1
    row = rows[0]
    assert row["hod_session"] == "new_york"
    assert row["lod_session"] == "london"
    assert row["day_high"] == 120.0
    assert row["day_low"] == 95.0
    assert row["day_of_week"] == "Monday"  # 2026-01-05 is a Monday


def test_classify_day_tie_broken_by_earliest_time():
    # Two sessions share the same high value; earliest high_time wins.
    # Asia high at 02:30, London high (same value) at 10:30 → Asia owns HOD.
    candles = _day_candles(
        "2026-01-06",
        asia_hl=(100.0, 115.0),
        london_hl=(99.0, 115.0),    # same high as asia, but later
        ny_hl=(101.0, 110.0),
    )
    grouped = sess_engine._group_by_day_and_session(tool._adapt_candles(candles))
    rows = tool._classify_days(grouped)
    assert rows[0]["hod_session"] == "asia"


# --- engine: matrix + marginals -------------------------------------------

def _row(hod: str, lod: str, direction: str = "bullish") -> dict:
    return {"hod_session": hod, "lod_session": lod, "net_direction": direction}


def test_build_matrix_counts_and_percentages():
    rows = [
        _row("new_york", "asia"),
        _row("new_york", "asia"),
        _row("london", "asia"),
        _row("new_york", "london"),
    ]
    block = engine.build_matrix(rows)
    assert block["sample_size"] == 4
    # joint counts
    assert block["matrix"]["new_york"]["asia"] == 2
    assert block["matrix"]["london"]["asia"] == 1
    assert block["matrix"]["new_york"]["london"] == 1
    # joint percentages
    assert block["matrix_pct"]["new_york"]["asia"] == 50.0
    assert block["matrix_pct"]["london"]["asia"] == 25.0
    # HOD marginals: NY printed the high on 3 of 4 days
    assert block["hod_marginals"]["new_york"] == 3
    assert block["hod_marginals_pct"]["new_york"] == 75.0
    # LOD marginals: asia printed the low on 3 of 4 days
    assert block["lod_marginals"]["asia"] == 3
    assert block["lod_marginals_pct"]["asia"] == 75.0


def test_build_matrix_skips_unknown_sessions():
    rows = [_row("new_york", "asia"), {"hod_session": "??", "lod_session": "asia"}]
    block = engine.build_matrix(rows)
    assert block["sample_size"] == 1  # the malformed row is dropped


def test_build_matrix_empty_is_all_zero():
    block = engine.build_matrix([])
    assert block["sample_size"] == 0
    assert block["matrix_pct"]["asia"]["asia"] == 0.0
    assert block["hod_marginals_pct"]["new_york"] == 0.0


# --- confidence buckets ----------------------------------------------------

def test_confidence_buckets():
    assert engine.confidence(50) == "HIGH"
    assert engine.confidence(49) == "MEDIUM"
    assert engine.confidence(20) == "MEDIUM"
    assert engine.confidence(19) == "LOW"
    assert engine.confidence(5) == "LOW"
    assert engine.confidence(4) == "INSUFFICIENT"
    assert engine.confidence(0) == "INSUFFICIENT"


# --- net direction ---------------------------------------------------------

def test_net_direction_bullish_when_up_leg_dominates():
    sessions = [
        {"session": "asia", "open": 100.0, "close": 108.0},      # +8
        {"session": "london", "open": 108.0, "close": 105.0},    # -3
    ]
    assert engine._net_direction(sessions) == "bullish"


def test_net_direction_bearish_when_down_leg_dominates():
    sessions = [
        {"session": "asia", "open": 100.0, "close": 102.0},      # +2
        {"session": "london", "open": 102.0, "close": 90.0},     # -12
    ]
    assert engine._net_direction(sessions) == "bearish"


# --- multi-day integration via the tool helpers ---------------------------

def test_classify_days_multiday_matrix_and_marginals():
    # Build 3 deterministic days, each with a known HOD/LOD session.
    days = [
        # day1: HOD ny, LOD asia
        ("2026-02-02", (90.0, 100.0), (92.0, 105.0), (95.0, 120.0)),
        # day2: HOD ny, LOD asia
        ("2026-02-03", (88.0, 100.0), (92.0, 106.0), (96.0, 118.0)),
        # day3: HOD london, LOD ny
        ("2026-02-04", (100.0, 110.0), (101.0, 130.0), (90.0, 112.0)),
    ]
    all_candles: list[dict] = []
    for day, asia, london, ny in days:
        all_candles += _day_candles(day, asia_hl=asia, london_hl=london, ny_hl=ny)
    grouped = sess_engine._group_by_day_and_session(tool._adapt_candles(all_candles))
    rows = tool._classify_days(grouped)
    assert len(rows) == 3

    block = engine.build_matrix(rows)
    assert block["sample_size"] == 3
    assert block["matrix"]["new_york"]["asia"] == 2
    assert block["matrix"]["london"]["new_york"] == 1
    # NY printed the high on 2 of 3 days
    assert block["hod_marginals"]["new_york"] == 2


# --- history capping -------------------------------------------------------

def test_history_caps_constants():
    # The tool caps the lookback at 365 days (1H is light) and requires >= 5.
    assert tool._MAX_DAYS == 365
    assert tool._MIN_DAYS == 5
