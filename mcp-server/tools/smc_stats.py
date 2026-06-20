"""
``compute_smc_stats`` — on-the-fly SMC hit-rate statistics (crypto, keyless).

Fetches deep 1H Binance history, slides the SMC engine across it, scores every
detected structure against the candles that followed, and aggregates the hit
rates in Python — mirroring the hosted product's ``/stats/smc/summary``
endpoint, but with NO database.

The hosted product persists per-structure outcomes and aggregates over the
full candle history; this tool runs the same evaluation over the last ~5000
1H candles (~7 months) in memory. So the numbers approximate the hosted ones
but will differ — and any rate with a small sample size ``n`` is noisy.
"""

from __future__ import annotations

from engines import smc_stats as smc_engine
from data import binance
from tools._common import crypto_only_error

# How much 1H history to pull. ~5000 1H candles ≈ 208 days — a deeper window
# for tighter hit-rate samples. Paged because a single Binance klines request
# caps at 1000.
_TOTAL_CANDLES = 5000
_MAX_PAGES = 12


def _rate(num: int, den: int) -> float:
    """Percentage (0–100, one decimal), 0.0 when the denominator is empty."""
    return round(num / den * 100, 1) if den else 0.0


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _agg_ob(events: list[dict]) -> dict:
    """OB retest/hold aggregation — mirrors router /summary 'order_blocks'."""
    n = len(events)
    retested = sum(1 for e in events if e["retested"])
    held = sum(1 for e in events if e["held"])
    retest_candles = [e["retested_within"] for e in events if e["retested"]]
    return {
        "n": n,
        "retest_rate": _rate(retested, n),
        "hold_rate": _rate(held, n),
        "hold_rate_when_retested": _rate(held, retested),
        "avg_retest_candles": round(_avg(retest_candles), 1),
        "bullish": sum(1 for e in events if e["ob_bias"] == "bullish"),
        "bearish": sum(1 for e in events if e["ob_bias"] == "bearish"),
    }


def _agg_fvg(events: list[dict]) -> dict:
    """FVG fill aggregation — mirrors router /summary 'fair_value_gaps'."""
    n = len(events)
    filled = sum(1 for e in events if e["filled"])
    fill_candles = [e["filled_within"] for e in events if e["filled"]]
    return {
        "n": n,
        "fill_rate": _rate(filled, n),
        "avg_fill_candles": round(_avg(fill_candles), 1),
        "avg_fill_pct": round(_avg([e["filled_pct"] for e in events]), 1),
        "bullish": sum(1 for e in events if e["fvg_bias"] == "bullish"),
        "bearish": sum(1 for e in events if e["fvg_bias"] == "bearish"),
    }


def _agg_bos(events: list[dict]) -> dict:
    """BOS continuation aggregation — mirrors router /summary 'bos'."""
    n = len(events)
    continued = sum(1 for e in events if e["continuation"])
    return {
        "n": n,
        "continuation_rate": _rate(continued, n),
        "avg_max_move_pct": round(_avg([e["max_move_pct"] for e in events]), 4),
        "bullish": sum(1 for e in events if e["bos_bias"] == "bullish"),
        "bearish": sum(1 for e in events if e["bos_bias"] == "bearish"),
    }


def _agg_choch(events: list[dict]) -> dict:
    """CHoCH reversal aggregation — mirrors router /summary 'choch'."""
    n = len(events)
    reversed_ = sum(1 for e in events if e["reversed"])
    return {
        "n": n,
        "reversal_rate": _rate(reversed_, n),
        "avg_max_move_pct": round(_avg([e["max_move_pct"] for e in events]), 4),
        "bullish": sum(1 for e in events if e["choch_bias"] == "bullish"),
        "bearish": sum(1 for e in events if e["choch_bias"] == "bearish"),
    }


def _agg_eq(events: list[dict]) -> dict:
    """EQH/EQL sweep+reversal aggregation — mirrors router /summary 'equal_levels'."""
    n = len(events)
    swept = sum(1 for e in events if e["swept"])
    reversed_ = sum(1 for e in events if e["reversed"])
    return {
        "n": n,
        "sweep_rate": _rate(swept, n),
        "reversal_rate": _rate(reversed_, n),
        "reversal_rate_when_swept": _rate(reversed_, swept),
        "avg_reversal_pct": round(_avg([e["reversal_pct"] for e in events]), 4),
        "eqh": sum(1 for e in events if e["eq_type"] == "EQH"),
        "eql": sum(1 for e in events if e["eq_type"] == "EQL"),
    }


