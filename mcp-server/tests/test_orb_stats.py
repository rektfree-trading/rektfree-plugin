"""Offline deterministic tests for the pure ORB engine + tool helpers.

We hand-build 5m candles inside the synthetic_ny RTH window (13:30-20:00 UTC)
so we KNOW each day's opening range and which side breaks. No network.
"""

from datetime import datetime, timezone

from engines import orb_stats as engine
from tools import orb_stats as tool


def _c(day_str, hh, mm, o, h, l, cl):
    ts = datetime(2025, 1, int(day_str), hh, mm, tzinfo=timezone.utc)
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": cl}


# ORB window for synthetic_ny with orb_minutes=15 is 13:30-13:45 (one 5m candle
# at 13:30, plus 13:35, 13:40 land inside the [13:30,13:45) slice).
def _orb_day(day, *, orb_high, orb_low, break_side):
    """Build a day's 5m candles: a tight opening range then a directed move."""
    candles = []
    mid = (orb_high + orb_low) / 2
    # Opening range: three 5m candles 13:30/13:35/13:40 spanning [orb_low, orb_high].
    candles.append(_c(day, 13, 30, mid, orb_high, orb_low, mid))
    candles.append(_c(day, 13, 35, mid, orb_high - 1, orb_low + 1, mid))
    candles.append(_c(day, 13, 40, mid, orb_high - 1, orb_low + 1, mid))
    # Post-ORB candles 13:45 onward.
    if break_side == "high":
        # break up only
        candles.append(_c(day, 13, 45, mid, orb_high + 50, mid, orb_high + 40))
        candles.append(_c(day, 13, 50, orb_high + 40, orb_high + 60, orb_high + 30, orb_high + 55))
    elif break_side == "low":
        candles.append(_c(day, 13, 45, mid, mid, orb_low - 50, orb_low - 40))
        candles.append(_c(day, 13, 50, orb_low - 40, orb_low - 30, orb_low - 60, orb_low - 55))
    elif break_side == "both":
        # low first, then high
        candles.append(_c(day, 13, 45, mid, mid, orb_low - 20, orb_low - 10))
        candles.append(_c(day, 13, 50, orb_low - 10, orb_high + 20, orb_low - 10, orb_high + 15))
    else:  # neither — stay strictly inside
        candles.append(_c(day, 13, 45, mid, orb_high - 1, orb_low + 1, mid))
        candles.append(_c(day, 13, 50, mid, orb_high - 1, orb_low + 1, mid))
    return candles


def test_orb_for_day_high_break():
    candles = _orb_day("06", orb_high=100.0, orb_low=90.0, break_side="high")
    _, windows = engine.convention_for("BTCUSDT")
    data = engine.compute_orb_for_day("BTCUSDT", datetime(2025, 1, 6).date(),
                                      candles, "synthetic_ny", windows, orb_minutes=15)
    assert data is not None
    assert data["orb_high"] == 100.0
    assert data["orb_low"] == 90.0
    assert data["orb_size"] == 10.0
    assert data["outcome"] == "only_h"
    assert data["first_break_side"] == "high"
    assert data["orb_window_utc"] == "13:30-13:45"
    # up extension = post_orb_high(160) - orb_high(100) = 60
    assert data["orb_up_extension"] == 60.0
    assert data["orb_down_extension"] == 0.0


def test_orb_for_day_low_then_both():
    candles = _orb_day("07", orb_high=100.0, orb_low=90.0, break_side="both")
    _, windows = engine.convention_for("BTCUSDT")
    data = engine.compute_orb_for_day("BTCUSDT", datetime(2025, 1, 7).date(),
                                      candles, "synthetic_ny", windows, orb_minutes=15)
    assert data["outcome"] == "both"
    assert data["two_side_broken"] is True
    # low crossed first (13:45 low = 70)
    assert data["first_break_side"] == "low"


def test_orb_for_day_neither_holds():
    candles = _orb_day("08", orb_high=100.0, orb_low=90.0, break_side="neither")
    _, windows = engine.convention_for("BTCUSDT")
    data = engine.compute_orb_for_day("BTCUSDT", datetime(2025, 1, 8).date(),
                                      candles, "synthetic_ny", windows, orb_minutes=15)
    assert data["outcome"] == "neither"
    assert data["first_break_side"] is None


