"""
Pure R-multiple trade simulation + equity-curve statistics (stdlib only).

This is the math layer behind ``tools/backtest_rr`` — a deterministic, first-touch
trade simulator and the aggregate statistics it feeds. It is intentionally free of
any data fetching, MCP, or AI: every function is a plain pure function over candle
lists and numbers, so the tool layer (and the tests) can drive it directly.

A "candle" is the same dict the fetcher returns:
``{time, open, high, low, close, volume}`` (floats; ``time`` is unix seconds).

Model (kept deliberately simple and conservative):

- ATR is a simple mean of true ranges over ``period`` candles (same definition as
  ``engines.volatility.atr_simple`` — re-derived here to keep this module
  standalone-pure).
- A trade enters at ``entry`` price in ``direction`` (``long``/``short``). The stop
  sits ``stop_distance`` away against the trade; the target sits ``target_r ×
  stop_distance`` in favour. We then WALK FORWARD candle-by-candle and record the
  FIRST touch:
    * stop hit  → realised ``-1R``
    * target hit → realised ``+target_r R``
    * if a single candle's range spans BOTH, we assume the STOP filled first
      (conservative — intrabar path is unknown).
  If neither is touched within ``max_hold_bars``, we exit at the last walked
  candle's close and book the fractional R = realised move / stop_distance.
"""

from __future__ import annotations

from datetime import datetime, timezone

LONG = "long"
SHORT = "short"


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def true_ranges(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    """True-range series. TR[0] = high-low; TR[i] uses the prior close."""
    n = len(highs)
    if n == 0:
        return []
    trs = [highs[0] - lows[0]]
    for i in range(1, n):
        prev_close = closes[i - 1]
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - prev_close),
            abs(lows[i] - prev_close),
        )
        trs.append(tr)
    return trs


def atr_at(candles: list[dict], end_idx: int, period: int) -> float:
    """Simple-mean ATR measured over the ``period`` candles ENDING at ``end_idx``.

    Uses candles ``[end_idx-period+1 .. end_idx]`` inclusive. Falls back to as many
    candles as are available when fewer than ``period`` precede ``end_idx``.
    Returns ``0.0`` if there is nothing to measure.
    """
    period = max(1, int(period))
    start = max(0, end_idx - period + 1)
    window = candles[start : end_idx + 1]
    if not window:
        return 0.0
    highs = [c["high"] for c in window]
    lows = [c["low"] for c in window]
    closes = [c["close"] for c in window]
    trs = true_ranges(highs, lows, closes)
    return sum(trs) / len(trs) if trs else 0.0


# ---------------------------------------------------------------------------
# Single-trade first-touch simulation
# ---------------------------------------------------------------------------

def simulate_trade(
    candles: list[dict],
    entry_idx: int,
    direction: str,
    entry: float,
    stop_distance: float,
    target_r: float,
    max_hold_bars: int,
) -> dict | None:
    """Simulate one first-touch trade walking forward from ``entry_idx + 1``.

    The entry candle itself is NOT used for stop/target evaluation — we only walk
    the candles AFTER it (the signal is "known" at the close of ``entry_idx``).

    Args:
        candles: full oldest→newest candle list.
        entry_idx: index of the signal/entry candle.
        direction: ``"long"`` or ``"short"``.
        entry: entry price.
        stop_distance: positive price distance from entry to the stop.
        target_r: reward multiple; target sits ``target_r × stop_distance`` away.
        max_hold_bars: max forward candles to walk before a time-based exit.

    Returns:
        A dict ``{r, exit_reason, bars_held, exit_price}`` where ``r`` is the
        realised R-multiple, or ``None`` if the trade is unusable (no forward
        candles, non-positive stop distance, or a degenerate direction).
    """
    if stop_distance <= 0:
        return None
    if direction not in (LONG, SHORT):
        return None
    n = len(candles)
    first = entry_idx + 1
    if first >= n:
        return None  # no forward candles to simulate

    last = min(n - 1, entry_idx + int(max_hold_bars))
    if last < first:
        return None

    if direction == LONG:
        stop = entry - stop_distance
        target = entry + target_r * stop_distance
    else:
        stop = entry + stop_distance
        target = entry - target_r * stop_distance

    for i in range(first, last + 1):
        c = candles[i]
        hi = c["high"]
        lo = c["low"]
        if direction == LONG:
            hit_stop = lo <= stop
            hit_target = hi >= target
        else:
            hit_stop = hi >= stop
            hit_target = lo <= target

        if hit_stop and hit_target:
            # Ambiguous bar — assume the stop filled first (conservative).
            return {
                "r": -1.0,
                "exit_reason": "stop_ambiguous",
                "bars_held": i - entry_idx,
                "exit_price": stop,
            }
        if hit_stop:
            return {
                "r": -1.0,
                "exit_reason": "stop",
                "bars_held": i - entry_idx,
                "exit_price": stop,
            }
        if hit_target:
            return {
                "r": float(target_r),
                "exit_reason": "target",
                "bars_held": i - entry_idx,
                "exit_price": target,
            }

    # Neither hit within the hold window → time exit at the last candle's close.
    exit_price = candles[last]["close"]
    if direction == LONG:
        move = exit_price - entry
    else:
        move = entry - exit_price
    r = move / stop_distance
    return {
        "r": r,
        "exit_reason": "time",
        "bars_held": last - entry_idx,
        "exit_price": exit_price,
    }


