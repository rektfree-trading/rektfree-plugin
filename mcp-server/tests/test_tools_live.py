"""
Live contract tests — every MCP tool returns a well-formed (error-free) payload
against the real Binance API. Skipped unless RF_LIVE_TESTS=1 (see conftest).

These are the end-to-end safety net: they prove the whole pipe (fetch → engine →
serialize → MCP) works for each registered tool.
"""

import asyncio
import json

import pytest

import server  # registers all tools on server.mcp via auto-discovery


def _call(name, args):
    res = asyncio.run(server.mcp.call_tool(name, args))
    return json.loads(res[0].text)


EXPECTED_TOOLS = {
    "analyze_smc", "get_levels", "get_market_profile", "get_orderflow",
    "scan_confluence", "scan_market", "compute_session_stats",
    "compute_smc_stats", "get_derivatives", "get_volatility",
    "get_correlations", "get_session_clock",
    # second wave
    "get_daily_bias", "get_ict_concepts", "compute_pdh_pdl_stats",
    "compute_ib_stats", "compute_day_type_stats",
    "compute_session_extension_stats", "get_session_forecast", "get_price_action",
    # third wave
    "run_backtest", "discover_edges",
    # fourth wave
    "calc_position_size", "get_candles", "backtest_rr",
    # fifth wave — intraday stats
    "compute_peak_points_stats", "get_session_card",
    "compute_orb_stats", "compute_eth_profile_stats",
}

CASES = [
    ("analyze_smc", {"symbol": "BTCUSDT", "timeframe": "1h", "limit": 120}, "structures"),
    ("get_levels", {"symbol": "BTCUSDT"}, "levels"),
    ("get_market_profile", {"symbol": "BTCUSDT", "timeframe": "1h", "limit": 200}, "sessions"),
    ("get_orderflow", {"symbol": "BTCUSDT", "timeframe": "5m", "candles": 3}, "candles"),
    ("scan_confluence", {"symbol": "BTCUSDT"}, "score"),
    ("scan_market", {"symbols": "BTCUSDT,ETHUSDT"}, "ranked"),
    ("compute_session_stats", {"symbol": "BTCUSDT", "days": 20}, "sweeps"),
    ("compute_smc_stats", {"symbol": "BTCUSDT"}, "ob_test"),
    ("get_derivatives", {"symbol": "BTCUSDT"}, "funding"),
    ("get_volatility", {"symbol": "BTCUSDT", "timeframe": "1h"}, "atr"),
    ("get_correlations", {"symbols": "BTCUSDT,ETHUSDT,SOLUSDT"}, "vs_base"),
    ("get_session_clock", {}, "session"),
    ("get_daily_bias", {"symbol": "BTCUSDT"}, "current_bias"),
    ("get_ict_concepts", {"symbol": "BTCUSDT"}, "current_dol"),
    ("compute_pdh_pdl_stats", {"symbol": "BTCUSDT", "days": 30}, "pdh"),
    ("compute_ib_stats", {"symbol": "BTCUSDT", "days": 30}, "breakouts"),
    ("compute_day_type_stats", {"symbol": "BTCUSDT", "days": 30}, "day_types"),
    ("compute_session_extension_stats", {"symbol": "BTCUSDT", "days": 30}, "extensions"),
    ("get_session_forecast", {"symbol": "BTCUSDT", "days": 60}, "expected_range"),
    ("get_price_action", {"symbol": "BTCUSDT", "timeframe": "1h", "limit": 120}, "patterns"),
    ("run_backtest", {"symbol": "BTCUSDT", "event_type": "london_sweep", "days": 90}, "outcomes"),
    ("discover_edges", {"symbol": "BTCUSDT", "days": 120, "min_samples": 8}, "edges"),
    ("calc_position_size", {"account_equity": 10000, "risk_pct": 1, "entry": 100, "stop": 95}, "position_size_units"),
    ("get_candles", {"symbol": "BTCUSDT", "timeframe": "1h", "limit": 50}, "candles"),
    ("backtest_rr", {"symbol": "BTCUSDT", "event_type": "london_sweep", "days": 90}, "stats"),
    ("compute_peak_points_stats", {"symbol": "BTCUSDT", "days": 60}, "matrix"),
    ("get_session_card", {"symbol": "BTCUSDT", "session": "london", "days": 60}, "hod_lod"),
    ("compute_orb_stats", {"symbol": "BTCUSDT", "days": 30}, "breakouts"),
    ("compute_eth_profile_stats", {"symbol": "BTCUSDT", "days": 30}, "touch"),
]


def test_all_tools_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == EXPECTED_TOOLS


@pytest.mark.live
@pytest.mark.parametrize("name,args,key", CASES, ids=[c[0] for c in CASES])
def test_tool_returns_clean_payload(name, args, key):
    payload = _call(name, args)
    assert "error" not in payload, f"{name} returned error: {payload.get('error')}"
    assert key in payload, f"{name} missing expected key '{key}'"


@pytest.mark.live
def test_forex_guard_consistent():
    # Only the crypto-only tools reject forex symbols (OANDA has no tick or
    # futures data). Everything else is forex-capable when RF_OANDA_TOKEN is set.
    for name in ("get_orderflow", "get_derivatives"):
        payload = _call(name, {"symbol": "EUR_USD"})
        assert "error" in payload and "forex" in payload["error"].lower()
