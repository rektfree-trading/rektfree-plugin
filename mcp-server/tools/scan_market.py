"""
``scan_market`` — multi-symbol confluence scanner (crypto, keyless).

Runs the same structural confluence grade as ``scan_confluence`` across a
watchlist of crypto symbols concurrently and returns them ranked by score, so a
trader can ask "any setups right now?" and get a market-wide read in one call.

Like ``scan_confluence`` this is a DETERMINISTIC STRUCTURAL grade — no AI, no
macro/DB inputs (see ``engines/confluence.py``). Use the ranking as a triage
list; the model interprets the top names.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from tools.confluence import grade_symbol

# Default watchlist — liquid Binance USDT perps/pairs. Override via the
# ``symbols`` argument.
DEFAULT_WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT",
]

# Liquid OANDA forex/metals pairs (need RF_OANDA_TOKEN). Underscore → OANDA.
FOREX_WATCHLIST = [
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "XAU_USD",
]

# Major stock indices via OANDA (CFDs). Same token as forex; underscore → OANDA.
INDEX_WATCHLIST = [
    "NAS100_USD", "SPX500_USD", "US30_USD", "DE30_EUR", "UK100_GBP",
]

# Preset keyword → watchlist. The whole ``symbols`` string (case-insensitive)
# can be one of these instead of explicit symbols.
_PRESETS = {
    "crypto": DEFAULT_WATCHLIST,
    "forex": FOREX_WATCHLIST,
    "fx": FOREX_WATCHLIST,
    "metals": FOREX_WATCHLIST,
    "indices": INDEX_WATCHLIST,
    "index": INDEX_WATCHLIST,
}

# Cap the fan-out so one call can't hammer Binance (each symbol = 2 fetches).
MAX_SYMBOLS = 15


def _parse_symbols(symbols: str) -> list[str]:
    """Parse a comma/space-separated symbol string into a clean upper list.

    Empty → the crypto default watchlist. A single preset keyword as the whole
    string ("forex"/"fx"/"metals"/"indices"/"index"/"crypto", case-insensitive)
    → the matching watchlist. Otherwise treat the string as explicit symbols.
    """
    if not symbols or not symbols.strip():
        return list(DEFAULT_WATCHLIST)
    preset = _PRESETS.get(symbols.strip().lower())
    if preset is not None:
        return list(preset)
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
    async def scan_market(
        symbols: str = "",
        only_actionable: bool = False,
    ) -> dict:
        """Scan a watchlist of crypto symbols and rank them by confluence score.

        Runs the structural confluence grade (1H + 4H SMC → 0–N score with a
        required aligned order block) on each symbol concurrently and returns
        them ranked best-first. Use it to triage the market: "where are the
        setups right now?"

        Same caveats as ``scan_confluence``: deterministic and structural, NO AI
        and NO macro/DB inputs — read it as a confluence checklist, not a signal.

        Args:
            symbols: Comma/space-separated symbols, e.g. ``"BTCUSDT, ETHUSDT,
                SOLUSDT"``. Empty → a default liquid crypto watchlist. Capped at
                15. Forex/metals (e.g. ``EUR_USD``, ``XAU_USD``) and stock
                indices (e.g. ``NAS100_USD``, ``SPX500_USD``) ARE supported when
                ``RF_OANDA_TOKEN`` is set (any underscore symbol routes to
                OANDA); crypto needs no key. You may also pass a single PRESET
                keyword as the whole string (case-insensitive): ``"crypto"``,
                ``"forex"``/``"fx"``, ``"metals"``, or ``"indices"``/``"index"``
                — these expand to curated watchlists (forex/metals/indices
                presets need ``RF_OANDA_TOKEN``). Symbols that fail are reported
                under ``errors``.
            only_actionable: When true, ``ranked`` includes only setups that meet
                the confluence ``min_score`` (the rest are summarized in
                ``filtered_out``).

        Returns:
            A dict with ``scanned`` (count), ``min_score``, ``actionable``
            (how many meet threshold), ``ranked`` (list of per-symbol grades —
            same fields as ``scan_confluence`` — sorted by score desc, then
            actionable, then |direction|), ``errors`` (symbols that failed, with
            why), and ``scored_at``. On a bad request, a dict with an ``error``.
        """
        wanted = _parse_symbols(symbols)
        if not wanted:
            return {"error": "No symbols to scan."}
        if len(wanted) > MAX_SYMBOLS:
            return {
                "error": (
                    f"Too many symbols ({len(wanted)}). Cap is {MAX_SYMBOLS} per "
                    "scan — narrow the list."
                )
            }

        # Grade every requested symbol. Crypto routes to Binance; forex/metals
        # route to OANDA. A forex symbol without a token surfaces its routing
        # error naturally via grade_symbol → the ``errors`` list below.
        errors: list[dict] = []
        to_grade: list[str] = list(wanted)

        results = await asyncio.gather(*(grade_symbol(s) for s in to_grade))

        ranked: list[dict] = []
        for sym, res in zip(to_grade, results):
            if "error" in res:
                errors.append({"symbol": sym, "error": res["error"]})
            else:
                ranked.append(res)

        # Best first: higher score, then those meeting threshold, then deeper
        # structure (counter-trend last as a mild tiebreak).
        ranked.sort(
            key=lambda r: (r["score"], r["meets_threshold"], not r["is_counter_trend"]),
            reverse=True,
        )

        actionable = sum(1 for r in ranked if r["meets_threshold"])
        min_score = ranked[0]["min_score"] if ranked else None

        filtered_out: list[dict] = []
        if only_actionable:
            keep = [r for r in ranked if r["meets_threshold"]]
            filtered_out = [
                {"symbol": r["symbol"], "score": r["score"], "direction": r["direction"]}
                for r in ranked if not r["meets_threshold"]
            ]
            ranked = keep

        out = {
            "scanned": len(to_grade),
            "min_score": min_score,
            "actionable": actionable,
            "ranked": ranked,
            "errors": errors,
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }
        if only_actionable:
            out["filtered_out"] = filtered_out
        return out
