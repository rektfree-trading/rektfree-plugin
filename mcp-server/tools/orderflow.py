"""
``get_orderflow`` — footprint / order-flow tool (crypto, keyless).

The hosted backend builds footprints from a live Binance trade stream and serves
them from Postgres. The plugin has neither a stream nor a DB, so this tool
reconstructs footprints **on the fly** from Binance's public, keyless
aggregated-trades endpoint, reusing the backend's exact bucketing logic
(``engines/orderflow.py``, ported from ``tick_aggregator.py``).

It returns the backend's /market/orderflow payload shape
(``{symbol, timeframe, candles:[...]}``) and augments each candle with a
``delta`` plus a top-level running ``cvd`` array to aid interpretation.
"""

from __future__ import annotations

import time

from data import agg_trades
from data.binance import BinanceError
from engines import orderflow as of_engine
from tools._common import crypto_only_error

# Footprint timeframes the backend aggregates — the plugin restricts to these.
_VALID_TIMEFRAMES = set(of_engine.TF_SECONDS)  # {"5m", "15m", "1h"}

# Keep the on-the-fly reconstruction bounded. A default of 12 candles of 5m is
# one hour; the max keeps page counts polite on liquid pairs.
_DEFAULT_CANDLES = 12
_MAX_CANDLES = 50


def register(mcp) -> None:
    @mcp.tool()
    async def get_orderflow(
        symbol: str = "BTCUSDT",
        timeframe: str = "5m",
        candles: int = _DEFAULT_CANDLES,
    ) -> dict:
        """Reconstruct footprint / order-flow data for a crypto symbol.

        Pages Binance's public aggregated-trades endpoint (no API key) over the
        last ``candles`` bars of ``timeframe`` and rebuilds per-price-level
        footprints with the backend's exact bucketing math: aggressive buy vs
        sell volume and counts at each price tick, total delta, cumulative delta
        (CVD), and large ("whale") trade events. Returns structured JSON for the
        model to interpret — absorption, exhaustion, imbalances, and divergence.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex pairs (with ``_``) are not
                supported — OANDA provides no tick data.
            timeframe: Footprint bar size, one of ``5m``, ``15m``, ``1h`` (the
                timeframes the backend aggregates). Other values are rejected.
            candles: Number of recent bars to reconstruct (default 12, max 50).
                Smaller is faster and gentler on Binance rate limits.

        Returns:
            A dict with ``symbol``, ``timeframe``, ``candles`` (chronological),
            and a running ``cvd`` array. Each candle has ``timestamp`` (unix
            seconds, bucket start), ``tick_size``, ``buy_volume``/``sell_volume``,
            ``buy_count``/``sell_count``, ``delta`` (buy_volume − sell_volume),
            ``price_levels`` (dict keyed by stringified price →
            ``{bv, sv, bc, sc}``), and ``large_trades``. If the trade window
            exceeded the page budget, a ``truncated: true`` flag is included. On
            failure, a dict with an ``error`` key.
        """
        if err := crypto_only_error(symbol):
            return err

        tf = timeframe.strip().lower()
        if tf not in _VALID_TIMEFRAMES:
            valid = ", ".join(sorted(_VALID_TIMEFRAMES))
            return {
                "error": (
                    f"Unsupported timeframe '{timeframe}'. Order-flow footprints "
                    f"are only built for: {valid}."
                )
            }

        try:
            n = int(candles)
        except (TypeError, ValueError):
            n = _DEFAULT_CANDLES
        n = max(1, min(n, _MAX_CANDLES))

        tf_seconds = of_engine.TF_SECONDS[tf]
        sym = symbol.strip().upper()

        # Window = last N closed-ish buckets ending now. Start at the bucket that
        # opens N intervals before the current bucket so we capture N full bars.
        now = time.time()
        cur_bucket = of_engine._bucket_start(now, tf_seconds)
        start_ms = int((cur_bucket - (n - 1) * tf_seconds) * 1000)
        end_ms = int(now * 1000)

        try:
            trades = await agg_trades.fetch_agg_trades(sym, start_ms, end_ms)
        except BinanceError as exc:
            return {"error": str(exc)}

        if not trades:
            return {
                "symbol": sym,
                "timeframe": tf,
                "candles": [],
                "cvd": [],
            }

        built = of_engine.build_footprints(trades, tf_seconds, sym)

        # Detect truncation: if the earliest trade we got is materially later
        # than the requested window start, the page budget capped the fetch.
        truncated = trades[0]["time"] * 1000 > start_ms + tf_seconds * 1000

        out_candles: list[dict] = []
        cvd: list[dict] = []
        running = 0.0
        for c in built:
            delta = round(c["buy_volume"] - c["sell_volume"], 6)
            running = round(running + delta, 6)
            out_candles.append({
                "timestamp": c["timestamp"],
                "tick_size": c["tick_size"],
                "buy_count": c["buy_count"],
                "sell_count": c["sell_count"],
                "buy_volume": c["buy_volume"],
                "sell_volume": c["sell_volume"],
                "delta": delta,
                "price_levels": c["price_levels"],
                "large_trades": c["large_trades"],
            })
            cvd.append({"timestamp": c["timestamp"], "cvd": running})

        payload: dict = {
            "symbol": sym,
            "timeframe": tf,
            "candles": out_candles,
            "cvd": cvd,
        }
        if truncated:
            payload["truncated"] = True
        return payload
