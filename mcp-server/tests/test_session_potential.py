"""Offline deterministic tests for the Session Potential card.

We synthesize 1H candle sets where we KNOW each session's range, when its high
and low form, and how it relates to the prior session, then assert the
direction / hod_lod / timing / breakout blocks plus confidence buckets and
history capping — without touching the network or the MCP decorator.
"""

from datetime import datetime, timezone

from engines import session_extension_stats as ext_engine
from engines import session_stats as sess_engine
from tools import session_extension_stats as ext_tool
from tools import session_potential as tool


# --- helpers --------------------------------------------------------------

def _ts(day: str, hour: int) -> float:
    y, m, d = (int(x) for x in day.split("-"))
    return datetime(y, m, d, hour, 0, tzinfo=timezone.utc).timestamp()


def _c(day: str, hour: int, o: float, h: float, l: float, cl: float) -> dict:
    return {"time": _ts(day, hour), "open": o, "high": h, "low": l, "close": cl, "volume": 1.0}


def _summaries(candles: list[dict]) -> dict[str, dict]:
    grouped = sess_engine._group_by_day_and_session(ext_tool._adapt_candles(candles))
    return ext_tool._build_day_summaries(grouped)


def _grouped(candles: list[dict]):
    return sess_engine._group_by_day_and_session(ext_tool._adapt_candles(candles))


# --- confidence buckets ----------------------------------------------------

def test_confidence_buckets():
    assert tool._confidence(50) == "HIGH"
    assert tool._confidence(20) == "MEDIUM"
    assert tool._confidence(19) == "LOW"
    assert tool._confidence(5) == "LOW"
    assert tool._confidence(4) == "INSUFFICIENT"


# --- session timing (new engine function) ---------------------------------

def test_session_timing_windows_and_peak_hour():
    # London: low at 08:00, high at 12:00, on a clearly long day.
    # Day high (NY 130) > day open (asia open 100) → up_leg dominates → long.
    candles = []
    day = "2026-03-02"
    # asia: hours 0-7, flat-ish, open 100
    for hr in range(0, 8):
        candles.append(_c(day, hr, 100.0, 101.0, 99.0, 100.0))
    # london hours 8-12: low forms at 08 (88), high at 12 (115)
    candles.append(_c(day, 8, 100.0, 101.0, 88.0, 95.0))   # london low
    candles.append(_c(day, 9, 95.0, 100.0, 94.0, 99.0))
    candles.append(_c(day, 10, 99.0, 105.0, 98.0, 104.0))
    candles.append(_c(day, 11, 104.0, 110.0, 103.0, 109.0))
    candles.append(_c(day, 12, 109.0, 115.0, 108.0, 114.0))  # london high
    # ny hours 13-20: pushes day high to 130
    for hr in range(13, 21):
        candles.append(_c(day, hr, 114.0, 130.0, 113.0, 129.0))

    summaries = _summaries(candles)
    block = ext_engine.session_timing_for(summaries, "london")
    # Long day → the long_expected window holds the data.
    long_block = block["long_expected"]
    assert long_block["low_peak_hour"] == 8     # london low formed at 08:00
    assert long_block["high_peak_hour"] == 12    # london high formed at 12:00
    # short bucket is empty for this single long day
    assert block["short_expected"]["sample_size"] == 0


def test_format_window_p25_p75():
    win, peak = ext_engine.format_window([8, 8, 9, 10, 12])
    assert win.endswith(":59") and win[:2].isdigit()
    assert peak == 9  # median of [8,8,9,10,12]


def test_format_window_empty():
    assert ext_engine.format_window([]) == ("--:--", 0)


# --- hod_lod for a session -------------------------------------------------

def test_hod_lod_for_session_counts():
    # 2 days. NY makes the day high both days; asia makes the low both days.
    candles = []
    for day in ("2026-04-01", "2026-04-02"):
        for hr in range(0, 8):       # asia: low 80
            candles.append(_c(day, hr, 100.0, 101.0, 80.0, 100.0))
        for hr in range(8, 13):      # london: mid
            candles.append(_c(day, hr, 100.0, 110.0, 95.0, 105.0))
        for hr in range(13, 21):     # ny: high 140
            candles.append(_c(day, hr, 105.0, 140.0, 104.0, 139.0))
    summaries = _summaries(candles)

    ny = tool._hod_lod_for_session(summaries, "new_york")
    assert ny["n"] == 2
    assert ny["hod_pct"] == 100.0    # NY printed the high both days
    assert ny["lod_pct"] == 0.0

    asia = tool._hod_lod_for_session(summaries, "asia")
    assert asia["lod_pct"] == 100.0  # asia printed the low both days
    assert asia["hod_pct"] == 0.0


# --- direction for a session ----------------------------------------------

def test_direction_for_session_long_skew():
    # One long day (up_leg dominates) with london present.
    candles = []
    day = "2026-05-04"  # a Monday
    for hr in range(0, 8):
        candles.append(_c(day, hr, 100.0, 101.0, 99.0, 100.0))   # open 100
    for hr in range(8, 13):
        candles.append(_c(day, hr, 100.0, 108.0, 98.0, 107.0))
    for hr in range(13, 21):
        candles.append(_c(day, hr, 107.0, 150.0, 106.0, 149.0))  # huge up leg
    summaries = _summaries(candles)
    block = tool._direction_for_session(summaries, "london")
    assert block["n"] == 1
    assert block["long_pct"] == 100.0
    assert "Monday" in block["by_day_of_week"]


# --- breakout grid: london extends asia -----------------------------------

def test_breakout_grid_london_breaks_asia_high_then_low():
    # Asia range [90, 110]. London first breaks the high (08:00), then the
    # low (10:00) → cell 'both', order 'h_then_l'.
    candles = []
    day = "2026-06-01"
    for hr in range(0, 8):
        candles.append(_c(day, hr, 100.0, 110.0, 90.0, 100.0))   # asia 90-110
    candles.append(_c(day, 8, 100.0, 115.0, 100.0, 112.0))       # breaks high first
    candles.append(_c(day, 9, 112.0, 113.0, 100.0, 105.0))
    candles.append(_c(day, 10, 105.0, 106.0, 85.0, 88.0))        # breaks low later
    candles.append(_c(day, 11, 88.0, 92.0, 87.0, 90.0))
    candles.append(_c(day, 12, 90.0, 95.0, 89.0, 94.0))
    for hr in range(13, 21):
        candles.append(_c(day, hr, 94.0, 96.0, 93.0, 95.0))

    grouped = _grouped(candles)
    summaries = ext_tool._build_day_summaries(grouped)
    ext = ext_tool._agg_extensions(grouped, summaries)
    london = ext["london"]
    assert london["vs_prior_session"] == "asia"
    assert london["both_pct"] == 100.0
    assert london["h_then_l_pct"] == 100.0
    assert london["neither_pct"] == 0.0


# --- engine helpers untouched (regression guard) --------------------------

def test_existing_engine_functions_still_present():
    # The append must not have broken the pre-existing public surface.
    assert callable(ext_engine.confidence_label)
    assert callable(ext_engine.extension_block)
    assert callable(ext_engine._compute_day_summary)
    assert callable(ext_engine._classify_breakout_with_sequencing)
    # confidence_label keeps its original (different) bucketing
    assert ext_engine.confidence_label(5) == "insufficient"
    assert ext_engine.confidence_label(100) == "high"


# --- history capping -------------------------------------------------------

def test_history_caps_constants():
    assert tool._MAX_DAYS == 365
    assert tool._MIN_DAYS == 5
    assert tool._VALID_SESSIONS == ("asia", "london", "new_york")
