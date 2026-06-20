"""Offline tests for the pure analysis engines (no network)."""

import math

from engines import correlations, levels, market_profile, smart_money, volatility


# --- helpers --------------------------------------------------------------

def _gen_candles(n=200, start=30_000.0, step=10.0, base_ts=1_700_000_000, interval=3600):
    """Deterministic gently-trending OHLC series for engine smoke tests."""
    candles = []
    price = start
    for i in range(n):
        o = price
        c = price + step
        h = max(o, c) + 5
        l = min(o, c) - 5
        candles.append(
            {"time": base_ts + i * interval, "open": o, "high": h, "low": l, "close": c, "volume": 1.0}
        )
        price = c
    return candles


def _split(candles):
    return (
        [c["open"] for c in candles],
        [c["high"] for c in candles],
        [c["low"] for c in candles],
        [c["close"] for c in candles],
        [c["time"] for c in candles],
    )


# --- volatility -----------------------------------------------------------

def test_true_ranges_hand_values():
    highs = [10, 12, 11, 13]
    lows = [8, 9, 9, 10]
    closes = [9, 11, 10, 12]
    assert volatility.true_ranges(highs, lows, closes) == [3, 2, 3]


def test_atr_simple_hand_values():
    highs = [10, 12, 11, 13]
    lows = [8, 9, 9, 10]
    closes = [9, 11, 10, 12]
    assert volatility.atr_simple(highs, lows, closes, 3) == (3 + 2 + 3) / 3
    assert volatility.atr_simple(highs, lows, closes, 2) == (2 + 3) / 2


def test_atr_insufficient_data_returns_zero():
    assert volatility.atr_simple([1, 2], [0, 1], [1, 2], 14) == 0.0


def test_realized_vol_factor_and_sign():
    closes = [100 * (1.01 ** i) for i in range(40)]  # steady up
    ann, factor = volatility.realized_vol(closes, window=30, interval="1h")
    assert factor == math.sqrt(365 * 24)
    assert ann >= 0.0


def test_bbw_squeeze_flags_low_width():
    widths = [1.0] * 99 + [0.1]  # last is tightest
    current, pct, squeeze = volatility.bbw_squeeze(widths, lookback=100)
    assert current == 0.1 and squeeze is True and pct <= 0.25


# --- correlations ---------------------------------------------------------

def test_pearson_perfect_and_anti():
    xs = [1, 2, 3, 4, 5]
    ys = [2, 4, 6, 8, 10]
    assert round(correlations.pearson(xs, ys), 6) == 1.0
    assert round(correlations.pearson(xs, [10, 8, 6, 4, 2]), 6) == -1.0


def test_pearson_constant_series_is_zero():
    assert correlations.pearson([1, 1, 1, 1], [1, 2, 3, 4]) == 0.0


def test_align_closes_intersects_timestamps():
    series = {
        "A": [{"time": 1, "close": 10}, {"time": 2, "close": 11}, {"time": 3, "close": 12}],
        "B": [{"time": 2, "close": 20}, {"time": 3, "close": 21}, {"time": 4, "close": 22}],
    }
    times, aligned = correlations.align_closes(series)
    assert times == [2, 3]
    assert aligned["A"] == [11, 12] and aligned["B"] == [20, 21]


def test_correlation_matrix_symmetric_with_unit_diagonal():
    rets = {"A": [0.01, -0.02, 0.03, 0.0], "B": [0.02, -0.01, 0.02, 0.01]}
    m = correlations.correlation_matrix(rets)
    assert m["A"]["A"] == 1.0 and m["B"]["B"] == 1.0
    assert m["A"]["B"] == m["B"]["A"]


def test_labels():
    assert correlations.strength(0.9) == "strong"
    assert correlations.strength(0.5) == "moderate"
    assert correlations.strength(0.1) == "weak"
    assert correlations.direction(0.5) == "same"
    assert correlations.direction(-0.5) == "opposite"
    assert correlations.shift_label(0.9, 0.5) == "tightening"
    assert correlations.shift_label(0.4, 0.9) == "decoupling"
    assert correlations.shift_label(0.8, 0.8) == "stable"


# --- SMC / levels / profile (smoke: runs clean + basic invariants) --------

def test_smart_money_analyze_runs():
    o, h, l, c, t = _split(_gen_candles(200))
    res = smart_money.analyze(o, h, l, c, t, swing_length=20, internal_length=5, eql_threshold=0.15, eql_length=5)
    assert hasattr(res, "trend_bias")
    assert isinstance(res.order_blocks, list)
    assert isinstance(res.fair_value_gaps, list)


def test_compute_levels_populates_daily():
    o, h, l, c, t = _split(_gen_candles(300, interval=900))  # 15m candles
    res = levels.compute_levels(h, l, o, c, t)
    assert res.daily.high > 0 and res.daily.high >= res.daily.low


def test_market_profile_value_area_invariant():
    o, h, l, c, t = _split(_gen_candles(240, interval=3600))
    profiles = market_profile.compute_profiles(h, l, c, t, timeframe="1H")
    assert profiles, "expected at least one TPO profile"
    last = profiles[-1]
    assert last.val <= last.poc <= last.vah
