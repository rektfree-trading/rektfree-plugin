"""
``scan_confluence`` — structural confluence scoring tool (crypto, keyless).

Fetches Binance 1H + 4H OHLCV, runs the vendored SMC engine on each timeframe,
and grades the setup with the pure confluence scorer (a faithful re-implement
of the backend scanner's 0–N math). Returns the numeric score + factor
breakdown + structural target/invalidation as JSON for the model to interpret.

This is a DETERMINISTIC STRUCTURAL GRADE — NOT the hosted scanner's full
signal. There is NO AI here, and the backend's DB-backed inputs (macro
calendar, avoid-signatures, historical sweep-rate, order-flow delta,
derivatives, daily SMC) are NEUTRALIZED. See ``engines/confluence.py`` for the
exact neutralization per input. Use the score + factors as a confluence
checklist, not a black-box buy signal.
"""

from __future__ import annotations

from datetime import datetime, timezone

from data import binance
from engines import confluence as confluence_engine
from engines import smart_money
from tools._common import crypto_only_error


async def grade_symbol(symbol: str) -> dict:
    """Score one crypto symbol's confluence and return the grade payload.

    Shared by the ``scan_confluence`` tool (single symbol) and ``scan_market``
    (watchlist), so both use identical fetch + SMC + scoring logic. Returns the
    grade dict on success, or ``{"error": ...}`` on a forex symbol, fetch
    failure, or insufficient data.
    """
    if err := crypto_only_error(symbol):
        return err

    # 1H drives the entry/structure; 4H gives the higher-timeframe bias.
    # 300 candles each: ~12.5 days on 1H and ~50 days on 4H — enough for
    # stable swings, ATR, and a recent TPO session. Mirrors the backend's
    # 1H+4H scan inputs (it fetches 200×1H / 100×4H; we fetch more for
    # steadier structure since we have no DB-cached history to fall back on).
    try:
        candles_1h = await binance.fetch_candles(symbol, "1h", 300)
        candles_4h = await binance.fetch_candles(symbol, "4h", 300)
    except binance.BinanceError as exc:
        return {"error": str(exc)}

    if not candles_1h or len(candles_1h) < 50:
        return {
            "error": (
                f"Not enough 1H candle data for {symbol} "
                f"(got {len(candles_1h)}, need ≥50)."
            )
        }

    # ── 1H SMC (swing_length=20, matches scan_symbol + tools/smc.py 1h) ──
    smc_1h = smart_money.analyze(
        [c["open"] for c in candles_1h],
        [c["high"] for c in candles_1h],
        [c["low"] for c in candles_1h],
        [c["close"] for c in candles_1h],
        [c["time"] for c in candles_1h],
        swing_length=20,
        internal_length=5,
        eql_threshold=0.15,
        eql_length=5,
    )

    # ── 4H SMC (swing_length=10, matches scan_symbol's HTF pass) ──
    smc_4h = None
    if candles_4h and len(candles_4h) >= 30:
        smc_4h = smart_money.analyze(
            [c["open"] for c in candles_4h],
            [c["high"] for c in candles_4h],
            [c["low"] for c in candles_4h],
            [c["close"] for c in candles_4h],
            [c["time"] for c in candles_4h],
            swing_length=10,
            internal_length=5,
            eql_threshold=0.15,
            eql_length=3,
        )

    current_price = candles_1h[-1]["close"]
    now = datetime.now(timezone.utc)

    grade = confluence_engine.score_setup(
        smc_1h=smc_1h,
        smc_4h=smc_4h,
        candles_1h=candles_1h,
        candles_4h=candles_4h,
        current_price=current_price,
        now_utc=now,
    )

    return {
        "symbol": symbol.upper(),
        "last_price": current_price,
        "score": grade["score"],
        "min_score": grade["min_score"],
        "meets_threshold": grade["meets_threshold"],
        "direction": grade["direction"],
        "is_counter_trend": grade["is_counter_trend"],
        "factors": grade["factors"],
        "target": grade["target"],
        "invalidation": grade["invalidation"],
        "scored_at": now.isoformat(),
    }


def register(mcp) -> None:
    @mcp.tool()
    async def scan_confluence(symbol: str = "BTCUSDT") -> dict:
        """Grade a crypto setup with a 0–N Smart Money confluence score.

        Fetches 1H and 4H candles from Binance (public, no API key needed),
        runs the full SMC engine on each (BOS/CHoCH, order blocks, FVGs, equal
        levels, liquidity sweeps, premium/discount), then stacks the signals
        into a single confluence score using the same point weights as the
        hosted RektFree scanner. Returns structured JSON for the model to turn
        into a go/no-go read.

        Scoring is structural and deterministic — an order block aligned with
        price near the trade direction is REQUIRED (no OB ⇒ score 0). Bonuses
        come from FVG overlap, OTE retracement, liquidity sweeps, draw-on-
        liquidity, premium/discount positioning, multi-timeframe alignment, and
        TPO (POC/VAH/VAL) confluence. ``min_score`` is the hosted operating
        threshold; counter-trend setups must clear a higher bar.

        IMPORTANT: This tool runs NO AI and has NO macro/DB inputs. The hosted
        scanner additionally weighs a macro calendar, avoid-signatures,
        historical sweep-rate, order-flow delta, derivatives, and a daily SMC
        pass — all of which are NEUTRALIZED here (macro treated as "no event").
        So this is a clean structural confluence grade, not the full hosted
        signal. Read the factors as a checklist; the model supplies the
        narrative and risk read.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex pairs (with ``_``) are not
                supported in this slice.

        Returns:
            A dict with ``symbol``, ``last_price``, ``score``, ``min_score``,
            ``meets_threshold`` (bool), ``direction`` (``long``/``short``),
            ``is_counter_trend`` (bool), ``factors`` (list of factor labels —
            same vocabulary as the hosted scanner; killzone/silver-bullet
            entries are listed but carry 0 weight after recalibration),
            ``target`` and ``invalidation`` (structural price levels), and
            ``scored_at`` (UTC ISO timestamp). On failure, a dict with an
            ``error`` key.
        """
        return await grade_symbol(symbol)
