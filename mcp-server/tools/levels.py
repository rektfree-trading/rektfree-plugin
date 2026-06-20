"""
``get_levels`` — key time-based price levels tool (crypto, keyless).

Fetches Binance 15m candles and runs the vendored levels engine, returning the
backend's /market/levels payload shape (``{symbol, last_price, levels}``).
"""

from __future__ import annotations

from data import binance
from engines import levels as levels_engine
from tools._common import crypto_only_error


def _serialize_levels(result: levels_engine.LevelsResult) -> list[dict]:
    """Flatten a LevelsResult into the backend's ``levels`` list shape.

    Mirrors the serialization in the backend's /market/levels router so labels
    and field names stay identical to the hosted product:
    each entry is ``{"label", "price", "time"}``.
    """

    def _pair(label: str, lp: levels_engine.LevelPair) -> list[dict]:
        out: list[dict] = []
        if lp.high > 0:
            out.append({"label": f"{label} High", "price": lp.high, "time": lp.high_time})
        if lp.low > 0:
            out.append({"label": f"{label} Low", "price": lp.low, "time": lp.low_time})
        return out

    def _open(label: str, price: float) -> list[dict]:
        return [{"label": label, "price": price, "time": 0}] if price > 0 else []

    def _session(prefix: str, sess: levels_engine.SessionLevel) -> list[dict]:
        out: list[dict] = []
        if sess.high > 0:
            out.append({"label": f"{prefix}{sess.name} High", "price": sess.high, "time": sess.high_time})
        if sess.low > 0:
            out.append({"label": f"{prefix}{sess.name} Low", "price": sess.low, "time": sess.low_time})
        return out

    lines: list[dict] = []
    # Current period
    lines += _pair("D", result.daily)
    lines += _pair("W", result.weekly)
    lines += _pair("M", result.monthly)
    # Previous period
    lines += _pair("pD", result.prev_daily)
    lines += _pair("pW", result.prev_weekly)
    lines += _pair("pM", result.prev_monthly)
    # Opens
    lines += _open("D Open", result.daily_open)
    lines += _open("Mon Open", result.monday_open)
    # Sessions (current day)
    for sess in result.sessions:
        lines += _session("", sess)
    # Sessions (previous day)
    for sess in result.prev_sessions:
        lines += _session("p", sess)
    return lines


def register(mcp) -> None:
    @mcp.tool()
    async def get_levels(symbol: str = "BTCUSDT") -> dict:
        """Compute key time-based price levels for a crypto symbol.

        Fetches 15m candles from Binance (public, no API key) covering ~10 days
        and derives the levels institutions anchor orders around: Daily/Weekly/
        Monthly highs, lows, and opens (current and previous period), plus
        session highs/lows (Asia/London/New York, today and yesterday). Returns
        structured JSON for the model to interpret — support/resistance,
        liquidity targets, and bias filters.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex pairs (with ``_``) are not
                supported in this slice.

        Returns:
            A dict with ``symbol``, ``last_price``, and ``levels`` — a list of
            ``{label, price, time}`` entries. Labels follow the backend
            convention: ``D/W/M`` = current day/week/month, ``pD/pW/pM`` =
            previous period, ``D Open``/``Mon Open`` = period opens, session
            names (``Asia``, ``London``, ``New York``) with ``p`` prefix for the
            prior day. On failure, a dict with an ``error`` key.
        """
        if err := crypto_only_error(symbol):
            return err

        # 1000 × 15m ≈ 10.4 days — enough for daily/weekly/session levels and
        # the current month so far. Mirrors the backend's /market/levels fetch.
        try:
            candles = await binance.fetch_candles(symbol, "15m", 1000)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not candles:
            return {"error": f"No candle data returned for {symbol}."}

        opens = [c["open"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        times = [c["time"] for c in candles]

        result = levels_engine.compute_levels(highs, lows, opens, closes, times)

        return {
            "symbol": symbol.upper(),
            "last_price": closes[-1],
            "levels": _serialize_levels(result),
        }
