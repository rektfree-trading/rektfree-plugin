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
    # Spot tools reject forex symbols with the shared guard message.
    for name in ("analyze_smc", "get_levels", "get_derivatives", "get_volatility"):
        payload = _call(name, {"symbol": "EUR_USD"})
        assert "error" in payload and "forex" in payload["error"].lower()
