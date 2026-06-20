"""Offline deterministic tests for the pure ETH-profile engine + tool helpers.

We hand-build 15m + 1H candles inside the synthetic_ny RTH window
(13:30-20:00 UTC) so we control each day's profile (POC/VAH/VAL) and whether the
next day's 1H candles touch the prior day's levels. No network.
"""

from datetime import datetime, timezone

from engines import eth_profile_stats as engine


def _c15(day, hh, mm, o, h, l, cl):
    ts = datetime(2025, 1, day, hh, mm, tzinfo=timezone.utc)
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": cl}


def _rth_15m_day(day, low, high):
    """A full RTH window of 15m candles spanning [low, high].

    Many candles cluster at the centre so the POC lands mid-range and a value
    area can be built (compute_profiles needs >=2 candles and nonzero range).
    """
    mid = (low + high) / 2
    candles = []
    # 13:30 → 19:45 inclusive = 26 fifteen-minute slots.
    hh, mm = 13, 30
    for i in range(26):
        if i == 0:
            candles.append(_c15(day, hh, mm, low, high, low, mid))  # full-range bar
        else:
            # tight bars around mid to concentrate TPOs at the centre
            candles.append(_c15(day, hh, mm, mid, mid + 5, mid - 5, mid))
        mm += 15
        if mm >= 60:
            mm = 0
            hh += 1
    return candles


def _profile_levels(day, low, high):
    poc, vah, val, total = engine.compute_today_profile(_rth_15m_day(day, low, high))
    return poc, vah, val, total


def test_compute_today_profile_builds_one_profile():
    poc, vah, val, total = _profile_levels(6, 90.0, 110.0)
    assert poc is not None and vah is not None and val is not None
    assert val <= poc <= vah
    assert total > 0


def test_touch_detection_prev_levels_hit():
    # Day 1 profile around 90-110 (POC ~100). Day 2's 1H candles sweep through
    # 100 so they touch prev POC/VAH/VAL.
    poc, vah, val, _ = _profile_levels(6, 90.0, 110.0)

    rth_15m_day2 = _rth_15m_day(7, 80.0, 120.0)
    # One 1H candle inside RTH that straddles the whole prev value area.
    rth_1h_day2 = [
        {"timestamp": datetime(2025, 1, 7, 14, 0, tzinfo=timezone.utc),
         "open": 100.0, "high": 130.0, "low": 70.0, "close": 100.0},
    ]
    _, windows = engine.convention_for("BTCUSDT")
    rth_label = f"{windows['rth'][0]}-{windows['rth'][1]}"
    data = engine.compute_day(
        "BTCUSDT", datetime(2025, 1, 7).date(), rth_15m_day2, rth_1h_day2,
        prev_poc=poc, prev_vah=vah, prev_val=val,
        convention_name="synthetic_ny", rth_window_label=rth_label,
    )
    assert data["touched_prev_poc"] is True
    assert data["touched_prev_vah"] is True
    assert data["touched_prev_val"] is True
    assert data["prev_poc_touch_time"] == "14:00"


def test_touch_detection_no_touch_when_far_away():
    poc, vah, val, _ = _profile_levels(6, 90.0, 110.0)
    rth_15m_day2 = _rth_15m_day(7, 200.0, 220.0)
    rth_1h_day2 = [
        {"timestamp": datetime(2025, 1, 7, 14, 0, tzinfo=timezone.utc),
         "open": 210.0, "high": 215.0, "low": 205.0, "close": 210.0},
    ]
    _, windows = engine.convention_for("BTCUSDT")
    rth_label = f"{windows['rth'][0]}-{windows['rth'][1]}"
    data = engine.compute_day(
        "BTCUSDT", datetime(2025, 1, 7).date(), rth_15m_day2, rth_1h_day2,
        prev_poc=poc, prev_vah=vah, prev_val=val,
        convention_name="synthetic_ny", rth_window_label=rth_label,
    )
    assert data["touched_prev_poc"] is False
    assert data["touched_prev_vah"] is False
    assert data["touched_prev_val"] is False


def test_first_day_has_null_prev_and_no_touch():
    rth_15m = _rth_15m_day(6, 90.0, 110.0)
    _, windows = engine.convention_for("BTCUSDT")
    rth_label = f"{windows['rth'][0]}-{windows['rth'][1]}"
    data = engine.compute_day(
        "BTCUSDT", datetime(2025, 1, 6).date(), rth_15m, [],
        prev_poc=None, prev_vah=None, prev_val=None,
        convention_name="synthetic_ny", rth_window_label=rth_label,
    )
    assert data["prev_poc"] is None
    assert data["touched_prev_poc"] is False


def test_build_events_chains_prev_levels():
    m15_by_day = {
        datetime(2025, 1, 6).date(): _rth_15m_day(6, 90.0, 110.0),
        datetime(2025, 1, 7).date(): _rth_15m_day(7, 80.0, 120.0),
    }
    # Day 2 1H sweeps the prev value area; day 1 has no 1H (first day anyway).
    h1_by_day = {
        datetime(2025, 1, 6).date(): [
            {"timestamp": datetime(2025, 1, 6, 14, 0, tzinfo=timezone.utc),
             "open": 100.0, "high": 110.0, "low": 90.0, "close": 100.0}],
        datetime(2025, 1, 7).date(): [
            {"timestamp": datetime(2025, 1, 7, 14, 0, tzinfo=timezone.utc),
             "open": 100.0, "high": 130.0, "low": 70.0, "close": 100.0}],
    }
    events = engine.build_events("BTCUSDT", m15_by_day, h1_by_day)
    assert len(events) == 2
    # Day 1: prev_* null (no touch). Day 2: prev_* seeded from day 1, touched.
    assert events[0]["prev_poc"] is None
    assert events[1]["prev_poc"] is not None
    assert events[1]["touched_prev_poc"] is True


def test_agg_touch_percentages_and_confidence():
    # 10 events: 7 touched POC, 4 touched VAH, 2 touched VAL.
    events = []
    for i in range(10):
        events.append({
            "touched_prev_poc": i < 7,
            "touched_prev_vah": i < 4,
            "touched_prev_val": i < 2,
            "prev_poc_touch_time": "15:00" if i < 7 else None,
            "prev_vah_touch_time": "16:00" if i < 4 else None,
            "prev_val_touch_time": "17:00" if i < 2 else None,
            "tpo_sample_label": "low",
        })
    t = engine.agg_touch(events)
    assert t["n"] == 10
    assert t["prev_poc_pct"] == 70.0
    assert t["prev_vah_pct"] == 40.0
    assert t["prev_val_pct"] == 20.0
    assert t["avg_prev_poc_touch_time"] == "15:00"
    assert t["tpo_quality_normal_pct"] == 100.0
    assert t["confidence"] == "low"  # n=10


def test_agg_extension_rth_range():
    events = [{"rth_range": 20.0}, {"rth_range": 40.0}, {"rth_range": 30.0}]
    e = engine.agg_extension(events)
    assert e["rth_extension"]["median"] == 30.0
    assert e["n"] == 3
    assert e["rth_extension"]["confidence"] == "insufficient"


def test_confidence_buckets():
    assert engine.confidence_label(9) == "insufficient"
    assert engine.confidence_label(29) == "low"
    assert engine.confidence_label(99) == "normal"
    assert engine.confidence_label(100) == "high"
