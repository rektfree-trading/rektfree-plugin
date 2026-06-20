"""Offline tests for the price-action candlestick detectors."""

from engines import price_action as pa


def _c(o, h, l, close):
    return {"time": 0, "open": o, "high": h, "low": l, "close": close, "volume": 1.0}


def test_doji_detected():
    # tiny body, real range → doji
    assert pa.is_doji(_c(100, 105, 95, 100.2)) is not None


def test_trend_candle_is_not_doji():
    assert pa.is_doji(_c(100, 110, 100, 110)) is None


def test_hammer_detected_bullish():
    # long lower wick, small body up top
    res = pa.is_hammer(_c(100, 101, 90, 100.5))
    assert res is not None


def test_bullish_engulfing():
    prev = _c(100, 100.5, 98, 98.5)   # small red
    cur = _c(98, 102, 97.5, 101.5)    # big green engulfing prev body
    assert pa.is_engulfing(prev, cur) == "bullish"


def test_bearish_engulfing():
    prev = _c(98, 101, 97.5, 100.5)   # green
    cur = _c(101, 101.5, 97, 97.5)    # red engulfing
    assert pa.is_engulfing(prev, cur) == "bearish"


def test_inside_bar():
    prev = _c(100, 110, 90, 105)
    cur = _c(101, 108, 95, 102)       # range inside prev
    assert pa.is_inside_bar(prev, cur) is not None


def test_inside_bar_not_flagged_when_outside():
    prev = _c(101, 108, 95, 102)
    cur = _c(100, 110, 90, 105)       # engulfs prev range
    assert pa.is_inside_bar(prev, cur) is None


def test_detect_patterns_returns_list():
    candles = [_c(100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(10)]
    out = pa.detect_patterns(candles)
    assert isinstance(out, list)
