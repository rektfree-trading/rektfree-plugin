"""
Pure-Python footprint / order-flow builder.

This is a DB-free, stream-free port of the hosted backend's
``app/services/tick_aggregator.py``. The backend consumes a live Binance trade
WebSocket and writes ``FootprintCandle`` rows to Postgres; here we take a flat
list of historical aggregated trades (from ``data/agg_trades.py``) and rebuild
the exact same per-price-level footprint candles in memory.

The bucketing math is kept **identical** to the backend so the plugin's output
matches the hosted product field-for-field:
- ``_bucket_start`` — floor timestamp to the timeframe interval.
- ``_tick_size_for_price`` — auto price-bucket size.
- ``LARGE_TRADE_THRESHOLDS`` / ``DEFAULT_LARGE_THRESHOLD`` — whale detection.
- ``_LiveCandle.add_trade`` / ``to_dict`` — price-level bucketing, buy/sell
  volume + counts, ``is_buy = not is_buyer_maker``.

Everything tied to async/DB (``async_session``, ``pg_insert``, ``_flush_candle``,
``flush_all``, the global ``handle_trade`` state) is intentionally dropped.
"""

from __future__ import annotations

import math
from collections import defaultdict

# Timeframe durations in seconds — same values as the backend's TF_SECONDS,
# keyed by the footprint timeframe tokens the plugin accepts.
TF_SECONDS: dict[str, int] = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
}

# Large trade threshold in quote currency (e.g. $50k for BTC) — ported verbatim.
LARGE_TRADE_THRESHOLDS: dict[str, int] = {
    "BTCUSDT": 50_000,
    "ETHUSDT": 25_000,
    "SOLUSDT": 10_000,
}
DEFAULT_LARGE_THRESHOLD = 10_000


def _bucket_start(ts_seconds: float, tf_seconds: int) -> int:
    """Get the candle bucket start time (unix seconds) for a timestamp."""
    return math.floor(ts_seconds / tf_seconds) * tf_seconds


def _tick_size_for_price(price: float) -> float:
    """Auto-determine price bucket size for footprint levels (backend parity)."""
    if price > 10000:
        return 50.0  # BTC: $50 buckets
    elif price > 1000:
        return 10.0
    elif price > 100:
        return 1.0
    elif price > 10:
        return 0.5
    elif price > 1:
        return 0.1
    else:
        return 0.01


class _LiveCandle:
    """In-memory accumulator for a single candle's footprint (backend parity)."""

    __slots__ = (
        "symbol", "bucket_start", "tick_size",
        "price_levels", "buy_count", "sell_count",
        "buy_volume", "sell_volume", "large_trades",
    )

    def __init__(self, symbol: str, bucket_start: int, tick_size: float):
        self.symbol = symbol
        self.bucket_start = bucket_start
        self.tick_size = tick_size
        self.price_levels: dict[float, dict] = defaultdict(
            lambda: {"bv": 0.0, "sv": 0.0, "bc": 0, "sc": 0}
        )
        self.buy_count = 0
        self.sell_count = 0
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.large_trades: list[dict] = []

    def add_trade(self, price: float, qty: float, is_buy: bool, ts: float):
        # Bucket the price into a tick-size level.
        level = math.floor(price / self.tick_size) * self.tick_size
        pl = self.price_levels[level]

        if is_buy:
            pl["bv"] += qty
            pl["bc"] += 1
            self.buy_count += 1
            self.buy_volume += qty
        else:
            pl["sv"] += qty
            pl["sc"] += 1
            self.sell_count += 1
            self.sell_volume += qty

    def to_dict(self) -> dict:
        # Round values for clean JSON — keyed by stringified price level.
        price_levels = {}
        for level, data in sorted(self.price_levels.items()):
            price_levels[str(round(level, 8))] = {
                "bv": round(data["bv"], 6),
                "sv": round(data["sv"], 6),
                "bc": data["bc"],
                "sc": data["sc"],
            }

        return {
            "timestamp": float(self.bucket_start),
            "price_levels": price_levels,
            "buy_count": self.buy_count,
            "sell_count": self.sell_count,
            "buy_volume": round(self.buy_volume, 6),
            "sell_volume": round(self.sell_volume, 6),
            "tick_size": self.tick_size,
            "large_trades": self.large_trades[-50:],  # cap at 50
        }


def build_footprints(
    trades: list[dict],
    timeframe_seconds: int,
    symbol: str,
    large_threshold: float | None = None,
) -> list[dict]:
    """Reconstruct footprint candles from a flat list of trades.

    Args:
        trades: Normalized trades from ``data.agg_trades.fetch_agg_trades`` —
            each ``{"price", "qty", "is_buyer_maker", "time"}`` (time in unix
            seconds). May be in any order; bucketed by timestamp.
        timeframe_seconds: Bucket size in seconds (one of ``TF_SECONDS``).
        symbol: Upper-cased symbol, used for the large-trade threshold lookup.
        large_threshold: Override the quote-value threshold for large trades.
            Defaults to the per-symbol table / ``DEFAULT_LARGE_THRESHOLD``.

    Returns:
        A list of candle dicts (one per occupied time bucket), chronological,
        each matching the backend ``to_dict`` shape plus a ``timestamp`` (unix
        seconds, bucket start). Empty list if ``trades`` is empty.
    """
    sym = symbol.strip().upper()
    if large_threshold is None:
        large_threshold = LARGE_TRADE_THRESHOLDS.get(sym, DEFAULT_LARGE_THRESHOLD)

    candles: dict[int, _LiveCandle] = {}

    for tr in trades:
        price = float(tr["price"])
        qty = float(tr["qty"])
        # Binance flag semantics, identical to the backend: a trade where the
        # buyer was the maker means an aggressive market SELL hit the bid.
        is_buy = not bool(tr["is_buyer_maker"])
        ts = float(tr["time"])

        bucket = _bucket_start(ts, timeframe_seconds)
        candle = candles.get(bucket)
        if candle is None:
            candle = _LiveCandle(sym, bucket, _tick_size_for_price(price))
            candles[bucket] = candle

        candle.add_trade(price, qty, is_buy, ts)

        quote_value = price * qty
        if quote_value >= large_threshold:
            candle.large_trades.append({
                "t": round(ts),
                "p": round(price, 2),
                "v": round(qty, 6),
                "q": round(quote_value),
                "s": "buy" if is_buy else "sell",
            })

    return [candles[b].to_dict() for b in sorted(candles)]
