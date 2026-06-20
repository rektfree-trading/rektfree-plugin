"""
Keyless Binance REST aggregated-trades fetcher.

Binance's public ``/api/v3/aggTrades`` endpoint requires no API key or auth, so
trade-level data works out of the box. The hosted backend builds footprints from
a live trade WebSocket and stores them in Postgres; the plugin has no stream and
no DB, so it reconstructs footprints on the fly from this historical endpoint.

Aggregated trades coalesce all fills of a single market order at one price into
one record, which is exactly the granularity the footprint builder needs:
``{p: price, q: qty, T: timestampMs, m: isBuyerMaker}``. We page across a time
window with ``startTime``/``endTime`` (1000 trades per page) and cap the total
request count so we stay polite to Binance's rate limits.

Forex (OANDA) is intentionally NOT here: it provides no individual trade data,
so footprint / order-flow analysis is crypto-only — same as the hosted product.
"""

from __future__ import annotations

import httpx

# Reuse the candle fetcher's error type + retrying request helper so callers can
# catch one class and both fetchers share the same rate-limit/backoff behavior.
from data.binance import BinanceError, request_json

# Binance caps a single aggTrades request at 1000 records.
MAX_PER_PAGE = 1000

# Politeness cap: never issue more than this many pages for one footprint build.
# 20 pages × 1000 trades ≈ 20k trades, plenty for a handful of 5m/15m/1h candles
# on a liquid pair while keeping us well clear of Binance's weight limits.
DEFAULT_MAX_PAGES = 20

_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


async def fetch_agg_trades(
    symbol: str,
    start_ms: int,
    end_ms: int,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[dict]:
    """Fetch aggregated trades in ``[start_ms, end_ms]`` from Binance (keyless).

    Pages forward through the window: each request asks for up to 1000 trades
    starting at ``startTime``; the next page advances ``startTime`` to the last
    returned trade's timestamp + 1ms. Stops when the window is exhausted, a page
    comes back short (no more data), or ``max_pages`` is hit (truncation).

    Args:
        symbol: Binance symbol, e.g. ``BTCUSDT`` (no separator).
        start_ms: Window start, unix milliseconds (inclusive).
        end_ms: Window end, unix milliseconds (inclusive).
        max_pages: Hard cap on REST requests to respect rate limits.

    Returns:
        A list of normalized trade dicts ordered oldest→newest, each:
        ``{"price": float, "qty": float, "is_buyer_maker": bool,
        "time": float}`` where ``time`` is unix seconds. The list may be
        truncated (fewer trades than the full window) if ``max_pages`` is hit.

    Raises:
        BinanceError: on HTTP failure or unexpected response shape.
    """
    sym = symbol.strip().upper()

    trades: list[dict] = []
    cursor = int(start_ms)
    end_ms = int(end_ms)

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            for _ in range(max(1, int(max_pages))):
                if cursor > end_ms:
                    break

                params = {
                    "symbol": sym,
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": MAX_PER_PAGE,
                }
                # Shared helper: retries 429/418/5xx + network blips with
                # backoff, raises BinanceError on a bad symbol (400).
                raw = await request_json(client, "aggTrades", params, context="aggTrades")
                if not isinstance(raw, list):
                    raise BinanceError(f"Unexpected Binance response: {raw!r}")

                if not raw:
                    break

                last_ms = cursor
                for item in raw:
                    t_ms = int(item["T"])
                    last_ms = t_ms
                    trades.append(
                        {
                            "price": float(item["p"]),
                            "qty": float(item["q"]),
                            "is_buyer_maker": bool(item["m"]),
                            "time": t_ms / 1000.0,  # ms → unix seconds
                        }
                    )

                # Short page → no more data in the window.
                if len(raw) < MAX_PER_PAGE:
                    break

                # Advance past the last trade we saw. If a single millisecond
                # holds 1000+ trades we'd loop; bump by 1ms to guarantee
                # forward progress (may skip rare same-ms overflow — acceptable).
                next_cursor = last_ms + 1
                if next_cursor <= cursor:
                    next_cursor = cursor + 1
                cursor = next_cursor
    except BinanceError:
        raise
    except Exception as exc:  # defensive: malformed item, etc.
        raise BinanceError(f"Failed parsing Binance aggTrades: {exc}") from exc

    return trades
