"""
Offline, deterministic tests for the R-multiple backtest math + get_candles.

No network: we hand-build synthetic candle lists and assert the pure simulator
(``engines.strategy_sim``) and the tool's pure helpers
(``tools.backtest_rr.simulate_events`` / ``_event_direction``) produce exactly the
expected R-multiples and aggregate stats. ``get_candles`` is exercised against a
stubbed fetcher so its limit-capping and ISO fields are verified without Binance.
"""

import asyncio

import pytest

from engines import strategy_sim
from tools import backtest_rr, get_candles


# --- candle helpers -------------------------------------------------------

def _c(time, o, h, l, cl, v=1.0):
    return {"time": float(time), "open": o, "high": h, "low": l, "close": cl, "volume": v}


def _flat(n, price, time0=0, interval=3600):
    """n flat candles at a fixed price (zero range), used as filler / ATR base."""
    return [_c(time0 + i * interval, price, price, price, price) for i in range(n)]


# --- ATR ------------------------------------------------------------------

def test_true_ranges_first_bar_is_high_low():
    highs = [10, 12, 11]
    lows = [8, 9, 9]
    closes = [9, 11, 10]
    trs = strategy_sim.true_ranges(highs, lows, closes)
    # TR0 = 10-8 = 2; TR1 = max(12-9, |12-9|, |9-9|) = 3; TR2 = max(11-9,|11-11|,|9-11|)=2
    assert trs == [2, 3, 2]


def test_atr_at_simple_mean_window():
    candles = [
        _c(0, 100, 102, 98, 100),   # TR 4
        _c(1, 100, 103, 99, 100),   # TR max(4, |103-100|, |99-100|)=4
        _c(2, 100, 101, 95, 100),   # TR max(6, |101-100|, |95-100|)=6
    ]
    # ATR over last 2 candles ending at idx 2: TRs computed on [idx1, idx2] window.
    atr = strategy_sim.atr_at(candles, end_idx=2, period=2)
    # window = candles[1:3]; trs = [103-99=4, max(6,|101-100|,|95-100|)=6] -> mean 5
    assert atr == 5.0


# --- single-trade first-touch --------------------------------------------

def test_long_hits_target():
    # entry at idx0 close=100, stop_distance=10 -> stop=90, target(+2R)=120.
    candles = [
        _c(0, 100, 100, 100, 100),
        _c(1, 100, 115, 99, 110),   # no touch (target 120 not hit, stop 90 not hit)
        _c(2, 110, 125, 108, 120),  # high 125 >= 120 target -> +2R
    ]
    t = strategy_sim.simulate_trade(candles, 0, "long", 100, 10, 2.0, 48)
    assert t["r"] == 2.0
    assert t["exit_reason"] == "target"
    assert t["bars_held"] == 2


def test_long_stopped_out():
    candles = [
        _c(0, 100, 100, 100, 100),
        _c(1, 100, 105, 88, 95),  # low 88 <= stop 90 -> -1R
    ]
    t = strategy_sim.simulate_trade(candles, 0, "long", 100, 10, 2.0, 48)
    assert t["r"] == -1.0
    assert t["exit_reason"] == "stop"


def test_both_hit_same_bar_is_stop_first():
    # A bar whose range spans both stop(90) and target(120) -> -1R, stop priority.
    candles = [
        _c(0, 100, 100, 100, 100),
        _c(1, 100, 130, 80, 100),
    ]
    t = strategy_sim.simulate_trade(candles, 0, "long", 100, 10, 2.0, 48)
    assert t["r"] == -1.0
    assert t["exit_reason"] == "stop_ambiguous"


def test_time_exit_fractional_r():
    # Neither stop nor target hit within hold window -> exit at last close.
    # entry 100, stop_distance 10. Last close 105 -> move +5 -> +0.5R.
    candles = [
        _c(0, 100, 100, 100, 100),
        _c(1, 100, 108, 95, 103),
        _c(2, 103, 108, 96, 105),
    ]
    t = strategy_sim.simulate_trade(candles, 0, "long", 100, 10, 2.0, max_hold_bars=2)
    assert t["exit_reason"] == "time"
    assert t["r"] == pytest.approx(0.5)


def test_short_hits_target():
    # short entry 100, stop_distance 10 -> stop=110, target(-2R)=80.
    candles = [
        _c(0, 100, 100, 100, 100),
        _c(1, 100, 105, 78, 85),  # low 78 <= target 80 -> +2R
    ]
    t = strategy_sim.simulate_trade(candles, 0, "short", 100, 10, 2.0, 48)
    assert t["r"] == 2.0
    assert t["exit_reason"] == "target"


def test_no_forward_bars_returns_none():
    candles = [_c(0, 100, 100, 100, 100)]
    assert strategy_sim.simulate_trade(candles, 0, "long", 100, 10, 2.0, 48) is None