def _agg_sweep(events: list[dict]) -> dict:
    """Liquidity-sweep success aggregation — mirrors router /summary 'liquidity_sweeps'."""
    n = len(events)
    success = sum(1 for e in events if e["success"])
    return {
        "n": n,
        "success_rate": _rate(success, n),
        "avg_max_move_pct": round(_avg([e["max_move_pct"] for e in events]), 4),
        "wick": sum(1 for e in events if e["sweep_type"] == "WICK"),
        "retest": sum(1 for e in events if e["sweep_type"] == "RETEST"),
    }


def register(mcp) -> None:
    @mcp.tool()
    async def compute_smc_stats(symbol: str = "BTCUSDT") -> dict:
        """Compute empirical SMC hit-rate statistics for a crypto symbol.

        Fetches deep 1H history from Binance (public, no API key), slides the
        full SMC engine across it (200-candle windows, step 50), then scores
        every detected structure against the candles that followed — exactly
        the evaluation the hosted product runs. Returns the aggregated hit
        rates for the model to interpret:

        - **ob_test** — order-block retest rate, hold rate, and hold-when-
          retested rate (did price respect the zone?).
        - **fvg_test** — fair-value-gap fill rate and average fill percentage.
        - **bos_test** — break-of-structure continuation rate (price ran 0.3%+
          in the break direction).
        - **choch_test** — change-of-character reversal rate (price reversed
          0.5%+ in the new direction).
        - **eq_test** — equal-high/low sweep rate and post-sweep reversal rate.
        - **sweep_test** — liquidity-sweep success rate (1%+ move after the
          grab).

        Every block carries a sample size ``n`` (and ``bullish``/``bearish`` or
        type splits) so the model can weight confidence — a 70% rate from n=4
        is noise, the same rate from n=120 is signal.

        IMPORTANT: these rates come from roughly the last ~5000 1H candles
        (~7 months). The hosted product aggregates over *full* history, so
        numbers here will differ from app.rektfree.com. Treat any small-n rate
        as noisy.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex pairs (with ``_``) are not
                supported in this slice.

        Returns:
            A dict with ``symbol``, ``window`` (``{candles, from, to}`` — the
            UTC date range the stats cover), and the six hit-rate blocks
            (``ob_test``, ``fvg_test``, ``bos_test``, ``choch_test``,
            ``eq_test``, ``sweep_test``), each with rates (0–100%) plus a
            sample size ``n``. On failure, a dict with an ``error`` key.
        """
        if err := crypto_only_error(symbol):
            return err

        try:
            candles = await binance.fetch_candles_paged(
                symbol, "1h", total=_TOTAL_CANDLES, max_pages=_MAX_PAGES
            )
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not candles:
            return {"error": f"No candle data returned for {symbol}."}

        if len(candles) < smc_engine.MIN_CANDLES:
            return {
                "error": (
                    f"Only {len(candles)} 1H candles available for "
                    f"{symbol.upper()} — need at least {smc_engine.MIN_CANDLES} "
                    "to slide the SMC window and score outcomes. Statistics "
                    "would be too sparse to be meaningful."
                )
            }

        outcomes = smc_engine.evaluate_smc_outcomes(candles)

        first_date = smc_engine._ts_to_date(candles[0]["time"]).isoformat()
        last_date = smc_engine._ts_to_date(candles[-1]["time"]).isoformat()

        return {
            "symbol": symbol.upper(),
            "window": {
                "candles": len(candles),
                "timeframe": "1h",
                "from": first_date,
                "to": last_date,
            },
            "ob_test": _agg_ob(outcomes["ob_test"]),
            "fvg_test": _agg_fvg(outcomes["fvg_test"]),
            "bos_test": _agg_bos(outcomes["bos_test"]),
            "choch_test": _agg_choch(outcomes["choch_test"]),
            "eq_test": _agg_eq(outcomes["eq_test"]),
            "sweep_test": _agg_sweep(outcomes["sweep_test"]),
        }
