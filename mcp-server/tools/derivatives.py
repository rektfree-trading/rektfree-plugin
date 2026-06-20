"""
``get_derivatives`` — futures positioning tool (crypto, keyless).

Fetches funding rate, open interest, account long/short ratios (global +
top-trader), and taker flow from Binance's public futures endpoints, then shapes
them — funding as %/annualized, OI change & trend, positioning divergence — into
structured JSON for the model to interpret (squeeze risk, crowding, conviction).
"""

from __future__ import annotations

import time

from data import derivatives
from data.binance import BinanceError
from tools._common import crypto_only_error

# Funding is exchanged every 8h on Binance perps → 3 payments/day.
_FUNDING_PER_DAY = 3
_FUNDING_DAYS_PER_YEAR = 365

# Period token → hours, to label the OI/positioning lookback window.
_PERIOD_HOURS = {
    "5m": 1 / 12, "15m": 0.25, "30m": 0.5, "1h": 1, "2h": 2,
    "4h": 4, "6h": 6, "12h": 12, "1d": 24,
}


def _trend(series: list[dict], key: str = "ratio", flat_pct: float = 1.0) -> str | None:
    """Classify a series' direction as rising / falling / flat (last vs first)."""
    if len(series) < 2:
        return None
    first, last = series[0][key], series[-1][key]
    if first == 0:
        return None
    change = (last - first) / abs(first) * 100
    if change > flat_pct:
        return "rising"
    if change < -flat_pct:
        return "falling"
    return "flat"


def _pct_change(series: list[dict], key: str) -> float | None:
    """Percent change of ``key`` from the first to the last point of a series."""
    if len(series) < 2 or series[0][key] == 0:
        return None
    return round((series[-1][key] - series[0][key]) / series[0][key] * 100, 4)


def register(mcp) -> None:
    @mcp.tool()
    async def get_derivatives(
        symbol: str = "BTCUSDT",
        period: str = "1h",
        limit: int = 24,
    ) -> dict:
        """Fetch crypto **futures positioning** — funding, OI, long/short, taker flow.

        Pulls from Binance's public, keyless futures endpoints and computes the
        trader-relevant shaping the hosted product stores in a DB (OI change,
        positioning trend) on the fly:

        - **Funding rate** — current %, annualized %, and time to next funding.
          Positive = longs pay shorts (crowded long); negative = shorts pay
          (crowded short); extremes flag squeeze risk.
        - **Open interest** — current value plus % change and trend over the
          lookback. OI rising with price = new positions backing the move; OI
          falling = positions closing (possible squeeze/unwind).
        - **Long/short account ratio** — both **global** (the crowd) and
          **top-trader** (large accounts, a smart-money proxy). Divergence
          between them is a signal.
        - **Taker buy/sell ratio** — aggressor flow; divergence from price hints
          at absorption/distribution.

        Args:
            symbol: Binance perp symbol, no separator (e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``). Forex pairs (with ``_``) have no
                futures data and are rejected.
            period: Lookback granularity — one of 5m, 15m, 30m, 1h, 2h, 4h, 6h,
                12h, 1d. Default ``1h``.
            limit: Number of trailing periods (1–500). Default 24 (24h at 1h).

        Returns:
            A dict with ``symbol``, ``mark_price``, ``funding``, ``open_interest``,
            ``long_short`` (global + top-trader, current + trend), ``taker``, a
            short ``lookback`` descriptor, and compact ``series`` for the model
            to read the trend. On failure, a dict with an ``error`` key.
        """
        if err := crypto_only_error(symbol):
            return err

        if period not in derivatives.VALID_PERIODS:
            return {
                "error": (
                    f"Unsupported period '{period}'. Valid values: "
                    + ", ".join(derivatives.VALID_PERIODS)
                )
            }
        limit = max(1, min(int(limit), 500))

        try:
            data = await derivatives.fetch_all(symbol, period=period, limit=limit)
        except BinanceError as exc:
            return {"error": str(exc)}

        funding = data["funding"]
        rate = funding["funding_rate"]
        now_ms = time.time() * 1000
        next_ms = funding["next_funding_time"]
        next_in_hours = round((next_ms - now_ms) / 3_600_000, 2) if next_ms else None

        oi_hist = data["oi_history"]
        glob = data["global_long_short"]
        top = data["top_long_short"]
        taker = data["taker"]
        lookback_hours = round(_PERIOD_HOURS.get(period, 1) * len(oi_hist or [1]), 2)

        return {
            "symbol": symbol.upper(),
            "mark_price": funding["mark_price"],
            "lookback": {"period": period, "limit": limit, "hours": lookback_hours},
            "funding": {
                "rate": rate,
                "rate_pct": round(rate * 100, 5),
                "annualized_pct": round(
                    rate * _FUNDING_PER_DAY * _FUNDING_DAYS_PER_YEAR * 100, 3
                ),
                "next_funding_time": next_ms,
                "next_funding_in_hours": next_in_hours,
            },
            "open_interest": {
                "current": data["open_interest"],
                "value_usdt": oi_hist[-1]["oi_value"] if oi_hist else None,
                "change_pct": _pct_change(oi_hist, "oi"),
                "trend": _trend(oi_hist, key="oi"),
            },
            "long_short": {
                "global_ratio": glob[-1]["ratio"] if glob else None,
                "global_trend": _trend(glob, key="ratio"),
                "top_trader_ratio": top[-1]["ratio"] if top else None,
                "top_trader_trend": _trend(top, key="ratio"),
            },
            "taker": {
                "buy_sell_ratio": taker[-1]["ratio"] if taker else None,
                "trend": _trend(taker, key="ratio"),
            },
            "series": {
                "open_interest": [
                    {"time": p["time"], "oi": p["oi"]} for p in oi_hist[-12:]
                ],
                "global_long_short": [
                    {"time": p["time"], "ratio": p["ratio"]} for p in glob[-12:]
                ],
                "taker": [
                    {"time": p["time"], "ratio": p["ratio"]} for p in taker[-12:]
                ],
            },
        }
