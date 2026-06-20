"""
Daily Bias service — implements TTrades Daily Bias logic.

Computes daily (and weekly) bias based on the relationship between the current
period's OHLC and the previous period's high/low. Also tracks whether the
previous period's high/low was "raided" (reached) during the current period.

Bias rules (per new period):
  1. Close above PH  → bullish (bias toward PH)
  2. Close below PL  → bearish (bias toward PL)
  3. Wicked above PH but closed below, low above PL → failed close above → bearish
  4. Wicked below PL but closed above, high below PH → failed close below → bullish
  5. Stayed inside (high ≤ PH and low ≥ PL) → use previous candle direction
  6. Outside bar but closed inside → no bias

Returns per-day (or per-week) bias entries with:
  - bias direction (+1 bullish, -1 bearish, 0 neutral)
  - bias reason (human-readable)
  - previous period high/low levels
  - whether PDH/PDL (or PWH/PWL) was hit during the period
  - cumulative statistics (success rate, close-through rate)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass
class BiasEntry:
    """A single period's bias determination."""
    timestamp: float          # start of the new period (Unix)
    bias: int                 # +1 bullish, -1 bearish, 0 neutral
    reason: str               # human-readable explanation
    prev_high: float          # previous period high
    prev_low: float           # previous period low
    hit_prev_high: bool = False   # PDH/PWH reached during this period
    hit_prev_low: bool = False    # PDL/PWL reached during this period
    close_through_high: bool = False  # closed through PDH
    close_through_low: bool = False   # closed through PDL


@dataclass
class BiasStats:
    """Cumulative bias statistics."""
    bias_ph_count: int = 0     # times bias was bullish
    bias_pl_count: int = 0     # times bias was bearish
    hit_ph_count: int = 0      # times PDH was reached when bias was bullish
    hit_pl_count: int = 0      # times PDL was reached when bias was bearish
    close_ph_count: int = 0    # times price closed through PDH after hitting it
    close_pl_count: int = 0    # times price closed through PDL after hitting it


@dataclass
class BiasResult:
    """Full bias analysis result for a timeframe."""
    entries: list[BiasEntry] = field(default_factory=list)
    stats: BiasStats = field(default_factory=BiasStats)
    current_bias: int = 0
    current_reason: str = ""
    current_prev_high: float = 0.0
    current_prev_low: float = 0.0


def _get_day_key(ts: float) -> str:
    """Get YYYY-MM-DD from a Unix timestamp."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def _get_week_key(ts: float) -> str:
    """Get ISO week key from a Unix timestamp."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def compute_daily_bias(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    times: list[float],
    period: Literal["D", "W"] = "D",
) -> BiasResult:
    """Compute daily or weekly bias from candle data.

    Accepts candle arrays at any timeframe (typically 1H or lower).
    Groups candles into daily or weekly periods, then applies TTrades
    bias logic at each period boundary.
    """
    if len(opens) < 2:
        return BiasResult()

    key_fn = _get_day_key if period == "D" else _get_week_key

    # Group candles into periods
    periods: list[dict] = []
    current_key = None
    current_period = None

    for i in range(len(opens)):
        k = key_fn(times[i])
        if k != current_key:
            if current_period is not None:
                periods.append(current_period)
            current_key = k
            current_period = {
                "key": k,
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "start_time": times[i],
                "end_time": times[i],
            }
        else:
            current_period["high"] = max(current_period["high"], highs[i])
            current_period["low"] = min(current_period["low"], lows[i])
            current_period["close"] = closes[i]
            current_period["end_time"] = times[i]

    if current_period is not None:
        periods.append(current_period)

    if len(periods) < 2:
        return BiasResult()

    result = BiasResult()
    stats = result.stats
    prev_up = True  # previous period closed above open

    for idx in range(1, len(periods)):
        prev = periods[idx - 1]
        curr = periods[idx]

        ph = prev["high"]   # previous high
        pl = prev["low"]    # previous low
        prev_close = prev["close"]
        ch = curr["high"]   # current high
        cl = curr["low"]    # current low

        bias = 0
        reason = ""

        label = "D" if period == "D" else "W"

        if prev_close > ph:
            # Previous period closed above its own high... shouldn't happen in
            # normal cases, but if aggregated from sub-candles the last close
            # IS the period close. We compare prev close to the period before prev.
            # Actually, the Pine logic compares close[1] (yesterday's close) to
            # n.ph (the day-before-yesterday's high). We need to look back further.
            pass
        if prev_close < pl:
            pass

        # TTrades logic: at new period boundary, compare PREVIOUS period's
        # close and OHLC against the period-before-previous H/L
        if idx < 2:
            # Not enough history for 2-period lookback, use direction heuristic
            prev_up = prev["close"] >= prev["open"]
            continue

        pp = periods[idx - 2]  # period before previous
        pp_h = pp["high"]      # e.g. PDH (day before yesterday's high)
        pp_l = pp["low"]       # e.g. PDL

        # Previous period's OHLC relative to period-before-previous H/L
        p_close = prev["close"]
        p_high = prev["high"]
        p_low = prev["low"]

        if p_close > pp_h:
            # Closed above previous-period high → bullish
            bias = 1
            reason = f"Close Above P{label}H"
        elif p_close < pp_l:
            # Closed below previous-period low → bearish
            bias = -1
            reason = f"Close Below P{label}L"
        elif p_close < pp_h and p_close > pp_l and p_high > pp_h and p_low > pp_l:
            # Wicked above PH but failed to close above → bearish
            bias = -1
            reason = f"Failed to Close Above P{label}H"
        elif p_close > pp_l and p_close < pp_h and p_high < pp_h and p_low < pp_l:
            # Wicked below PL but failed to close below → bullish
            bias = 1
            reason = f"Failed to Close Below P{label}L"
        elif p_high <= pp_h and p_low >= pp_l:
            # Stayed inside range → use previous direction
            bias = 1 if prev_up else -1
            reason = f"Close Inside — Bias P{label}{'H' if bias == 1 else 'L'}"
        else:
            # Outside bar but closed inside
            bias = 0
            reason = "Outside Bar Closed Inside — No Bias"

        # Track close-through: if bias was bullish last time and we closed above PH
        # (handled via stats at next iteration)
        # For now, track stats
        if bias == 1:
            stats.bias_ph_count += 1
        elif bias == -1:
            stats.bias_pl_count += 1

        # Check if previous period high/low was hit during current period
        hit_high = ch >= pp_h
        hit_low = cl <= pp_l

        if hit_high and bias == 1:
            stats.hit_ph_count += 1
        if hit_low and bias == -1:
            stats.hit_pl_count += 1

        # Check close-through
        close_through_high = curr["close"] > pp_h if hit_high else False
        close_through_low = curr["close"] < pp_l if hit_low else False

        if close_through_high and bias == 1:
            stats.close_ph_count += 1
        if close_through_low and bias == -1:
            stats.close_pl_count += 1

        entry = BiasEntry(
            timestamp=curr["start_time"],
            bias=bias,
            reason=reason,
            prev_high=pp_h,
            prev_low=pp_l,
            hit_prev_high=hit_high,
            hit_prev_low=hit_low,
            close_through_high=close_through_high,
            close_through_low=close_through_low,
        )
        result.entries.append(entry)

        # Update direction tracker
        prev_up = prev["close"] >= prev["open"]

    # Set current state from latest entry
    if result.entries:
        latest = result.entries[-1]
        result.current_bias = latest.bias
        result.current_reason = latest.reason
        result.current_prev_high = latest.prev_high
        result.current_prev_low = latest.prev_low

    return result
