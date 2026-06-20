"""
Pure-Python volatility & range calculators (no exchange/DB/app imports).

Implements the standard, well-documented formulas the ``get_volatility`` tool
needs: True Range / ATR, Average Daily Range, realized (log-return) volatility,
and Bollinger Band width with a squeeze read. Everything here is plain stdlib
math/statistics over lists of floats so the tool stays dependency-light and the
math is auditable. All functions are side-effect free.
"""

from __future__ import annotations

import math
import statistics


# ---------------------------------------------------------------------------
# True Range / ATR
# ---------------------------------------------------------------------------

def true_ranges(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    """Per-candle True Range series, aligned to candles[1:].

    True Range = max(
        high - low,
        |high - prev_close|,
        |low  - prev_close|,
    )

    The first candle has no previous close, so the returned list has one fewer
    element than the inputs (it corresponds to ``candles[1:]``).
    """
    trs: list[float] = []
    for i in range(1, len(closes)):
        prev_close = closes[i - 1]
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - prev_close)
        lc = abs(lows[i] - prev_close)
        trs.append(max(hl, hc, lc))
    return trs


def atr_simple(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    """ATR as a *simple* mean of the last ``period`` True Ranges.

    We use the simple (SMA) variant rather than Wilder's smoothing — it's the
    most transparent and, over a short recent window, tracks Wilder closely.
    The tool reports ``method: "simple"`` so the choice is explicit. Returns
    ``0.0`` if there aren't enough candles to form ``period`` true ranges.
    """
    trs = true_ranges(highs, lows, closes)
    if len(trs) < period or period <= 0:
        return 0.0
    return sum(trs[-period:]) / period


# ---------------------------------------------------------------------------
# Realized volatility (log returns)
# ---------------------------------------------------------------------------

# Periods per year by Binance interval — used to annualize realized vol. Crypto
# trades 24/7/365, so these are full-calendar counts (no 252-trading-day haircut).
PERIODS_PER_YEAR: dict[str, float] = {
    "1m": 365 * 24 * 60,
    "5m": 365 * 24 * 12,
    "15m": 365 * 24 * 4,
    "1h": 365 * 24,
    "4h": 365 * 6,
    "1d": 365,
    "1w": 52,
}


def log_returns(closes: list[float]) -> list[float]:
    """Natural-log returns ln(c[i] / c[i-1]); length = len(closes) - 1."""
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev > 0 and closes[i] > 0:
            out.append(math.log(closes[i] / prev))
    return out


def realized_vol(closes: list[float], window: int, interval: str) -> tuple[float, float]:
    """Annualized realized volatility over the last ``window`` log returns.

    Computes the sample stdev of per-period log returns, then scales by
    ``sqrt(periods_per_year)`` for the given interval to annualize.

    Returns ``(annualized_pct, annualization_factor)``. The annualization factor
    is ``sqrt(periods_per_year)`` so the caller can report it. Returns
    ``(0.0, factor)`` if there aren't at least 2 returns in the window.
    """
    ppy = PERIODS_PER_YEAR.get(interval, 365 * 24)
    factor = math.sqrt(ppy)
    rets = log_returns(closes)
    if len(rets) < 2:
        return 0.0, factor
    sample = rets[-window:] if len(rets) >= window else rets
    if len(sample) < 2:
        return 0.0, factor
    sigma = statistics.stdev(sample)  # per-period stdev of log returns
    return sigma * factor * 100.0, factor


# ---------------------------------------------------------------------------
# Bollinger Band width
# ---------------------------------------------------------------------------

def bbw_series(closes: list[float], period: int = 20, mult: float = 2.0) -> list[float]:
    """Rolling Bollinger Band width series.

    For each window of ``period`` closes: mid = SMA, band = mult * (population
    stdev), width = (upper - lower) / mid = 2*mult*stdev / mid. The returned
    series is aligned to ``closes[period-1:]`` (one width per completed window).
    """
    out: list[float] = []
    if len(closes) < period or period <= 0:
        return out
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        mid = sum(window) / period
        if mid <= 0:
            continue
        sd = statistics.pstdev(window)  # population stdev over the window
        upper = mid + mult * sd
        lower = mid - mult * sd
        out.append((upper - lower) / mid)
    return out


def bbw_squeeze(widths: list[float], lookback: int = 100, squeeze_pct: float = 0.25) -> tuple[float, float, bool]:
    """Classify the current BBW against its own recent range.

    Computes where the latest width sits within the last ``lookback`` widths as a
    percentile (0 = tightest in the window, 1 = widest). A squeeze is flagged when
    that percentile is at or below ``squeeze_pct`` (default bottom 25% =
    compression, expansion likely).

    Returns ``(current_width, percentile, is_squeeze)``. Returns
    ``(current, 0.0, False)`` if there's only one width.
    """
    if not widths:
        return 0.0, 0.0, False
    current = widths[-1]
    window = widths[-lookback:] if len(widths) >= lookback else widths
    if len(window) < 2:
        return current, 0.0, False
    # Percentile rank of current width within the window (fraction at or below it).
    below = sum(1 for w in window if w <= current)
    percentile = below / len(window)
    return current, percentile, percentile <= squeeze_pct