def test_zero_stop_distance_returns_none():
    candles = [_c(0, 100, 100, 100, 100), _c(1, 100, 110, 90, 100)]
    assert strategy_sim.simulate_trade(candles, 0, "long", 100, 0, 2.0, 48) is None


# --- aggregate stats ------------------------------------------------------

def test_aggregate_stats_hand_set():
    # Hand-computed set: two +2R wins, two -1R losses.
    rs = [2.0, -1.0, 2.0, -1.0]
    s = strategy_sim.aggregate_stats(rs)
    assert s["trades"] == 4
    assert s["wins"] == 2
    assert s["losses"] == 2
    assert s["win_rate"] == 50.0
    assert s["avg_win_R"] == 2.0
    assert s["avg_loss_R"] == -1.0
    assert s["expectancy_R"] == pytest.approx(0.5)  # (2-1+2-1)/4
    # gross win = 2+2 = 4; gross loss = 1+1 = 2 -> PF = 2.0
    assert s["profit_factor"] == pytest.approx(2.0)
    assert s["total_R"] == pytest.approx(2.0)


def test_profit_factor_and_drawdown():
    # equity: +2 -> 2, -1 -> 1, -1 -> 0, +2 -> 2.
    rs = [2.0, -1.0, -1.0, 2.0]
    s = strategy_sim.aggregate_stats(rs)
    # gross win = 4, gross loss = 2 -> PF = 2.0
    assert s["profit_factor"] == pytest.approx(2.0)
    # curve = [2, 1, 0, 2]; peak 2, trough 0 -> max DD = 2.
    assert s["max_drawdown_R"] == pytest.approx(2.0)
    assert s["equity_curve"] == [2.0, 1.0, 0.0, 2.0]


def test_profit_factor_none_without_losses():
    s = strategy_sim.aggregate_stats([2.0, 2.0])
    assert s["profit_factor"] is None
    assert s["max_drawdown_R"] == 0.0


def test_drawdown_from_zero_baseline():
    # Immediately-negative curve: DD measured from the 0 start.
    s = strategy_sim.aggregate_stats([-1.0, -1.0])
    assert s["max_drawdown_R"] == pytest.approx(2.0)


def test_empty_stats():
    s = strategy_sim.aggregate_stats([])
    assert s["trades"] == 0
    assert s["profit_factor"] is None
    assert s["equity_curve"] == []


def test_downsample_caps_and_keeps_last():
    pts = [float(i) for i in range(1000)]
    out = strategy_sim.downsample(pts, cap=100)
    assert len(out) == 100
    assert out[0] == 0.0
    assert out[-1] == 999.0  # final equity preserved
    assert strategy_sim.downsample([1.0, 2.0], cap=100) == [1.0, 2.0]


def test_confidence_buckets():
    assert strategy_sim.confidence(60) == "HIGH"
    assert strategy_sim.confidence(20) == "MEDIUM"
    assert strategy_sim.confidence(5) == "LOW"
    assert strategy_sim.confidence(4) == "INSUFFICIENT"


# --- event direction mapping ----------------------------------------------

def test_event_direction_bullish_bearish():
    assert backtest_rr._event_direction({"event_type": "session_range", "direction": "bullish"}) == "long"
    assert backtest_rr._event_direction({"event_type": "ny_continuation", "direction": "bearish"}) == "short"


def test_event_direction_sweep_reversal():
    # swept high + reversal -> short; swept low + reversal -> long.
    assert backtest_rr._event_direction(
        {"event_type": "asia_sweep", "sweep_side": "high", "reversal": True}
    ) == "short"
    assert backtest_rr._event_direction(
        {"event_type": "london_sweep", "sweep_side": "low", "reversal": True}
    ) == "long"
    # No reversal (continuation) -> trade with the sweep side.
    assert backtest_rr._event_direction(
        {"event_type": "asia_sweep", "sweep_side": "high", "reversal": False}
    ) == "long"
    # 'both' is ambiguous.
    assert backtest_rr._event_direction(
        {"event_type": "asia_sweep", "sweep_side": "both", "reversal": True}
    ) is None


# --- entry-index resolution -----------------------------------------------

def test_resolve_entry_index_session_range():
    # Build candles at known UTC hours of a fixed date. London is hours 8..12.
    import datetime as _dt
    base = _dt.datetime(2024, 1, 2, 0, 0, tzinfo=_dt.timezone.utc)
    candles = []
    for hour in range(24):
        ts = (base + _dt.timedelta(hours=hour)).timestamp()
        candles.append(_c(ts, 100, 100, 100, 100 + hour))
    ev = {"event_type": "session_range", "session": "london", "date": "2024-01-02"}
    idx = strategy_sim.resolve_entry_index(candles, ev)
    # London window 8..13 -> last in-window candle is hour 12 -> index 12.
    assert idx == 12
    assert strategy_sim._candle_dt(candles[idx]).hour == 12


