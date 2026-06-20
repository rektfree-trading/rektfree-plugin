"""
``get_ict_concepts`` — ICT session concepts tool (crypto, keyless).

Fetches Binance intraday candles and runs the vendored ICT engine, returning
the backend's /market/ict payload shape: Draw on Liquidity (DOL), Power of 3
(AMD), Judas Swing, and Session Bias.
"""

from __future__ import annotations

from data import binance
from engines import ict_concepts as ict_engine
from tools._common import crypto_only_error


def _serialize(result: ict_engine.ICTResult) -> dict:
    """Convert an ICTResult into the JSON payload Claude reads.

    Mirrors the backend's /market/ict serialization so field names stay
    identical to the hosted product. Bias fields are already strings on the
    engine's dataclasses (``"bullish"``/``"bearish"``/``"neutral"``).
    """
    return {
        "dol": [
            {
                "day_start": e.day_start,
                "bias": e.bias,
                "dol_price": e.dol_price,
                "dol_label": e.dol_label,
                "opposite_price": e.opposite_price,
                "reached": e.reached,
            }
            for e in result.dol_entries
        ],
        "amd": [
            {
                "day_start": p.day_start,
                "phase": p.phase,
                "start_time": p.start_time,
                "end_time": p.end_time,
                "high": p.high,
                "low": p.low,
                "direction": p.direction,
                "range_pct": p.range_pct,
                "quality": p.quality,
            }
            for p in result.amd_phases
        ],
        "judas_swings": [
            {
                "day_start": j.day_start,
                "sweep_time": j.sweep_time,
                "sweep_price": j.sweep_price,
                "direction": j.direction,
                "asia_high": j.asia_high,
                "asia_low": j.asia_low,
                "reversal_confirmed": j.reversal_confirmed,
            }
            for j in result.judas_swings
        ],
        "session_bias": [
            {
                "day_start": s.day_start,
                "session": s.session,
                "bias": s.bias,
                "reason": s.reason,
                "target_high": s.target_high,
                "target_low": s.target_low,
                "hit_target": s.hit_target,
            }
            for s in result.session_bias_entries
        ],
        "current_dol": {
            "bias": result.current_dol.bias,
            "dol_price": result.current_dol.dol_price,
            "dol_label": result.current_dol.dol_label,
            "opposite_price": result.current_dol.opposite_price,
            "reached": result.current_dol.reached,
        } if result.current_dol else None,
        "current_session_bias": {
            "session": result.current_session_bias.session,
            "bias": result.current_session_bias.bias,
            "reason": result.current_session_bias.reason,
        } if result.current_session_bias else None,
    }


def register(mcp) -> None:
    @mcp.tool()
    async def get_ict_concepts(symbol: str = "BTCUSDT", timeframe: str = "1h") -> dict:
        """Run ICT intraday session-concept analysis on a crypto symbol.

        Fetches intraday candles from Binance (public, no API key) and runs the
        full ICT session engine: Draw on Liquidity (DOL — the PDH/PDL target the
        daily bias points to), Power of 3 / AMD (Accumulation in Asia,
        Manipulation in London Open, Distribution in NY) with clean/messy quality
        labels, Judas Swing detection (the fake London-open sweep), and per-
        session Bias (London + NY). Returns structured JSON for the model to
        interpret into a session game-plan.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex pairs (with ``_``) are not
                supported in this slice.
            timeframe: Intraday timeframe for session grouping — 1h (default) or
                15m give the cleanest session boundaries. Lower timeframes give
                finer phase ranges; higher ones span more days.

        Returns:
            A dict with ``symbol``, ``timeframe``, ``candle_count``, ``dol``,
            ``amd``, ``judas_swings``, ``session_bias`` (per-day history lists),
            plus ``current_dol`` and ``current_session_bias`` for the latest day.
            On failure, a dict with an ``error`` key.
        """
        if err := crypto_only_error(symbol):
            return err

        # 1000 intraday candles — enough trading days for session grouping and
        # the daily-bias DOL lookback. Mirrors the backend's /market/ict fetch.
        try:
            candles = await binance.fetch_candles(symbol, timeframe, 1000)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not candles:
            return {"error": f"No candle data returned for {symbol} {timeframe}."}

        opens = [c["open"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        times = [c["time"] for c in candles]

        result = ict_engine.analyze(opens, highs, lows, closes, times)

        payload = _serialize(result)
        payload["symbol"] = symbol.upper()
        payload["timeframe"] = timeframe.lower()
        payload["candle_count"] = len(candles)
        return payload
