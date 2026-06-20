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

import asyncio
import time

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

# Seconds per Binance interval — used by the paged historical fetcher to size a
# lookback window. Keyed by the canonical interval strings in TIMEFRAME_MAP.
INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}

_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

# Transient-failure retry policy. Traders hit these endpoints repeatedly
# (scanners, order-flow rebuilds), so a single 429 or network blip shouldn't
# surface as a hard error — we retry with exponential backoff, honoring a
# Retry-After header when Binance sends one.
_MAX_RETRIES = 3            # extra attempts after the first (4 tries total)
_BACKOFF_BASE = 0.5         # seconds, doubled each attempt
_MAX_RETRY_SLEEP = 8.0      # cap any single backoff/Retry-After wait
# 429 = rate limited, 418 = IP auto-banned for ignoring 429s, 5xx = upstream.
_RETRY_STATUS = frozenset({418, 429, 500, 502, 503, 504})


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


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds form) into float seconds."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


async def request_json(
    client: httpx.AsyncClient,
    path: str,
    params: dict,
    *,
    context: str = "request",
):
    """GET a Binance REST endpoint with bounded retry/backoff; return parsed JSON.

    Retries transient failures — HTTP 429/418 (rate limit / IP throttle), 5xx,
    and network errors — with exponential backoff, honoring a ``Retry-After``
    header when present. A 400 (bad symbol/params) is terminal and raises
    immediately, as does an exhausted retry budget.

    Args:
        client: An open ``httpx.AsyncClient`` (callers reuse one across pages).
        path: Endpoint path under the REST base, e.g. ``"klines"``.
        params: Query parameters (should include ``symbol`` for error context).
        context: Short label used in error messages (e.g. ``"request"``,
            ``"aggTrades"``).

    Returns:
        The decoded JSON (``list`` or ``dict``).

    Raises:
        BinanceError: on a terminal 400, a non-retriable status, a malformed
            body, or once the retry budget is exhausted.
    """
    url = f"{BINANCE_REST_URL}/{path.lstrip('/')}"
    sym = params.get("symbol", "?")
    last_err = "unknown error"

    for attempt in range(_MAX_RETRIES + 1):
        retry_after: float | None = None
        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:  # network / timeout — transient
            last_err = f"network error: {exc}"
        else:
            if resp.status_code == 200:
                raw = resp.json()
                if not isinstance(raw, (list, dict)):
                    raise BinanceError(f"Unexpected Binance response: {raw!r}")
                return raw
            if resp.status_code == 400:
                # Binance returns 400 + JSON {"code","msg"} for bad symbols.
                try:
                    msg = resp.json().get("msg", resp.text)
                except Exception:
                    msg = resp.text
                raise BinanceError(
                    f"Binance rejected {context} for symbol '{sym}': {msg}"
                )
            if resp.status_code not in _RETRY_STATUS:
                raise BinanceError(
                    f"Binance returned HTTP {resp.status_code}: {resp.text[:200]}"
                )
            last_err = f"HTTP {resp.status_code}"
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))

        if attempt >= _MAX_RETRIES:
            break
        sleep_s = retry_after if retry_after is not None else _BACKOFF_BASE * (2 ** attempt)
        await asyncio.sleep(min(sleep_s, _MAX_RETRY_SLEEP))

    raise BinanceError(
        f"Binance unavailable for {context} '{sym}' after "
        f"{_MAX_RETRIES + 1} attempts ({last_err})."
    )


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

    params = {"symbol": sym, "interval": interval, "limit": limit}

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        raw = await request_json(client, "klines", params, context="request")

    if not isinstance(raw, list):
        raise BinanceError(f"Unexpected Binance response: {raw!r}")

    return [_kline_to_candle(item) for item in raw]


def _kline_to_candle(item: list) -> dict:
    """Convert one raw Binance kline row to a candle dict.

    Kline layout: ``[openTime, open, high, low, close, volume, ...]``.
    """
    return {
        "time": item[0] / 1000.0,  # ms → unix seconds
        "open": float(item[1]),
        "high": float(item[2]),
        "low": float(item[3]),
        "close": float(item[4]),
        "volume": float(item[5]),
    }


async def fetch_candles_paged(
    symbol: str,
    timeframe: str = "1h",
    total: int = 2000,
    max_pages: int = 8,
) -> list[dict]:
    """Fetch up to ``total`` recent candles by paging Binance klines (keyless).

    A single klines request caps at 1000 candles; statistics need a deeper
    history, so this pages forward across a ``[now - total*interval, now]``
    window, assembling and de-duplicating candles. Reuses the retrying
    ``request_json`` helper and is hard-capped at ``max_pages`` requests to stay
    polite to Binance's rate limits — so the returned series may be shorter than
    ``total`` if the cap is hit first.

    Args:
        symbol: Binance symbol, e.g. ``BTCUSDT`` (no separator).
        timeframe: One of 1m/5m/15m/1h/4h/1d/1w (aliases accepted).
        total: Target number of most-recent candles to assemble.
        max_pages: Hard cap on REST requests (each yields ≤1000 candles).

    Returns:
        A list of candle dicts ordered oldest→newest (same shape as
        :func:`fetch_candles`).

    Raises:
        BinanceError: on HTTP failure or unexpected response shape.
    """
    interval = normalize_timeframe(timeframe)
    sec = INTERVAL_SECONDS[interval]
    sym = symbol.strip().upper()
    total = max(1, int(total))

    now_ms = int(time.time() * 1000)
    cursor = now_ms - total * sec * 1000  # window start
    seen: set[int] = set()
    candles: list[dict] = []

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for _ in range(max(1, int(max_pages))):
            if cursor >= now_ms:
                break
            params = {
                "symbol": sym,
                "interval": interval,
                "startTime": cursor,
                "limit": MAX_LIMIT,
            }
            raw = await request_json(client, "klines", params, context="request")
            if not isinstance(raw, list):
                raise BinanceError(f"Unexpected Binance response: {raw!r}")
            if not raw:
                break

            for item in raw:
                open_ms = int(item[0])
                if open_ms in seen:
                    continue
                seen.add(open_ms)
                candles.append(_kline_to_candle(item))

            # Short page → window exhausted. Otherwise advance past the last
            # open time to the next bucket.
            if len(raw) < MAX_LIMIT:
                break
            cursor = int(raw[-1][0]) + sec * 1000

    candles.sort(key=lambda c: c["time"])
    return candles
