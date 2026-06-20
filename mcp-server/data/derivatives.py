"""
Keyless Binance **Futures** (derivatives) fetchers.

Binance's futures endpoints under ``fapi.binance.com`` are public and need no
API key, so perp positioning data works out of the box: funding rate, open
interest, account long/short ratios (global *and* top-trader), and taker
buy/sell flow.

The hosted backend polls a single snapshot every 5 minutes and stores it, then
computes OI change from the prior DB row. The plugin has no DB — but it doesn't
need one here: Binance also exposes public *history* endpoints
(``openInterestHist`` and the ratio ``…Ratio`` series), so we fetch a short
trailing window and compute change / trend on the fly. That actually gives a
richer read than a single stored snapshot.

Derivatives are crypto-only (futures); forex pairs have no equivalent — same as
the hosted product.
"""

from __future__ import annotations

import asyncio

import httpx

from data.binance import BinanceError, request_json

# Futures REST host (distinct from the spot ``api.binance.com`` base).
BINANCE_FAPI = "https://fapi.binance.com"

# Valid period tokens for the futures-data history endpoints.
VALID_PERIODS = ("5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d")

_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


async def _funding(client: httpx.AsyncClient, symbol: str) -> dict:
    """Current funding rate, next funding time, and mark price (premiumIndex)."""
    data = await request_json(
        client, "fapi/v1/premiumIndex", {"symbol": symbol},
        context="derivatives", base=BINANCE_FAPI,
    )
    return {
        "funding_rate": float(data.get("lastFundingRate", 0) or 0),
        "next_funding_time": float(data.get("nextFundingTime", 0) or 0),
        "mark_price": float(data.get("markPrice", 0) or 0),
    }


async def _open_interest(client: httpx.AsyncClient, symbol: str) -> float:
    """Current open interest in base (coin) units."""
    data = await request_json(
        client, "fapi/v1/openInterest", {"symbol": symbol},
        context="derivatives", base=BINANCE_FAPI,
    )
    return float(data.get("openInterest", 0) or 0)


async def _oi_history(client: httpx.AsyncClient, symbol: str, period: str, limit: int) -> list[dict]:
    """Trailing open-interest series (coin units + USDT value), oldest→newest."""
    data = await request_json(
        client, "futures/data/openInterestHist",
        {"symbol": symbol, "period": period, "limit": limit},
        context="derivatives", base=BINANCE_FAPI,
    )
    return [
        {
            "time": float(d["timestamp"]) / 1000.0,
            "oi": float(d["sumOpenInterest"]),
            "oi_value": float(d["sumOpenInterestValue"]),
        }
        for d in (data or [])
    ]


async def _long_short(
    client: httpx.AsyncClient, symbol: str, period: str, limit: int, *, top: bool
) -> list[dict]:
    """Long/short account-ratio series, oldest→newest.

    ``top=True`` queries the **top-trader** ratio (large accounts — a smart-money
    proxy); ``top=False`` queries the **global** account ratio (the crowd).
    """
    path = (
        "futures/data/topLongShortAccountRatio" if top
        else "futures/data/globalLongShortAccountRatio"
    )
    data = await request_json(
        client, path, {"symbol": symbol, "period": period, "limit": limit},
        context="derivatives", base=BINANCE_FAPI,
    )
    return [
        {
            "time": float(d["timestamp"]) / 1000.0,
            "ratio": float(d["longShortRatio"]),
            "long_account": float(d.get("longAccount", 0) or 0),
            "short_account": float(d.get("shortAccount", 0) or 0),
        }
        for d in (data or [])
    ]


async def _taker(client: httpx.AsyncClient, symbol: str, period: str, limit: int) -> list[dict]:
    """Taker buy/sell volume-ratio series, oldest→newest (aggressor flow)."""
    data = await request_json(
        client, "futures/data/takerlongshortRatio",
        {"symbol": symbol, "period": period, "limit": limit},
        context="derivatives", base=BINANCE_FAPI,
    )
    return [
        {
            "time": float(d["timestamp"]) / 1000.0,
            "ratio": float(d["buySellRatio"]),
            "buy_vol": float(d.get("buyVol", 0) or 0),
            "sell_vol": float(d.get("sellVol", 0) or 0),
        }
        for d in (data or [])
    ]


async def fetch_all(symbol: str, period: str = "1h", limit: int = 24) -> dict:
    """Fetch the full derivatives picture for ``symbol`` (keyless).

    Funding rate and open interest are **required** — a failure there raises
    ``BinanceError`` (e.g. an unknown symbol). The history series (OI, global &
    top-trader long/short, taker) are **best-effort**: a flaky/empty optional
    endpoint degrades to ``None``/``[]`` rather than failing the whole call.

    Args:
        symbol: Binance perp symbol, e.g. ``BTCUSDT`` (no separator).
        period: One of ``VALID_PERIODS`` for the history endpoints.
        limit: Number of trailing periods to pull (Binance caps at 500).

    Returns:
        A dict with ``funding``, ``open_interest`` (current, coin units), and the
        ``oi_history`` / ``global_long_short`` / ``top_long_short`` / ``taker``
        series (each a list, possibly empty).

    Raises:
        BinanceError: if the required funding/OI fetch fails.
    """
    sym = symbol.strip().upper()

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        async def _opt(coro):
            try:
                return await coro
            except BinanceError:
                return None

        # Required — let these propagate.
        funding, oi = await asyncio.gather(
            _funding(client, sym),
            _open_interest(client, sym),
        )
        # Best-effort series.
        oi_hist, glob_ls, top_ls, taker = await asyncio.gather(
            _opt(_oi_history(client, sym, period, limit)),
            _opt(_long_short(client, sym, period, limit, top=False)),
            _opt(_long_short(client, sym, period, limit, top=True)),
            _opt(_taker(client, sym, period, limit)),
        )

    return {
        "funding": funding,
        "open_interest": oi,
        "oi_history": oi_hist or [],
        "global_long_short": glob_ls or [],
        "top_long_short": top_ls or [],
        "taker": taker or [],
    }
