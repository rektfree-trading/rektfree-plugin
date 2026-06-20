"""
``get_market_profile`` — Market Profile / TPO analysis tool (crypto, keyless).

Fetches Binance candles and runs the vendored Market Profile engine, returning
the backend's /market/profile payload shape (``{symbol, timeframe, last_price,
sessions}``). Each session carries POC, VAH/VAL, and the per-price TPO buckets
so the host model can read profile shape, value area, and POC migration.
"""

from __future__ import annotations

from data import binance
from data import market
from engines import market_profile as profile_engine

# The plugin accepts lowercase timeframe tokens (matching binance.fetch_candles),
# but the engine's `_get_session_boundaries` switches on the backend's
# CASE-SENSITIVE Timeframe.value strings (capital H, bare D/W). Fetch candles
# with the lowercase token, then pass the mapped string into compute_profiles.
_ENGINE_TIMEFRAME: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1H",
    "4h": "4H",
    "1d": "D",
    "1w": "W",
}


def register(mcp) -> None:
    @mcp.tool()
    async def get_market_profile(
        symbol: str = "BTCUSDT",
        timeframe: str = "1h",
        limit: int = 500,
        max_sessions: int = 10,
    ) -> dict:
        """Compute Market Profile / TPO analysis for a crypto symbol.

        Fetches candles from Binance (public, no API key) and builds a
        Time-Price-Opportunity profile per session: the candle range is divided
        into auto-sized price buckets, TPOs are counted per bucket, and the
        engine derives the POC (Point of Control — most-traded price), the Value
        Area (VAH/VAL — the ~68.26% band of activity around POC), and per-bucket
        letters/zones. Sessions are grouped by timeframe (e.g. 1h → daily
        sessions, 4h → weekly, 1d/1w → monthly). Returns structured JSON for the
        model to interpret — fair value, balance vs imbalance, profile shape, and
        where price is likely drawn next.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex/metals (e.g. ``EUR_USD``,
                ``XAU_USD``) ARE supported when ``RF_OANDA_TOKEN`` is set;
                crypto needs no key.
            timeframe: Candle timeframe — one of 1m/5m/15m/1h/4h/1d/1w (aliases
                accepted). Determines how candles are grouped into sessions.
            limit: Number of candles to fetch (capped at 1000 by Binance).
            max_sessions: Maximum number of recent sessions to return (newest
                last).

        Returns:
            A dict with ``symbol``, ``timeframe``, ``last_price`` (last close),
            and ``sessions`` — a list of profile sessions ordered oldest→newest.
            Each session is ``{label, start_time, end_time, tick_size, poc, vah,
            val, poc_count, total_tpos, buckets}`` where ``buckets`` is a list of
            ``{price, count, letters, zone}`` (count==0 buckets are dropped) and
            ``zone`` is ``"poc"``, ``"value"``, or ``"outside"``. ``end_time`` is
            ``0`` for the still-open current session. On failure, a dict with an
            ``error`` key.
        """
        try:
            candles = await market.fetch_candles(symbol, timeframe, limit)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not candles:
            return {"error": f"No candle data returned for {symbol}."}

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        times = [c["time"] for c in candles]

        # Map the user's lowercase timeframe to the backend-style string the
        # engine's session-boundary logic expects (e.g. 1h→1H, 1d→D). Fall back
        # to the normalized lowercase token for any alias not in the map.
        normalized = binance.normalize_timeframe(timeframe)
        engine_tf = _ENGINE_TIMEFRAME.get(normalized, normalized)

        profiles = profile_engine.compute_profiles(
            highs,
            lows,
            closes,
            times,
            timeframe=engine_tf,
            max_sessions=max_sessions,
        )

        return {
            "symbol": symbol.upper(),
            "timeframe": normalized,
            "last_price": closes[-1],
            "sessions": [
                {
                    "label": p.session_label,
                    "start_time": p.start_time,
                    "end_time": p.end_time,
                    "tick_size": p.tick_size,
                    "poc": p.poc,
                    "vah": p.vah,
                    "val": p.val,
                    "poc_count": p.poc_count,
                    "total_tpos": p.total_tpos,
                    "buckets": [
                        {
                            "price": b.price_level,
                            "count": b.count,
                            "letters": b.letters,
                            "zone": b.zone,
                        }
                        for b in p.buckets
                        if b.count > 0  # skip empty buckets
                    ],
                }
                for p in profiles
            ],
        }