def test_resolve_entry_index_sweep_uses_confirming_session():
    import datetime as _dt
    base = _dt.datetime(2024, 1, 2, 0, 0, tzinfo=_dt.timezone.utc)
    candles = [_c((base + _dt.timedelta(hours=h)).timestamp(), 100, 100, 100, 100) for h in range(24)]
    # asia_sweep is confirmed during london (8..13) -> last london candle = hour 12 = idx 12.
    ev = {"event_type": "asia_sweep", "date": "2024-01-02", "sweep_side": "high", "reversal": True}
    assert strategy_sim.resolve_entry_index(candles, ev) == 12
    # london_sweep confirmed during new_york (13..21) -> last = hour 20 = idx 20.
    ev2 = {"event_type": "london_sweep", "date": "2024-01-02", "sweep_side": "low", "reversal": True}
    assert strategy_sim.resolve_entry_index(candles, ev2) == 20


def test_resolve_entry_index_missing_date():
    assert strategy_sim.resolve_entry_index([_c(0, 1, 1, 1, 1)], {"event_type": "session_range"}) is None


# --- simulate_events end to end (pure) ------------------------------------

def test_simulate_events_skips_and_counts():
    import datetime as _dt
    base = _dt.datetime(2024, 1, 2, 0, 0, tzinfo=_dt.timezone.utc)
    candles = []
    for h in range(24):
        ts = (base + _dt.timedelta(hours=h)).timestamp()
        # Flat-ish bars; give a small range so ATR > 0.
        candles.append(_c(ts, 100, 101, 99, 100))
    # Add a forward bar that hits a long target.
    ts_next = (base + _dt.timedelta(hours=24)).timestamp()
    candles.append(_c(ts_next, 100, 200, 100, 150))

    # A london session_range bullish event -> entry at hour 12 (idx 12), long.
    good = {"event_type": "session_range", "session": "london",
            "date": "2024-01-02", "direction": "bullish"}
    # An event with no resolvable date -> skipped.
    bad = {"event_type": "session_range", "session": "london", "direction": "bullish"}

    rs, skipped = backtest_rr.simulate_events(
        candles, [good, bad],
        stop_atr_mult=1.0, target_r=2.0, atr_period=14, max_hold_bars=48,
    )
    assert skipped["no_entry_candle"] == 1
    assert len(rs) == 1  # only the good event simulated
    # ATR at idx12 ~ 2 (range 99..101), stop_distance ~2, target +4 -> 104.
    # The forward bar (idx24) high 200 clears it -> +2R.
    assert rs[0] == 2.0


# --- get_candles via stub fetch -------------------------------------------

def test_get_candles_caps_limit_to_1000(monkeypatch):
    captured = {}

    async def fake_paged(symbol, timeframe, total, max_pages):
        captured["total"] = total
        captured["symbol"] = symbol
        return [_c(1_700_000_000 + i * 3600, 100 + i, 101 + i, 99 + i, 100 + i) for i in range(total)]

    monkeypatch.setattr(get_candles.market, "fetch_candles_paged", fake_paged)

    tool = _grab_tool(get_candles, "get_candles")
    # 5000 requested -> capped to 1000, and >500 so it pages.
    res = asyncio.run(tool(symbol="btcusdt", timeframe="1h", limit=5000))
    assert captured["total"] == 1000  # limit hard-capped before paging
    assert captured["symbol"] == "btcusdt"
    assert res["count"] == 1000
    assert res["symbol"] == "BTCUSDT"


def test_get_candles_small_limit_iso_fields(monkeypatch):
    async def fake_fetch(symbol, timeframe, limit):
        return [_c(1_700_000_000 + i * 3600, 100 + i, 101 + i, 99 + i, 100 + i) for i in range(limit)]

    monkeypatch.setattr(get_candles.market, "fetch_candles", fake_fetch)
    tool = _grab_tool(get_candles, "get_candles")
    res = asyncio.run(tool(symbol="BTCUSDT", timeframe="1h", limit=3))
    assert res["count"] == 3
    assert res["symbol"] == "BTCUSDT"
    assert res["timeframe"] == "1h"
    assert res["last_price"] == 102  # close of 3rd candle (100+2)
    assert res["candles"][0]["time_iso"].endswith("+00:00")
    assert "T" in res["candles"][0]["time_iso"]
    # last_price matches last candle close
    assert res["last_price"] == res["candles"][-1]["close"]


def test_get_candles_bad_timeframe():
    tool = _grab_tool(get_candles, "get_candles")
    res = asyncio.run(tool(symbol="BTCUSDT", timeframe="bogus", limit=10))
    assert "error" in res


# --- helper to extract a registered tool callable -------------------------

def _grab_tool(module, name):
    """Register the module on a throwaway MCP and return the raw async fn.

    The tool functions are closures inside ``register``; we capture the inner
    callable by registering against a stub ``mcp`` whose ``tool()`` decorator
    records the function.
    """
    grabbed = {}

    class _StubMCP:
        def tool(self, *a, **k):
            def deco(fn):
                grabbed[fn.__name__] = fn
                return fn
            return deco

    module.register(_StubMCP())
    return grabbed[name]
