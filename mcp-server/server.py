#!/usr/bin/env python3
"""
RektFree MCP server — exposes the pure SMC analysis engine as MCP tools.

This is the "brain-free" data layer of the plugin: it fetches market data and
runs the vendored analyzers, returning structured JSON. Claude itself (the host)
is the AI brain that interprets the numbers — so there are no AI-provider keys
here, by design.

First vertical slice: a single tool, ``analyze_smc`` (Binance/crypto, keyless).
Run as a stdio MCP server:  python3 server.py
"""

from __future__ import annotations

import os
import sys

# Allow `from engines import ...` / `from data import ...` when launched by
# absolute path (the plugin sets cwd elsewhere). Add our own dir to sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from data import binance  # noqa: E402
from engines import smart_money  # noqa: E402

mcp = FastMCP("rektfree")


def _bias_str(bias: int) -> str:
    if bias == smart_money.BULLISH:
        return "bullish"
    if bias == smart_money.BEARISH:
        return "bearish"
    return "neutral"


def _swing_params(timeframe: str) -> tuple[int, int]:
    """Scale swing/eql lookback by timeframe — mirrors the backend router."""
    tf = timeframe.strip().lower()
    if tf in ("1m", "m1", "5m", "m5"):
        return 50, 10
    if tf in ("15m", "m15", "1h", "h1"):
        return 20, 5
    return 10, 3


def _serialize(result: smart_money.SMCResult, times: list[float]) -> dict:
    """Convert an SMCResult into the JSON payload Claude reads.

    Mirrors the backend's /market/smc serialization so the skill guidance and
    field names stay identical to the hosted product.
    """
    n = len(times)
    return {
        "trend_bias": _bias_str(result.trend_bias),
        "swing_high": result.swing_high,
        "swing_high_time": result.swing_high_time,
        "swing_low": result.swing_low,
        "swing_low_time": result.swing_low_time,
        "strong_high": result.strong_high,
        "strong_low": result.strong_low,
        "weak_high": result.weak_high,
        "weak_low": result.weak_low,
        "structures": [
            {
                "type": s.type,
                "bias": _bias_str(s.bias),
                "level": s.level,
                "start_time": s.start_time,
                "end_time": s.end_time,
            }
            for s in result.structures[-30:]
        ],
        "order_blocks": [
            {
                "high": ob.high,
                "low": ob.low,
                "bias": _bias_str(ob.bias),
                "timestamp": ob.timestamp,
            }
            for ob in result.order_blocks
        ],
        "fair_value_gaps": [
            {
                "top": fvg.top,
                "bottom": fvg.bottom,
                "mid": fvg.mid,
                "bias": _bias_str(fvg.bias),
                "timestamp": fvg.timestamp,
            }
            for fvg in result.fair_value_gaps
        ],
        "equal_levels": [
            {
                "level": eq.level,
                "type": eq.type,
                "prev_time": eq.prev_time,
                "curr_time": eq.curr_time,
            }
            for eq in result.equal_levels
            if eq.curr_index > n * 0.7
        ][-10:],
        "swing_labels": [
            {
                "label": sl.label,
                "price": sl.price,
                "timestamp": sl.timestamp,
                "bias": _bias_str(sl.bias),
            }
            for sl in result.swing_labels
        ],
        "liquidity_sweeps": [
            {
                "level": ls.level,
                "sweep_price": ls.sweep_price,
                "timestamp": ls.timestamp,
                "pivot_time": ls.pivot_time,
                "type": ls.type,
                "bias": _bias_str(ls.bias),
            }
            for ls in result.liquidity_sweeps
        ],
        "breaker_blocks": [
            {
                "high": bb.high,
                "low": bb.low,
                "timestamp": bb.timestamp,
                "bias": _bias_str(bb.bias),
            }
            for bb in result.breaker_blocks
        ],
        "sweep_areas": [
            {
                "top": sa.top,
                "bottom": sa.bottom,
                "start_time": sa.start_time,
                "end_time": sa.end_time,
                "direction": sa.direction,
                "bias": _bias_str(sa.bias),
            }
            for sa in result.sweep_areas
        ],
    }


@mcp.tool()
async def analyze_smc(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    limit: int = 500,
) -> dict:
    """Run Smart Money Concepts (SMC) analysis on a crypto symbol.

    Fetches OHLCV candles from Binance (public, no API key needed) and runs the
    full SMC engine: market structure (BOS/CHoCH), order blocks, fair value gaps,
    equal highs/lows, liquidity sweeps, breaker blocks, and premium/discount
    range. Returns structured JSON for the model to interpret.

    Args:
        symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
            ``ETHUSDT``, ``SOLUSDT``. Forex pairs (with ``_``) are not supported
            in this slice.
        timeframe: One of 1m, 5m, 15m, 1h, 4h, 1d, 1w. Default ``1h``.
        limit: Number of candles to analyze (50–1000). Default 500. More candles
            give longer-range structure; fewer give a tighter recent picture.

    Returns:
        A dict with ``symbol``, ``timeframe``, ``candle_count``, ``last_price``,
        and the full SMC breakdown (trend_bias, structures, order_blocks,
        fair_value_gaps, equal_levels, swing_labels, liquidity_sweeps,
        breaker_blocks, sweep_areas, and strong/weak/swing levels). On failure,
        a dict with an ``error`` key.
    """
    if "_" in symbol:
        return {
            "error": (
                f"'{symbol}' looks like a forex pair. This tool only supports "
                "keyless crypto symbols (e.g. BTCUSDT) for now."
            )
        }

    try:
        candles = await binance.fetch_candles(symbol, timeframe, limit)
    except binance.BinanceError as exc:
        return {"error": str(exc)}

    if not candles:
        return {"error": f"No candle data returned for {symbol} {timeframe}."}

    opens = [c["open"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    times = [c["time"] for c in candles]

    swing_len, eql_len = _swing_params(timeframe)
    result = smart_money.analyze(
        opens,
        highs,
        lows,
        closes,
        times,
        swing_length=swing_len,
        internal_length=5,
        eql_threshold=0.15,
        eql_length=eql_len,
    )

    payload = _serialize(result, times)
    payload["symbol"] = symbol.upper()
    payload["timeframe"] = timeframe.lower()
    payload["candle_count"] = len(candles)
    payload["last_price"] = closes[-1]
    return payload


if __name__ == "__main__":
    mcp.run()
