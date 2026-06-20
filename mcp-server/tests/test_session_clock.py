"""Offline tests for the pure session/killzone clock."""

from datetime import datetime, timezone

from tools import session_clock


def _at(hour, minute=0):
    return session_clock._build_clock(
        datetime(2026, 6, 17, hour, minute, tzinfo=timezone.utc)  # a Wednesday
    )


def test_session_classification_boundaries():
    assert _at(2)["session"] == "asia"          # 00:00–08:00
    assert _at(9, 30)["session"] == "london"     # 08:00–13:00
    assert _at(13, 30)["session"] == "new_york"  # 13:00–21:00
    assert _at(22)["session"] == "post_ny"       # 21:00–24:00


def test_clock_fields_present_and_sane():
    clock = _at(13, 30)
    assert clock["next_session"]
    # minutes-style fields are never negative
    for key, val in clock.items():
        if "minutes" in key and isinstance(val, (int, float)):
            assert val >= 0


def test_internal_self_test_passes():
    # The module ships its own boundary asserts; calling it must not raise.
    session_clock._self_test()
