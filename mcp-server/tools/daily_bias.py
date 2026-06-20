"""
``get_daily_bias`` — TTrades daily/weekly bias tool (crypto, keyless).

Fetches Binance 1h candles and runs the vendored daily-bias engine, returning
the backend's /market/bias payload shape (``{symbol, timeframe, period,
current_bias, ..., entries, stats}``).
"""

from __future__ import annotations

from data import binance
from engines import daily_bias as bias_engine
from tools._common import bias_str, crypto_only_error


def _format_pct(hit: int, total: int) -> float:
    """Return percentage rounded to 1 decimal — mirrors the backend router."""
    if total == 0:
        return 0.0
    return round(hit / total * 100, 1)


def _serialize(result: bias_engine.BiasResult, period: str) -> dict:
    """Convert a BiasResult into the JSON payload Claude reads.

    Mirrors the backend's /market/bias serialization so field names and the
    success/close-through stats stay identical to the hosted product.
    """
    stats = result.stats
    return {
        "period": period,
        "current_bias": bias_str(result.current_bias),
        "current_reason": result.current_reason,
        "current_prev_high": result.current_prev_high,
        "current_prev_low": result.current_prev_low,
        "entries": [
            {
                "timestamp": e.timestamp,
                "bias": bias_str(e.bias),
                "reason": e.reason,
                "prev_high": e.prev_high,
                "prev_low": e.prev_low,
                "hit_prev_high": e.hit_prev_high,
                "hit_prev_low": e.hit_prev_low,
            }
            for e in result.entries
        ],
        "stats": {
            "bullish": {
                "count": stats.bias_ph_count,
                "success_rate": _format_pct(stats.hit_ph_count, stats.bias_ph_count),
                "close_through_rate": _format_pct(stats.close_ph_count, stats.hit_ph_count),
            },
            "bearish": {
                "count": stats.bias_pl_count,
                "success_rate": _format_pct(stats.hit_pl_count, stats.bias_pl_count),
                "close_through_rate": _format_pct(stats.close_pl_count, stats.hit_pl_count),
            },
        },
    }


def register(mcp) -> None:
    @mcp.tool()
    async def get_daily_bias(symbol: str = "BTCUSDT", period: str = "D") -> dict:
        """Compute the TTrades daily (or weekly) bias for a crypto symbol.

        Fetches 1h candles from Binance (public, no API key) covering ~40 days,
        groups them into daily (or weekly) periods, and applies the TTrades
        bias methodology: where yesterday closed relative to the day-before's
        high/low decides today's directional bias and its draw-on-liquidity
        target (PDH when bullish, PDL when bearish). Returns structured JSON for
        the model to interpret — direction, reasoning, target levels, and the
        historical success / close-through hit rates.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex pairs (with ``_``) are not
                supported in this slice.
            period: ``D`` for daily bias (default) or ``W`` for weekly bias.

        Returns:
            A dict with ``symbol``, ``timeframe``, ``period``, ``current_bias``
            (bullish/bearish/neutral), ``current_reason``, ``current_prev_high``
            / ``current_prev_low`` (the draw-on-liquidity levels), an
            ``entries`` list (per-period bias history) and ``stats`` (bullish /
            bearish counts with success_rate and close_through_rate). On
            failure, a dict with an ``error`` key.
        """
        if err := crypto_only_error(symbol):
            return err

        p = "W" if period.strip().upper() == "W" else "D"

        # 1000 × 1h ≈ 41 days — enough daily periods for bias history and the
        # success-rate stats. Mirrors the backend's /market/bias fetch.
        try:
            candles = await binance.fetch_candles(symbol, "1h", 1000)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not candles:
            return {"error": f"No candle data returned for {symbol}."}

        opens = [c["open"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        times = [c["time"] for c in candles]

        result = bias_engine.compute_daily_bias(opens, highs, lows, closes, times, period=p)

        payload = _serialize(result, p)
        payload["symbol"] = symbol.upper()
        payload["timeframe"] = "1h"
        return payload
