"""
``get_candles`` — raw OHLCV primitive (crypto keyless; forex/metals via OANDA).

The lowest-level data tool: it fetches actual candles and hands them back so the
host model can eyeball real prices, swing points, and recent structure, or run its
own arithmetic on them. No engine, no interpretation — just clean, ISO-stamped
OHLCV. Everything else in the plugin derives numbers FROM candles; this returns
the candles themselves.
"""

from __future__ import annotations

from datetime import datetime, timezone

from data import binance
from data import market

# Hard cap on how many candles we return / fetch in one call.
_MAX_LIMIT = 1000
# Above this we page (fetch_candles caps a single request at ~1000 anyway, but
# paging gives a stable deep window regardless of backend).
_PAGE_THRESHOLD = 500


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def register(mcp) -> None:
    @mcp.tool()
    async def get_candles(
        symbol: str = "BTCUSDT",
        timeframe: str = "1h",
        limit: int = 200,
    ) -> dict:
        """Fetch raw OHLCV candles for a symbol and return them as structured JSON.

        This is the raw-data primitive: use it when you want to look at or compute
        on ACTUAL prices — recent highs/lows, the last close, candle-by-candle
        moves, or to sanity-check what another tool reported. It does no analysis;
        it just returns the bars.

        Crypto comes from Binance with no API key. Forex/metals/indices (e.g.
        ``EUR_USD``, ``XAU_USD``, ``NAS100_USD`` — underscore-separated) are
        supported when ``RF_OANDA_TOKEN`` is set.

        Note: the NEWEST candle is usually still FORMING (partial) — its
        high/low/close will keep changing until the period closes. Treat the last
        bar as provisional.

        Args:
            symbol: Crypto symbol with no separator (``BTCUSDT``, ``ETHUSDT``), or
                an underscore-separated forex/metals/index symbol (``EUR_USD``,
                ``XAU_USD``, ``NAS100_USD``) when ``RF_OANDA_TOKEN`` is set.
            timeframe: 1m/5m/15m/1h/4h/1d/1w (aliases like ``h1`` accepted).
                Default ``1h``.
            limit: Number of most-recent candles to return. Capped at 1000.
                Default 200.

        Returns:
            A dict shaped ``{symbol, timeframe, count, first (ISO-UTC),
            last (ISO-UTC), last_price, candles: [{time, time_iso, open, high,
            low, close, volume}, ...]}`` ordered oldest→newest. On a bad timeframe
            or fetch failure, a dict with an ``error`` key (never raises).
        """
        try:
            interval = binance.normalize_timeframe(timeframe)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        limit = max(1, min(int(limit), _MAX_LIMIT))

        try:
            if limit > _PAGE_THRESHOLD:
                max_pages = max(2, (limit // 1000) + 2)
                raw = await market.fetch_candles_paged(
                    symbol, interval, total=limit, max_pages=max_pages
                )
                # Paging may overshoot the window slightly; trim to the newest N.
                raw = raw[-limit:]
            else:
                raw = await market.fetch_candles(symbol, interval, limit)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not raw:
            return {"error": f"No candle data returned for {symbol}."}

        candles = [
            {
                "time": c["time"],
                "time_iso": _iso(c["time"]),
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c.get("volume", 0.0),
            }
            for c in raw
        ]

        return {
            "symbol": symbol.upper(),
            "timeframe": interval,
            "count": len(candles),
            "first": candles[0]["time_iso"],
            "last": candles[-1]["time_iso"],
            "last_price": candles[-1]["close"],
            "candles": candles,
        }
