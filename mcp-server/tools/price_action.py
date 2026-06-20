"""
``get_price_action`` — candlestick / price-action pattern detector (crypto, keyless).

Fetches Binance candles and runs the vendored price-action engine, returning the
detected candlestick patterns (single/two/three-candle + inside/outside bars)
with their location and direction, plus a compact recent-candle summary. This is
the plugin's only raw-candle read — every other tool returns higher-level derived
analysis (SMC, levels, profile, …). The model interprets these shapes in context.
"""

from __future__ import annotations

from data import binance
from engines import price_action as pa_engine
from tools._common import crypto_only_error

# Cap how many of the most-recent detections we return. Pattern shapes fire
# constantly on noisy data; the recent ones are the only actionable ones.
_MAX_PATTERNS = 20


def register(mcp) -> None:
    @mcp.tool()
    async def get_price_action(
        symbol: str = "BTCUSDT",
        timeframe: str = "1h",
        limit: int = 100,
    ) -> dict:
        """Detect candlestick / price-action patterns for a crypto symbol.

        Fetches recent candles from Binance (public, no API key) and scans them
        for the standard candlestick patterns: single-candle (doji, hammer /
        hanging man, shooting star / inverted hammer, marubozu, spinning top),
        two-candle (engulfing, harami, piercing line / dark cloud cover), three-
        candle (morning / evening star, three white soldiers / three black
        crows), and structural inside / outside bars. Returns each detection with
        its index, timestamp, direction, and the candle's high/low so the model
        can place it — plus a recent-candle summary (direction, average body
        size, current candle geometry).

        A pattern shape on its own is noise; it matters only **in context** — at
        a key level, after a liquidity sweep, or aligned with structure. The
        model judges that; this tool just reports the shapes.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex pairs (with ``_``) are not
                supported in this slice.
            timeframe: Candle timeframe — one of 1m/5m/15m/1h/4h/1d/1w (aliases
                accepted). Defaults to ``1h``.
            limit: Number of candles to scan (1–1000, capped by Binance).
                Defaults to 100.

        Returns:
            A dict with ``symbol``, ``timeframe``, ``last_price``, a ``summary``
            (last close, recent direction, bull/bear candle counts, average
            body ratio, current candle body% and wick ratios), and ``patterns``
            — the most-recent detections (oldest→newest, most recent last, capped
            to ~20). Each pattern is ``{pattern, key, index, time, direction,
            span, high, low}``. On failure, a dict with an ``error`` key.
        """
        if err := crypto_only_error(symbol):
            return err

        try:
            candles = await binance.fetch_candles(symbol, timeframe, limit)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not candles:
            return {"error": f"No candle data returned for {symbol}."}

        patterns = pa_engine.detect_patterns(candles)
        # Keep only the most-recent detections; they're the only actionable ones.
        recent = patterns[-_MAX_PATTERNS:]

        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "last_price": candles[-1]["close"],
            "summary": pa_engine.summarize(candles),
            "patterns": recent,
        }
