"""
Unified market-data router — dispatch by symbol convention.

Crypto symbols have no separator (``BTCUSDT``) → Binance (keyless).
Forex/metals symbols are underscore-separated (``EUR_USD``, ``XAU_USD``) → OANDA
(bring-your-own ``RF_OANDA_TOKEN``).

Tools call these instead of ``binance.*`` directly so a single rule decides the
venue. Both backends return the same candle dict shape and raise
``binance.BinanceError`` on failure, so existing ``except binance.BinanceError``
handlers catch both.
"""

from __future__ import annotations

from data import binance, oanda


def is_forex(symbol: str) -> bool:
    """True for underscore-separated forex/metals symbols (the OANDA convention)."""
    return "_" in symbol


async def fetch_candles(symbol: str, timeframe: str = "1h", limit: int = 500) -> list[dict]:
    """Fetch candles, routing crypto→Binance and forex→OANDA."""
    if is_forex(symbol):
        return await oanda.fetch_candles(symbol, timeframe, limit)
    return await binance.fetch_candles(symbol, timeframe, limit)


async def fetch_candles_paged(
    symbol: str, timeframe: str = "1h", total: int = 2000, max_pages: int = 8
) -> list[dict]:
    """Fetch deep history, routing crypto→Binance and forex→OANDA."""
    if is_forex(symbol):
        return await oanda.fetch_candles_paged(symbol, timeframe, total, max_pages)
    return await binance.fetch_candles_paged(symbol, timeframe, total, max_pages)