# ---------------------------------------------------------------------------
# Aggregate equity-curve statistics
# ---------------------------------------------------------------------------

def equity_curve(r_multiples: list[float]) -> list[float]:
    """Cumulative-R equity curve (running sum of per-trade R)."""
    curve: list[float] = []
    cum = 0.0
    for r in r_multiples:
        cum += r
        curve.append(cum)
    return curve


def max_drawdown_r(curve: list[float]) -> float:
    """Maximum drawdown (in R) on a cumulative-R equity curve.

    Returns a non-negative number: the largest peak→trough decline. The curve is
    treated as starting from 0, so an immediately-negative curve still reports a
    drawdown from the 0 baseline.
    """
    peak = 0.0
    max_dd = 0.0
    for v in curve:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
    return max_dd


def aggregate_stats(r_multiples: list[float]) -> dict:
    """Aggregate a list of per-trade R-multiples into summary statistics.

    Returns a dict with: ``trades``, ``wins``, ``losses``, ``win_rate`` (0–100),
    ``avg_win_R``, ``avg_loss_R`` (negative), ``expectancy_R`` (mean R/trade),
    ``profit_factor`` (gross win R / gross loss R; ``None`` when there are no
    losses), ``total_R``, ``max_drawdown_R``, and the ``equity_curve``.

    A trade with R > 0 is a win, R < 0 a loss; exactly-0 R counts as neither for
    win-rate but still contributes 0 to totals/expectancy.
    """
    n = len(r_multiples)
    if n == 0:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "avg_win_R": 0.0,
            "avg_loss_R": 0.0,
            "expectancy_R": 0.0,
            "profit_factor": None,
            "total_R": 0.0,
            "max_drawdown_R": 0.0,
            "equity_curve": [],
        }

    wins = [r for r in r_multiples if r > 0]
    losses = [r for r in r_multiples if r < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)  # positive magnitude
    total_r = sum(r_multiples)
    curve = equity_curve(r_multiples)

    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None

    return {
        "trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n * 100, 2),
        "avg_win_R": round(gross_win / len(wins), 4) if wins else 0.0,
        "avg_loss_R": round(sum(losses) / len(losses), 4) if losses else 0.0,
        "expectancy_R": round(total_r / n, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor is not None else None,
        "total_R": round(total_r, 4),
        "max_drawdown_R": round(max_drawdown_r(curve), 4),
        "equity_curve": [round(v, 4) for v in curve],
    }


def downsample(points: list[float], cap: int) -> list[float]:
    """Evenly downsample ``points`` to at most ``cap`` values (endpoints kept).

    Used to bound the returned equity-curve length without dropping the final
    cumulative-R value. Returns the list unchanged when it already fits.
    """
    cap = max(2, int(cap))
    n = len(points)
    if n <= cap:
        return list(points)
    step = (n - 1) / (cap - 1)
    out = [points[round(i * step)] for i in range(cap)]
    out[-1] = points[-1]  # always preserve the final equity value
    return out


def confidence(n: int) -> str:
    """Sample-size confidence bucket (same thresholds as the frequency backtest)."""
    if n >= 50:
        return "HIGH"
    if n >= 20:
        return "MEDIUM"
    if n >= 5:
        return "LOW"
    return "INSUFFICIENT"


# ---------------------------------------------------------------------------
# Entry-candle resolution for session-family events
# ---------------------------------------------------------------------------

# Session UTC hour windows — must match engines.session_stats.SESSIONS.
_SESSION_HOURS = {
    "asia": (0, 8),
    "london": (8, 13),
    "new_york": (13, 21),
}


def _candle_dt(c: dict) -> datetime:
    return datetime.fromtimestamp(c["time"], tz=timezone.utc)


def resolve_entry_index(candles: list[dict], event: dict) -> int | None:
    """Map a session-family event to its entry candle index in ``candles``.

    Session-family events (``session_range``/``asia_sweep``/``london_sweep``/
    ``ny_continuation``/``power_of_3``) carry a ``date`` (``YYYY-MM-DD``) and a
    governing session, but NOT a candle index. We define the entry as the LAST
    candle of the signal's confirming session on that date (the bar at which the
    direction is known), so the simulation walks the bars AFTER it.

    The confirming session per event_type:
        * session_range  → its own ``session``
        * asia_sweep     → london (the session that did the sweeping)
        * london_sweep   → new_york
        * ny_continuation→ new_york
        * power_of_3     → new_york (distribution leg), falling back to london

    Returns the candle index, or ``None`` if the date/session window has no
    candles in ``candles`` (so the event is skipped).
    """
    date_str = event.get("date")
    if not date_str:
        return None
    et = event.get("event_type")
    sess = _confirming_session(et, event)
    if sess is None:
        return None
    start_h, end_h = _SESSION_HOURS[sess]

    best_idx: int | None = None
    for i, c in enumerate(candles):
        dt = _candle_dt(c)
        if dt.strftime("%Y-%m-%d") != date_str:
            continue
        if start_h <= dt.hour < end_h:
            best_idx = i  # keep advancing → ends on the last in-window candle
    return best_idx


def _confirming_session(event_type: str, event: dict) -> str | None:
    if event_type == "session_range":
        s = event.get("session")
        return s if s in _SESSION_HOURS else None
    if event_type == "asia_sweep":
        return "london"
    if event_type in ("london_sweep", "ny_continuation", "power_of_3"):
        return "new_york"
    return None