def test_orb_for_day_no_window_returns_none():
    # Candles entirely outside the RTH/ORB window → None.
    candles = [_c("06", 2, 0, 100, 101, 99, 100)]
    _, windows = engine.convention_for("BTCUSDT")
    assert engine.compute_orb_for_day("BTCUSDT", datetime(2025, 1, 6).date(),
                                      candles, "synthetic_ny", windows, orb_minutes=15) is None


def test_agg_breakouts_distribution_and_confidence():
    # Build a known mix: 5 high, 3 low, 1 both, 1 neither = 10 days.
    events = []
    for _ in range(5):
        events.append({"outcome": "only_h", "first_break_side": "high",
                       "first_break_time": "13:45", "orb_size": 10.0,
                       "orb_up_extension": 60.0, "orb_down_extension": 0.0})
    for _ in range(3):
        events.append({"outcome": "only_l", "first_break_side": "low",
                       "first_break_time": "13:45", "orb_size": 10.0,
                       "orb_up_extension": 0.0, "orb_down_extension": 40.0})
    events.append({"outcome": "both", "first_break_side": "low",
                   "first_break_time": "13:50", "orb_size": 10.0,
                   "orb_up_extension": 20.0, "orb_down_extension": 20.0})
    events.append({"outcome": "neither", "first_break_side": None,
                   "first_break_time": None, "orb_size": 10.0,
                   "orb_up_extension": 0.0, "orb_down_extension": 0.0})

    b = engine.agg_breakouts(events)
    assert b["n"] == 10
    assert b["outcomes"]["only_h_pct"] == 50.0
    assert b["outcomes"]["only_l_pct"] == 30.0
    assert b["outcomes"]["both_pct"] == 10.0
    assert b["outcomes"]["neither_pct"] == 10.0
    assert b["two_side_pct"] == 10.0
    assert b["breakout_rate"] == 90.0
    assert b["orb_hold_rate"] == 10.0
    # first-break side: high 5, low 3(only_l)+1(both)=4, none 1 → 50/40/10
    assert b["first_break_side"]["high_pct"] == 50.0
    assert b["first_break_side"]["low_pct"] == 40.0
    assert b["first_break_side"]["none_pct"] == 10.0
    # n=10 → "low" confidence (>=10, <30)
    assert b["confidence"] == "low"


def test_agg_extension_multiples_of_range():
    events = [
        {"orb_size": 10.0, "orb_up_extension": 30.0, "orb_down_extension": 0.0},
        {"orb_size": 10.0, "orb_up_extension": 10.0, "orb_down_extension": 0.0},
        {"orb_size": 20.0, "orb_up_extension": 0.0, "orb_down_extension": 40.0},
    ]
    e = engine.agg_extension(events)
    assert e["orb_size"]["median"] == 10.0
    # up multiples: 3.0, 1.0, 0.0 → median 1.0
    assert e["orb_up_extension_x_size"]["median"] == 1.0
    # down multiples: 0.0, 0.0, 2.0 → median 0.0
    assert e["orb_down_extension_x_size"]["median"] == 0.0
    assert e["n"] == 3
    assert e["orb_size"]["confidence"] == "insufficient"  # n<10


def test_build_events_groups_days():
    m5 = []
    m5 += _orb_day("06", orb_high=100.0, orb_low=90.0, break_side="high")
    m5 += _orb_day("07", orb_high=100.0, orb_low=90.0, break_side="low")
    events = tool.build_events("BTCUSDT", m5, orb_minutes=15)
    assert len(events) == 2
    assert {e["outcome"] for e in events} == {"only_h", "only_l"}


def test_tool_caps_days():
    assert tool._MAX_DAYS == 180
    assert tool._DEFAULT_DAYS == 120


def test_confidence_buckets():
    assert engine.confidence_label(4) == "insufficient"
    assert engine.confidence_label(10) == "low"
    assert engine.confidence_label(30) == "normal"
    assert engine.confidence_label(100) == "high"
