"""Offline test for the confluence scorer (structure of the grade)."""

from datetime import datetime, timezone

from engines import confluence, smart_money

from tests.test_engines_pure import _gen_candles, _split


def test_score_setup_returns_well_formed_grade():
    candles_1h = _gen_candles(300, interval=3600)
    candles_4h = _gen_candles(200, interval=14400)
    o, h, l, c, t = _split(candles_1h)
    smc_1h = smart_money.analyze(o, h, l, c, t, swing_length=20, internal_length=5, eql_threshold=0.15, eql_length=5)
    o4, h4, l4, c4, t4 = _split(candles_4h)
    smc_4h = smart_money.analyze(o4, h4, l4, c4, t4, swing_length=10, internal_length=5, eql_threshold=0.15, eql_length=3)

    grade = confluence.score_setup(
        smc_1h=smc_1h,
        smc_4h=smc_4h,
        candles_1h=candles_1h,
        candles_4h=candles_4h,
        current_price=candles_1h[-1]["close"],
        now_utc=datetime.now(timezone.utc),
    )

    assert set(["score", "min_score", "meets_threshold", "direction", "factors"]).issubset(grade)
    assert isinstance(grade["score"], (int, float))
    assert grade["min_score"] >= 1
    assert isinstance(grade["factors"], list)
    # meets_threshold must be consistent with score vs min_score (counter-trend aside)
    if grade["score"] < grade["min_score"]:
        assert grade["meets_threshold"] is False
