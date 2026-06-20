"""
OANDA REST candle fetcher — **bring-your-own-token** forex/metals data.

Unlike Binance (keyless), OANDA requires a personal API token even for candles.
The plugin reads it from the environment so the *user* supplies their own — we
never ship a token. Set:

    RF_OANDA_TOKEN   your OANDA REST API token (required for forex)
    RF_OANDA_ENV     "practice" (default) or "live" — picks the host
    RF_OANDA_BASE    optional full base URL override (e.g. a custom host)

Only the candles endpoint is used (``/v3/instruments/{instrument}/candles``),
which needs just the Bearer token — no account id. Forex symbols are the OANDA
instrument format with an underscore (``EUR_USD``, ``XAU_USD``), which is exactly
the plugin's forex symbol convention, so the symbol passes straight through.

Returns the same candle dict shape as ``binance`` (float OHLCV + unix-second
``time``) and raises ``binance.BinanceError`` so callers catch one error type.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import httpx

from data.binance import BinanceError

# OANDA granularity tokens keyed by the plugin's timeframe strings.
GRANULARITY_MAP: dict[str, str] = {
    "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
    "1h": "H1", "4h": "H4", "1d": "D", "1w": "W",
    # friendly aliases
    "h1": "H1", "h4": "H4", "m1": "M1", "m5": "M5", "m15": "M15",
    "d": "D", "d1": "D", "w": "W", "w1": "W",
}

# OANDA caps a single candles request at 5000.
MAX_COUNT = 5000

_HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5
_MAX_RETRY_SLEEP = 8.0
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_HTTP_TIMEOUT = httpx.Timeout(20.0, connect=5.0)


def _clean_token() -> str | None:
    """The configured OANDA token, or None if unset / an unresolved placeholder.

    Guards against a config that passes a literal ``${RF_OANDA_TOKEN}`` (an
    unexpanded substitution) — treat that as "not set" so the user gets the
    helpful setup error rather than a confusing 401.
    """
    tok = (os.environ.get("RF_OANDA_TOKEN") or "").strip()
    if not tok or tok.startswith("${"):
        return None
    return tok


def has_token() -> bool:
    """True when an OANDA token is configured (forex analysis available)."""
    return _clean_token() is not None


def _base_url() -> str:
    if override := os.environ.get("RF_OANDA_BASE"):
        return override.rstrip("/")
    env = (os.environ.get("RF_OANDA_ENV") or "practice").strip().lower()
    return _HOSTS.get(env, _HOSTS["practice"])


def _token_or_raise(symbol: str) -> str:
    token = _clean_token()
    if not token:
        raise BinanceError(
            f"'{symbol}' is a forex/metals symbol, which needs an OANDA API "
            "token. Set RF_OANDA_TOKEN (and optionally RF_OANDA_ENV=practice|live) "
            "in the plugin's MCP env, then reconnect. Crypto symbols (e.g. BTCUSDT) "
            "need no key."
        )
    return token


def normalize_granularity(timeframe: str) -> str:
    key = timeframe.strip().lower()
    if key not in GRANULARITY_MAP:
        valid = ", ".join(sorted({v for v in GRANULARITY_MAP.values()}))
        raise BinanceError(f"Unsupported timeframe '{timeframe}'. OANDA granularities: {valid}")
    return GRANULARITY_MAP[key]


def _parse(raw: dict) -> list[dict]:
    out: list[dict] = []
    for c in raw.get("candles", []):
        if not c.get("complete", False):
            continue  # skip the still-forming candle
        mid = c["mid"]
        ts = c["time"].replace("000Z", "+00:00").replace("Z", "+00:00")
        out.append(
            {
                "time": datetime.fromisoformat(ts).timestamp(),
                "open": float(mid["o"]),
                "high": float(mid["h"]),
                "low": float(mid["l"]),
                "close": float(mid["c"]),
                "volume": float(c.get("volume", 0)),
            }
        )
    return out


async def _request(client: httpx.AsyncClient, url: str, headers: dict) -> dict:
    last_err = "unknown error"
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            last_err = f"network error: {exc}"
        else:
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (401, 403):
                raise BinanceError(
                    "OANDA rejected the token (HTTP "
                    f"{resp.status_code}). Check RF_OANDA_TOKEN and RF_OANDA_ENV "
                    "(practice vs live must match where the token was issued)."
                )
            if resp.status_code in (400, 404):
                raise BinanceError(f"OANDA rejected the request (HTTP {resp.status_code}): {resp.text[:200]}")
            if resp.status_code not in _RETRY_STATUS:
                raise BinanceError(f"OANDA returned HTTP {resp.status_code}: {resp.text[:200]}")
            last_err = f"HTTP {resp.status_code}"
        if attempt >= _MAX_RETRIES:
            break
        await asyncio.sleep(min(_BACKOFF_BASE * (2 ** attempt), _MAX_RETRY_SLEEP))
    raise BinanceError(f"OANDA unavailable after {_MAX_RETRIES + 1} attempts ({last_err}).")


async def fetch_candles(symbol: str, timeframe: str = "1h", limit: int = 500) -> list[dict]:
    """Fetch historical OANDA candles (bring-your-own RF_OANDA_TOKEN).

    Args:
        symbol: OANDA instrument with an underscore, e.g. ``EUR_USD``, ``XAU_USD``.
        timeframe: 1m/5m/15m/30m/1h/4h/1d/1w (aliases accepted).
        limit: Number of candles (capped at 5000 by OANDA).

    Returns:
        Candle dicts oldest→newest with float OHLCV + unix-second ``time``.

    Raises:
        BinanceError: if no token is set, on auth/HTTP failure, or bad timeframe.
    """
    token = _token_or_raise(symbol)
    granularity = normalize_granularity(timeframe)
    count = max(1, min(int(limit), MAX_COUNT))
    instrument = symbol.strip().upper()
    url = (
        f"{_base_url()}/v3/instruments/{instrument}/candles"
        f"?granularity={granularity}&count={count}&price=M"
    )
    headers = {"Authorization": f"Bearer {token}", "Accept-Datetime-Format": "RFC3339"}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        raw = await _request(client, url, headers)
    return _parse(raw)


async def fetch_candles_paged(
    symbol: str, timeframe: str = "1h", total: int = 2000, max_pages: int = 6
) -> list[dict]:
    """Fetch up to ``total`` recent OANDA candles, paging the 5000/request cap.

    Pages forward with ``from`` timestamps. Deduplicates by candle time and
    returns oldest→newest. Capped at ``max_pages`` requests.
    """
    token = _token_or_raise(symbol)
    granularity = normalize_granularity(timeframe)
    instrument = symbol.strip().upper()
    total = max(1, int(total))
    headers = {"Authorization": f"Bearer {token}", "Accept-Datetime-Format": "RFC3339"}
    base = _base_url()

    if total <= MAX_COUNT:
        return await fetch_candles(symbol, timeframe, total)

    seen: set[float] = set()
    candles: list[dict] = []
    # Start ~`total` candles back; OANDA returns up to MAX_COUNT from `from`.
    from_dt: str | None = None
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for _ in range(max(1, int(max_pages))):
            url = f"{base}/v3/instruments/{instrument}/candles?granularity={granularity}&count={MAX_COUNT}&price=M"
            if from_dt:
                url += f"&from={from_dt}"
            raw = await _request(client, url, headers)
            page = _parse(raw)
            if not page:
                break
            new = [c for c in page if c["time"] not in seen]
            for c in new:
                seen.add(c["time"])
            candles.extend(new)
            if len(page) < MAX_COUNT or len(candles) >= total:
                break
            # Next page starts just after the last candle we got (RFC3339).
            last = datetime.fromtimestamp(page[-1]["time"] + 1, tz=timezone.utc)
            from_dt = last.strftime("%Y-%m-%dT%H:%M:%SZ")
    candles.sort(key=lambda c: c["time"])
    return candles[-total:]
