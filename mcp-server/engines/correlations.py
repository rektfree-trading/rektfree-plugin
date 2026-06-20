"""
Pure-Python cross-asset correlation helpers (no exchange/DB/app imports).

Implements the standard, auditable math the ``get_correlations`` tool needs:
log returns, timestamp alignment across symbols, Pearson correlation, and a
strength/direction label. Everything here is plain stdlib math over lists of
floats / candle dicts so the math stays dependency-light and verifiable.

Mirrors the spirit of the backend's ``correlation_stats`` service (Pearson over
returns, 0.7/0.4 strength thresholds) but works purely on the keyless candle
dicts the plugin's Binance fetcher returns — no DB, no app imports.
"""

from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------

def log_returns(closes: list[float]) -> list[float]:
    """Natural-log returns ln(c[i] / c[i-1]); length = len(closes) - 1.

    Log returns are used (vs simple percent returns) because they're additive
    across time and symmetric — the standard input for a correlation of price
    movement. Non-positive prices are skipped defensively.
    """
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        cur = closes[i]
        if prev > 0 and cur > 0:
            out.append(math.log(cur / prev))
        else:
            out.append(0.0)
    return out


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------

def align_closes(
    series: dict[str, list[dict]],
) -> tuple[list[float], dict[str, list[float]]]:
    """Align candle series by timestamp and return matched closes per symbol.

    Takes ``{symbol: [candle dicts oldest→newest]}`` (each candle a dict with a
    ``time`` unix-second key and a float ``close``) and intersects the ``time``
    values across *all* symbols so every returned close corresponds to the same
    bar. Bars missing from any one symbol are dropped from all.

    Returns ``(times, {symbol: [close, ...]})`` where ``times`` is the sorted
    list of shared timestamps and each close list is the same length, aligned to
    ``times``. Returns ``([], {})`` if there's no common timestamp.
    """
    if not series:
        return [], {}

    # Intersection of timestamps present in every symbol.
    common: set[float] | None = None
    for candles in series.values():
        ts = {c["time"] for c in candles}
        common = ts if common is None else (common & ts)
    if not common:
        return [], {sym: [] for sym in series}

    times = sorted(common)
    aligned: dict[str, list[float]] = {}
    for sym, candles in series.items():
        by_time = {c["time"]: c["close"] for c in candles}
        aligned[sym] = [by_time[t] for t in times]
    return times, aligned


# ---------------------------------------------------------------------------
# Pearson correlation
# ---------------------------------------------------------------------------

def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient of two equal-length series (no numpy).

    r = cov(x, y) / (std_x * std_y) over sample statistics. Returns ``0.0`` when
    there are fewer than 3 points or either series is constant (zero variance,
    correlation undefined). The result is clamped to ``[-1, 1]`` to absorb any
    floating-point overshoot.
    """
    n = min(len(xs), len(ys))
    if n < 3:
        return 0.0
    xs = xs[:n]
    ys = ys[:n]
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    var_x = sum((x - mx) ** 2 for x in xs)
    var_y = sum((y - my) ** 2 for y in ys)
    if var_x <= 0.0 or var_y <= 0.0:
        return 0.0
    r = cov / math.sqrt(var_x * var_y)
    # Clamp against fp overshoot (e.g. 1.0000000002 on a perfect pair).
    return max(-1.0, min(1.0, r))


def correlation_matrix(returns: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    """Full symmetric Pearson matrix over a {symbol: returns} mapping.

    Diagonal is exactly ``1.0``; off-diagonals are symmetric (``m[a][b] ==
    m[b][a]``) and rounded to 4 dp. Assumes the return series are already
    aligned (same length / same bars).
    """
    syms = list(returns.keys())
    matrix: dict[str, dict[str, float]] = {s: {} for s in syms}
    for i, a in enumerate(syms):
        matrix[a][a] = 1.0
        for b in syms[i + 1:]:
            r = round(pearson(returns[a], returns[b]), 4)
            matrix[a][b] = r
            matrix[b][a] = r
    return matrix


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def strength(r: float) -> str:
    """Strength bucket for a correlation magnitude: strong/moderate/weak.

    |r| > 0.7 → strong, 0.4–0.7 → moderate, < 0.4 → weak. Sign is reported
    separately via :func:`direction`.
    """
    a = abs(r)
    if a > 0.7:
        return "strong"
    if a >= 0.4:
        return "moderate"
    return "weak"


def direction(r: float) -> str:
    """Sign of the relationship: same / opposite / none (near-zero)."""
    if r >= 0.1:
        return "same"
    if r <= -0.1:
        return "opposite"
    return "none"


def shift_label(recent_r: float, older_r: float, eps: float = 0.15) -> str:
    """Classify the recent-vs-older correlation move: tightening/decoupling/stable.

    Compares correlation over the most recent half of the window against the
    older half. A rise of more than ``eps`` = "tightening" (moving more in
    lockstep — risk-on/everything-follows-BTC); a fall of more than ``eps`` =
    "decoupling" (the symbol is going its own way); otherwise "stable".
    """
    delta = recent_r - older_r
    if delta > eps:
        return "tightening"
    if delta < -eps:
        return "decoupling"
    return "stable"
