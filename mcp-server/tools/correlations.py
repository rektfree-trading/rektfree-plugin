"""
``get_correlations`` — cross-asset correlation for crypto (keyless).

Fetches aligned Binance candles for a watchlist (or a single symbol vs a base),
computes log-return Pearson correlations — a full symmetric matrix plus each
symbol vs the base (default ``BTCUSDT``) — and a recent-vs-older regime shift so
the model can read whether the market is tightening to BTC (risk-on rotation /
everything-follows-BTC) or decoupling (diversification showing up).

Pure-Python math lives in ``engines/correlations.py``; this module only fetches,
aligns, and shapes the JSON. Crypto only — forex (``_``) symbols are skipped.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from data import binance
from engines import correlations as corr

# Default watchlist when no symbols are given — liquid USDT pairs, BTC-led.
DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
]

# Cap the fan-out so one call can't hammer Binance (each symbol = 1 fetch).
MAX_SYMBOLS = 10

# Minimum aligned bars for a meaningful correlation. Below this, short-window
# noise dominates and the numbers mislead.
MIN_ALIGNED_BARS = 20


def _parse_symbols(symbols: str) -> list[str]:
    """Parse a comma/space-separated symbol string into a clean upper list."""
    if not symbols or not symbols.strip():
        return list(DEFAULT_WATCHLIST)
    raw = symbols.replace(",", " ").split()
    seen: set[str] = set()
    out: list[str] = []
    for s in raw:
        sym = s.strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def register(mcp) -> None:
    @mcp.tool()
    async def get_correlations(
        symbols: str = "",
        base: str = "BTCUSDT",
        timeframe: str = "4h",
        limit: int = 180,
    ) -> dict:
        """Cross-asset correlation for a crypto watchlist vs a base (default BTC).

        Fetches candles for each symbol concurrently, aligns them by timestamp
        (so every correlation uses matching bars), computes log returns, then a
        Pearson correlation matrix across all symbols and each symbol vs the
        ``base``. Adds a regime shift — correlation over the recent half of the
        window vs the older half — so the model can read "tightening" (moving
        with BTC, risk-on / everything-follows-BTC) vs "decoupling" (going its
        own way, diversification). Returns structured JSON for the model to
        interpret — confirmation, diversification, and doubled-up risk.

        Args:
            symbols: Comma/space-separated Binance crypto symbols, e.g.
                ``"ETHUSDT, SOLUSDT"``. Empty → a default watchlist
                (BTC/ETH/SOL/BNB/XRP). The ``base`` is always included. Capped
                at 10 symbols. Forex pairs (with ``_``) are skipped.
            base: The reference symbol every other is measured against. Default
                ``BTCUSDT`` — for crypto, BTC is the market's beta anchor.
            timeframe: Candle interval, one of 1m/5m/15m/1h/4h/1d/1w (aliases
                accepted). Default ``4h``.
            limit: Candles per symbol to fetch (≤1000). Default 180 (~30 days of
                4h bars). More bars = steadier correlation, less reactive.

        Returns:
            A dict with ``base``, ``timeframe``, ``window`` ({bars, from, to}),
            ``vs_base`` (list of {symbol, r, strength, direction, recent_r,
            older_r, shift}, sorted by |r| desc), ``matrix`` (symmetric
            {symbol: {symbol: r}} with 1.0 diagonal), and ``skipped`` (rejected
            symbols with reasons). On a hard failure, a dict with an ``error``
            key.
        """
        base = (base or "BTCUSDT").strip().upper()
        skipped: list[dict] = []

        # Base must be crypto — it anchors every correlation.
        if "_" in base:
            return {
                "error": (
                    f"base '{base}' looks like a forex pair. get_correlations "
                    "only supports keyless crypto symbols (e.g. BTCUSDT)."
                )
            }

        # Build the symbol set: requested + base, dedup, drop forex, cap.
        requested = _parse_symbols(symbols)
        wanted: list[str] = [base]
        for s in requested:
            if "_" in s:
                skipped.append({"symbol": s, "reason": "forex pair (not supported)"})
                continue
            if s not in wanted:
                wanted.append(s)

        if len(wanted) > MAX_SYMBOLS:
            for s in wanted[MAX_SYMBOLS:]:
                skipped.append({"symbol": s, "reason": f"over {MAX_SYMBOLS}-symbol cap"})
            wanted = wanted[:MAX_SYMBOLS]

        if len(wanted) < 2:
            return {
                "error": "Need at least 2 crypto symbols (base + one more) to correlate.",
                "skipped": skipped,
            }

        # Fetch all symbols concurrently. A single bad symbol shouldn't sink the
        # whole call — fold its error into `skipped` instead.
        async def _fetch(sym: str):
            try:
                return sym, await binance.fetch_candles(sym, timeframe, limit), None
            except binance.BinanceError as exc:
                return sym, None, str(exc)

        results = await asyncio.gather(*(_fetch(s) for s in wanted))

        series: dict[str, list[dict]] = {}
        for sym, candles, err in results:
            if err is not None:
                skipped.append({"symbol": sym, "reason": err})
            elif not candles:
                skipped.append({"symbol": sym, "reason": "no candle data"})
            else:
                series[sym] = candles

        if base not in series:
            return {
                "error": f"Could not fetch base symbol '{base}'.",
                "skipped": skipped,
            }
        if len(series) < 2:
            return {
                "error": "Fewer than 2 symbols had usable data after fetching.",
                "skipped": skipped,
            }

        # Align by timestamp so every return uses matching bars.
        times, aligned = corr.align_closes(series)
        if len(times) < MIN_ALIGNED_BARS:
            return {
                "error": (
                    f"Only {len(times)} aligned bars across symbols "
                    f"(need ≥{MIN_ALIGNED_BARS}). Try a wider limit or fewer symbols."
                ),
                "skipped": skipped,
            }

        # Log returns per symbol (all aligned → all same length).
        returns = {sym: corr.log_returns(closes) for sym, closes in aligned.items()}

        # Full matrix + vs-base read.
        matrix = corr.correlation_matrix(returns)

        base_ret = returns[base]
        half = len(base_ret) // 2
        vs_base: list[dict] = []
        for sym, ret in returns.items():
            if sym == base:
                continue
            r = round(corr.pearson(ret, base_ret), 4)
            # Regime shift: recent half vs older half of the return window.
            recent_r = round(corr.pearson(ret[half:], base_ret[half:]), 4)
            older_r = round(corr.pearson(ret[:half], base_ret[:half]), 4)
            vs_base.append({
                "symbol": sym,
                "r": r,
                "strength": corr.strength(r),
                "direction": corr.direction(r),
                "recent_r": recent_r,
                "older_r": older_r,
                "shift": corr.shift_label(recent_r, older_r),
            })

        vs_base.sort(key=lambda x: abs(x["r"]), reverse=True)

        def _iso(ts: float) -> str:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        return {
            "base": base,
            "timeframe": binance.normalize_timeframe(timeframe),
            "window": {
                "bars": len(times),
                "from": _iso(times[0]),
                "to": _iso(times[-1]),
            },
            "vs_base": vs_base,
            "matrix": matrix,
            "skipped": skipped,
        }
