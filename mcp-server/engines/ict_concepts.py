"""
ICT Session Concepts — Draw on Liquidity, Power of 3 (AMD),
Judas Swing, and Session Bias.

All four indicators are computed from the same underlying data: candles
grouped by trading day and then by session (Asia/London/NY). A single
`analyze()` call returns all four indicators for maximum efficiency.

Session times (UTC):
  Asia (Accumulation):  00:00 – 05:00  (maps to 7PM–12AM EST)
  London Open (Manip):  07:00 – 10:00  (maps to 2AM–5AM EST)
  London:               07:00 – 13:00
  NY (Distribution):    13:00 – 17:00  (maps to 8AM–12PM EST)
  NY Full:              13:00 – 21:00

PO3 is fractal — the same pattern appears on every timeframe.
This implementation focuses on the daily PO3 model and computes
quality metrics (accumulation tightness, manipulation %, distribution %).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from engines.daily_bias import compute_daily_bias


# ── Session boundaries (hour UTC) ─────────────────────────────────
# Aligned with ICT PO3 reference (EST → UTC conversion)

ASIA_START, ASIA_END = 0, 5          # Accumulation: 7PM-12AM EST = 00:00-05:00 UTC
LONDON_START, LONDON_END = 7, 13     # Full London session
NY_START, NY_END = 13, 21            # Full NY session
MANIP_START, MANIP_END = 7, 10       # Manipulation: London Open 2AM-5AM EST = 07:00-10:00 UTC
DIST_START, DIST_END = 13, 17        # Distribution: NY session 8AM-12PM EST = 13:00-17:00 UTC


# ── Data classes ──────────────────────────────────────────────────

@dataclass
class SessionRange:
    """OHLC for a single session within a day."""
    session: str
    high: float = 0.0
    low: float = float("inf")
    open: float = 0.0
    close: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0
    candle_count: int = 0

    def update(self, o: float, h: float, l: float, c: float, t: float):
        if self.candle_count == 0:
            self.open = o
            self.start_time = t
        self.high = max(self.high, h)
        self.low = min(self.low, l)
        self.close = c
        self.end_time = t
        self.candle_count += 1

    @property
    def range(self) -> float:
        if self.candle_count == 0:
            return 0.0
        return self.high - self.low


@dataclass
class DOLEntry:
    """Draw on Liquidity for a single day."""
    day_start: float
    bias: str                 # "bullish" / "bearish" / "neutral"
    dol_price: float          # target level
    dol_label: str            # "PDH" or "PDL"
    opposite_price: float     # the other level (invalidation side)
    reached: bool = False


@dataclass
class AMDPhase:
    """One phase of the Power of 3 pattern for a single day."""
    day_start: float
    phase: str                # "accumulation" / "manipulation" / "distribution"
    start_time: float
    end_time: float
    high: float
    low: float
    direction: str = ""       # manipulation: "up_sweep"/"down_sweep"; distribution: "bullish"/"bearish"
    range_pct: float = 0.0    # percentage of total day range this phase covers
    quality: str = ""         # "clean" / "messy" / "" — PO3 quality label


@dataclass
class JudasSwing:
    """A detected Judas (fake) swing within a day."""
    day_start: float
    sweep_time: float
    sweep_price: float
    direction: str            # "up" = fake bullish, "down" = fake bearish
    asia_high: float
    asia_low: float
    reversal_confirmed: bool = False


@dataclass
class SessionBiasEntry:
    """Bias determination for a specific session."""
    day_start: float
    session: str              # "london" or "ny"
    bias: str                 # "bullish" / "bearish" / "neutral"
    reason: str
    target_high: float
    target_low: float
    hit_target: bool = False


@dataclass
class ICTResult:
    """Combined result of all 4 ICT session concepts."""
    dol_entries: list[DOLEntry] = field(default_factory=list)
    amd_phases: list[AMDPhase] = field(default_factory=list)
    judas_swings: list[JudasSwing] = field(default_factory=list)
    session_bias_entries: list[SessionBiasEntry] = field(default_factory=list)
    current_dol: DOLEntry | None = None
    current_session_bias: SessionBiasEntry | None = None


# ── Helpers ───────────────────────────────────────────────────────

def _get_day_key(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def _get_hour(ts: float) -> int:
    return datetime.fromtimestamp(ts, tz=timezone.utc).hour


def _session_for_hour(hour: int) -> str | None:
    """Map hour to session — uses full session boundaries for grouping."""
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 13:
        return "london"
    if 13 <= hour < 21:
        return "ny"
    return None


def _group_by_day_and_session(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    times: list[float],
) -> dict[str, dict[str, SessionRange]]:
    """Group candles into {day_key: {session_name: SessionRange}}."""
    days: dict[str, dict[str, SessionRange]] = {}

    for i in range(len(times)):
        day_key = _get_day_key(times[i])
        hour = _get_hour(times[i])
        sess = _session_for_hour(hour)
        if sess is None:
            continue

        if day_key not in days:
            days[day_key] = {}
        if sess not in days[day_key]:
            days[day_key][sess] = SessionRange(session=sess)

        days[day_key][sess].update(opens[i], highs[i], lows[i], closes[i], times[i])

    return days


def _get_window_range(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    times: list[float],
    day_key: str,
    hour_start: int,
    hour_end: int,
    label: str = "",
) -> SessionRange | None:
    """Get range for a specific hour window within a day."""
    sr = SessionRange(session=label or f"{hour_start}-{hour_end}")
    for i in range(len(times)):
        if _get_day_key(times[i]) != day_key:
            continue
        hour = _get_hour(times[i])
        if hour_start <= hour < hour_end:
            sr.update(opens[i], highs[i], lows[i], closes[i], times[i])
    return sr if sr.candle_count > 0 else None


def _compute_adr(
    day_sessions: dict[str, dict[str, SessionRange]],
    sorted_days: list[str],
    current_idx: int,
    lookback: int = 14,
) -> float:
    """Compute Average Daily Range from recent days."""
    ranges = []
    start = max(0, current_idx - lookback)
    for idx in range(start, current_idx):
        day_key = sorted_days[idx]
        sessions = day_sessions[day_key]
        day_high = max((s.high for s in sessions.values() if s.candle_count > 0), default=0)
        day_low = min((s.low for s in sessions.values() if s.candle_count > 0), default=0)
        if day_high > 0 and day_low > 0:
            ranges.append(day_high - day_low)
    return sum(ranges) / len(ranges) if ranges else 0.0


# ── Main analysis ─────────────────────────────────────────────────

def analyze(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    times: list[float],
) -> ICTResult:
    """Compute all 4 ICT session concepts from candle data.

    Expects intraday candles (1H or smaller) for best results.
    """
    if len(opens) < 10:
        return ICTResult()

    result = ICTResult()

    # Step 1: Group candles by day and session
    day_sessions = _group_by_day_and_session(opens, highs, lows, closes, times)
    sorted_days = sorted(day_sessions.keys())

    # Step 2: Compute daily bias (reuse existing service)
    bias_result = compute_daily_bias(opens, highs, lows, closes, times, period="D")
    bias_by_ts: dict[float, tuple[int, float, float]] = {}
    for entry in bias_result.entries:
        bias_by_ts[entry.timestamp] = (entry.bias, entry.prev_high, entry.prev_low)

    # Step 3: Process each day
    for day_idx, day_key in enumerate(sorted_days):
        sessions = day_sessions[day_key]
        asia = sessions.get("asia")
        london = sessions.get("london")
        ny = sessions.get("ny")

        if not asia or asia.candle_count == 0:
            continue

        day_start = asia.start_time

        # Compute day's total range
        day_high = max((s.high for s in sessions.values() if s.candle_count > 0), default=0)
        day_low = min((s.low for s in sessions.values() if s.candle_count > 0), default=float("inf"))
        day_range = day_high - day_low if day_high > day_low else 0.0

        # ADR for quality assessment
        adr = _compute_adr(day_sessions, sorted_days, day_idx)

        # ── DOL (Draw on Liquidity) ──
        day_bias = 0
        prev_high = 0.0
        prev_low = 0.0
        for ts, (b, ph, pl) in bias_by_ts.items():
            if _get_day_key(ts) == day_key:
                day_bias = b
                prev_high = ph
                prev_low = pl
                break

        if day_bias != 0 and prev_high > 0:
            is_bull = day_bias == 1
            dol_price = prev_high if is_bull else prev_low
            opposite = prev_low if is_bull else prev_high

            reached = (is_bull and day_high >= dol_price) or (
                not is_bull and day_low <= dol_price
            )

            dol = DOLEntry(
                day_start=day_start,
                bias="bullish" if is_bull else "bearish",
                dol_price=dol_price,
                dol_label="PDH" if is_bull else "PDL",
                opposite_price=opposite,
                reached=reached,
            )
            result.dol_entries.append(dol)

        # ── AMD (Power of 3) ──
        # Get specific windows for each phase
        accum = _get_window_range(opens, highs, lows, closes, times, day_key,
                                  ASIA_START, ASIA_END, "accumulation")
        manip = _get_window_range(opens, highs, lows, closes, times, day_key,
                                  MANIP_START, MANIP_END, "manipulation")
        dist = _get_window_range(opens, highs, lows, closes, times, day_key,
                                 DIST_START, DIST_END, "distribution")

        if accum and accum.candle_count > 0:
            # Accumulation quality: range < 30% of ADR = tight (good)
            accum_pct = (accum.range / adr * 100) if adr > 0 else 0.0
            accum_quality = "clean" if accum_pct < 30 else ("messy" if accum_pct > 50 else "")
            accum_range_pct = (accum.range / day_range * 100) if day_range > 0 else 0.0

            result.amd_phases.append(AMDPhase(
                day_start=day_start,
                phase="accumulation",
                start_time=accum.start_time,
                end_time=accum.end_time,
                high=accum.high,
                low=accum.low,
                range_pct=round(accum_range_pct, 1),
                quality=accum_quality,
            ))

        manip_dir = ""
        if manip and manip.candle_count > 0 and accum and accum.candle_count > 0:
            # Determine manipulation direction
            swept_high = manip.high > accum.high
            swept_low = manip.low < accum.low

            if swept_high and not swept_low:
                manip_dir = "up_sweep"
            elif swept_low and not swept_high:
                manip_dir = "down_sweep"
            elif swept_high and swept_low:
                high_dist = manip.high - accum.high
                low_dist = accum.low - manip.low
                manip_dir = "up_sweep" if high_dist > low_dist else "down_sweep"
            else:
                manip_dir = ""

            # Manipulation quality: should cover 20-40% of day range
            manip_range_pct = (manip.range / day_range * 100) if day_range > 0 else 0.0
            if 20 <= manip_range_pct <= 40 and manip_dir:
                manip_quality = "clean"
            elif manip_dir:
                manip_quality = "messy"
            else:
                manip_quality = ""

            result.amd_phases.append(AMDPhase(
                day_start=day_start,
                phase="manipulation",
                start_time=manip.start_time,
                end_time=manip.end_time,
                high=manip.high,
                low=manip.low,
                direction=manip_dir,
                range_pct=round(manip_range_pct, 1),
                quality=manip_quality,
            ))

            # ── Judas Swing detection ──
            if swept_high and not swept_low:
                reversal = False
                if london and london.close < accum.high:
                    reversal = True
                elif ny and ny.close < accum.high:
                    reversal = True
                result.judas_swings.append(JudasSwing(
                    day_start=day_start,
                    sweep_time=manip.end_time,
                    sweep_price=manip.high,
                    direction="up",
                    asia_high=accum.high,
                    asia_low=accum.low,
                    reversal_confirmed=reversal,
                ))
            elif swept_low and not swept_high:
                reversal = False
                if london and london.close > accum.low:
                    reversal = True
                elif ny and ny.close > accum.low:
                    reversal = True
                result.judas_swings.append(JudasSwing(
                    day_start=day_start,
                    sweep_time=manip.end_time,
                    sweep_price=manip.low,
                    direction="down",
                    asia_high=accum.high,
                    asia_low=accum.low,
                    reversal_confirmed=reversal,
                ))
            elif swept_high and swept_low:
                high_dist = manip.high - accum.high
                low_dist = accum.low - manip.low
                if high_dist > low_dist:
                    result.judas_swings.append(JudasSwing(
                        day_start=day_start,
                        sweep_time=manip.end_time,
                        sweep_price=manip.high,
                        direction="up",
                        asia_high=accum.high,
                        asia_low=accum.low,
                        reversal_confirmed=london is not None and london.close < accum.high,
                    ))
                else:
                    result.judas_swings.append(JudasSwing(
                        day_start=day_start,
                        sweep_time=manip.end_time,
                        sweep_price=manip.low,
                        direction="down",
                        asia_high=accum.high,
                        asia_low=accum.low,
                        reversal_confirmed=london is not None and london.close > accum.low,
                    ))

        # Distribution phase
        if dist and dist.candle_count > 0 and manip and manip.candle_count > 0:
            # Distribution direction: opposite of manipulation sweep
            if manip_dir == "up_sweep":
                dist_dir = "bearish"
            elif manip_dir == "down_sweep":
                dist_dir = "bullish"
            else:
                if london and london.close > london.open:
                    dist_dir = "bullish"
                elif london and london.close < london.open:
                    dist_dir = "bearish"
                else:
                    dist_dir = ""

            # Distribution quality: should cover 50-70% of day range
            dist_range_pct = (dist.range / day_range * 100) if day_range > 0 else 0.0
            if 50 <= dist_range_pct <= 70 and dist_dir:
                dist_quality = "clean"
            elif dist_dir:
                dist_quality = "messy"
            else:
                dist_quality = ""

            result.amd_phases.append(AMDPhase(
                day_start=day_start,
                phase="distribution",
                start_time=dist.start_time,
                end_time=dist.end_time,
                high=dist.high,
                low=dist.low,
                direction=dist_dir,
                range_pct=round(dist_range_pct, 1),
                quality=dist_quality,
            ))

        # ── Session Bias ──
        # London bias: based on accumulation range sweep
        if accum and london and accum.candle_count > 0 and london.candle_count > 0:
            london_swept_high = london.high > accum.high
            london_swept_low = london.low < accum.low

            if london_swept_high and not london_swept_low:
                sb = SessionBiasEntry(
                    day_start=day_start,
                    session="london",
                    bias="bearish",
                    reason="Accumulation H swept — sell-side target",
                    target_high=accum.high,
                    target_low=accum.low,
                    hit_target=london.close < accum.high,
                )
            elif london_swept_low and not london_swept_high:
                sb = SessionBiasEntry(
                    day_start=day_start,
                    session="london",
                    bias="bullish",
                    reason="Accumulation L swept — buy-side target",
                    target_high=accum.high,
                    target_low=accum.low,
                    hit_target=london.close > accum.low,
                )
            elif london_swept_high and london_swept_low:
                if london.close > accum.high:
                    sb = SessionBiasEntry(
                        day_start=day_start, session="london", bias="bullish",
                        reason="Both swept — closed above range",
                        target_high=accum.high, target_low=accum.low, hit_target=True,
                    )
                elif london.close < accum.low:
                    sb = SessionBiasEntry(
                        day_start=day_start, session="london", bias="bearish",
                        reason="Both swept — closed below range",
                        target_high=accum.high, target_low=accum.low, hit_target=True,
                    )
                else:
                    sb = SessionBiasEntry(
                        day_start=day_start, session="london", bias="neutral",
                        reason="Both swept — closed inside range",
                        target_high=accum.high, target_low=accum.low,
                    )
            else:
                mid = (accum.high + accum.low) / 2
                if london.close > mid:
                    sb = SessionBiasEntry(
                        day_start=day_start, session="london", bias="bullish",
                        reason="No sweep — closed above range mid",
                        target_high=accum.high, target_low=accum.low,
                    )
                else:
                    sb = SessionBiasEntry(
                        day_start=day_start, session="london", bias="bearish",
                        reason="No sweep — closed below range mid",
                        target_high=accum.high, target_low=accum.low,
                    )

            result.session_bias_entries.append(sb)

        # NY bias: based on London
        if london and ny and london.candle_count > 0 and ny.candle_count > 0:
            london_up = london.close > london.open
            ny_swept_london_high = ny.high > london.high
            ny_swept_london_low = ny.low < london.low

            if ny_swept_london_high and not ny_swept_london_low:
                ny_sb = SessionBiasEntry(
                    day_start=day_start, session="ny", bias="bearish",
                    reason="London H swept — reversal expected",
                    target_high=london.high, target_low=london.low,
                    hit_target=ny.close < london.high,
                )
            elif ny_swept_london_low and not ny_swept_london_high:
                ny_sb = SessionBiasEntry(
                    day_start=day_start, session="ny", bias="bullish",
                    reason="London L swept — reversal expected",
                    target_high=london.high, target_low=london.low,
                    hit_target=ny.close > london.low,
                )
            elif london_up:
                ny_sb = SessionBiasEntry(
                    day_start=day_start, session="ny", bias="bullish",
                    reason="London bullish — continuation expected",
                    target_high=london.high, target_low=london.low,
                    hit_target=ny.high > london.high,
                )
            else:
                ny_sb = SessionBiasEntry(
                    day_start=day_start, session="ny", bias="bearish",
                    reason="London bearish — continuation expected",
                    target_high=london.high, target_low=london.low,
                    hit_target=ny.low < london.low,
                )

            result.session_bias_entries.append(ny_sb)

    # Set current state
    if result.dol_entries:
        result.current_dol = result.dol_entries[-1]
    if result.session_bias_entries:
        result.current_session_bias = result.session_bias_entries[-1]

    return result
