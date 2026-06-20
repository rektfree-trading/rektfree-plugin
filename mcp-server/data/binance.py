"""
Keyless Binance REST candle fetcher.

Binance's public `/api/v3/klines` endpoint requires no API key or auth, so
crypto market data works out of the box. This is a slim, dependency-light
port of the backend's fetcher — no DB cache, no Decimal precision juggling,
just the bytes the SMC engine needs (floats + unix-second timestamps).

Forex (OANDA) is intentionally NOT here: it needs the user's Bearer token +
account id even for candles. That is the future "bring-your-own-keys" path.
"""

from __future__ import annotations

import httpx

BINANCE_REST_URL = "https://api.binance.com/api/v3"

# Binance interval strings keyed by the timeframe tokens we accept from users.
TIMEFRAME_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
    # Friendly aliases
    "h1": "1h",
    "h4": "4h",
    "m1": "1m",
    "m5": "5m",
    "m15": "15m",
    "d": "1d",
    "d1": "1d",
    "w": "1w",
    "w1": "1w",
}

# Binance caps a single klines request at 1000 candles.
MAX_LIMIT = 1000

_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class BinanceError(RuntimeError):
    """Raised when Binance returns an error or unexpected payload."""


def normalize_timeframe(timeframe: str) -> str:
    """Map a user-supplied timeframe token to a Binance interval string."""
    key = timeframe.strip().lower()
    if key not in TIMEFRAME_MAP:
        valid = ", ".join(sorted({v for v in TIMEFRAME_MAP.values()}))
        raise BinanceError(
            f"Unsupported timeframe '{timeframe}'. Valid values: {valid}"
        )
    return TIMEFRAME_MAP[key]


async def fetch_candles(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 500,
) -> list[dict]:
    """Fetch historical OHLCV candles from Binance (keyless).

    Args:
        symbol: Binance symbol, e.g. ``BTCUSDT`` (no separator).
        timeframe: One of 1m/5m/15m/1h/4h/1d/1w (aliases accepted).
        limit: Number of candles (capped at 1000 by Binance).

    Returns:
        A list of candle dicts ordered oldest→newest, each with float
        ``open/high/low/close/volume`` and a float ``time`` (unix seconds).

    Raises:
        BinanceError: on HTTP failure or unexpected response shape.
    """
    interval = normalize_timeframe(timeframe)
    limit = max(1, min(int(limit), MAX_LIMIT))
    sym = symbol.strip().upper()

    url = f"{BINANCE_REST_URL}/klines"
    params = {"symbol": sym, "interval": interval, "limit": limit}

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, params=params)
    except httpx.HTTPError as exc:  # network / timeout
        raise BinanceError(f"Network error reaching Binance: {exc}") from exc

    if resp.status_code == 400:
        # Binance returns 400 with a JSON {"code", "msg"} for bad symbols.
        try:
            msg = resp.json().get("msg", resp.text)
        except Exception:
            msg = resp.text
        raise BinanceError(
            f"Binance rejected request for symbol '{sym}': {msg}"
        )
    if resp.status_code != 200:
        raise BinanceError(
            f"Binance returned HTTP {resp.status_code}: {resp.text[:200]}"
        )

    raw = resp.json()
    if not isinstance(raw, list):
        raise BinanceError(f"Unexpected Binance response: {raw!r}")

    candles: list[dict] = []
    for item in raw:
        # Kline layout: [openTime, open, high, low, close, volume, ...]
        candles.append(
            {
                "time": item[0] / 1000.0,  # ms → unix seconds
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
        )
    return candles
