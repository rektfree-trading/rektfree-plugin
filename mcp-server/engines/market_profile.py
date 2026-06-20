"""
Market Profile / TPO (Time Price Opportunity) analysis engine.

Computes session-based TPO profiles from OHLC candle data:
- Groups candles into sessions based on timeframe
- Divides price range into tick-size buckets
- Counts TPOs per bucket, assigns letters per time period
- Finds POC (Point of Control) — price level with most TPOs
- Computes Value Area (VAH / VAL) — ~68.26% of TPOs around POC
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class TPOBucket:
    price_level: float        # bottom of the bucket
    count: int = 0            # number of TPOs (candles touching this level)
    letters: list[str] = field(default_factory=list)
    zone: str = "outside"     # "poc", "value", or "outside"


@dataclass
class TPOProfile:
    session_label: str
    start_time: float         # unix seconds
    end_time: float           # unix seconds (0 = still open)
    tick_size: float
    poc: float = 0.0          # Point of Control price level
    vah: float = 0.0          # Value Area High
    val: float = 0.0          # Value Area Low
    poc_count: int = 0        # TPO count at POC
    total_tpos: int = 0
    buckets: list[TPOBucket] = field(default_factory=list)


TPO_LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


def _get_session_boundaries(
    times: list[float],
    timeframe: str,
) -> list[tuple[int, int, str]]:
    """Group candle indices into sessions.

    Returns list of (start_idx, end_idx, label) tuples.
    """
    if not times:
        return []

    sessions: list[tuple[int, int, str]] = []

    if timeframe in ("1m", "5m"):
        # Session = 1 hour for 1m, 4 hours for 5m
        bucket_hours = 1 if timeframe == "1m" else 4
        current_key = None
        start_idx = 0

        for i, ts in enumerate(times):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            bucket_hour = (dt.hour // bucket_hours) * bucket_hours
            key = f"{dt.year}-{dt.month:02d}-{dt.day:02d} {bucket_hour:02d}:00"

            if key != current_key:
                if current_key is not None:
                    sessions.append((start_idx, i - 1, current_key))
                current_key = key
                start_idx = i

        if current_key is not None:
            sessions.append((start_idx, len(times) - 1, current_key))

    elif timeframe in ("15m", "1H"):
        # Session = 1 day
        current_key = None
        start_idx = 0

        for i, ts in enumerate(times):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            key = f"{dt.year}-{dt.month:02d}-{dt.day:02d}"

            if key != current_key:
                if current_key is not None:
                    sessions.append((start_idx, i - 1, current_key))
                current_key = key
                start_idx = i

        if current_key is not None:
            sessions.append((start_idx, len(times) - 1, current_key))

    elif timeframe == "4H":
        # Session = 1 week
        current_key = None
        start_idx = 0

        for i, ts in enumerate(times):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            iso = dt.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"

            if key != current_key:
                if current_key is not None:
                    sessions.append((start_idx, i - 1, current_key))
                current_key = key
                start_idx = i

        if current_key is not None:
            sessions.append((start_idx, len(times) - 1, current_key))

    else:
        # D, W → session = 1 month
        current_key = None
        start_idx = 0

        for i, ts in enumerate(times):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            key = f"{dt.year}-{dt.month:02d}"

            if key != current_key:
                if current_key is not None:
                    sessions.append((start_idx, i - 1, current_key))
                current_key = key
                start_idx = i

        if current_key is not None:
            sessions.append((start_idx, len(times) - 1, current_key))

    return sessions


def _auto_tick_size(highs: list[float], lows: list[float], start: int, end: int) -> float:
    """Auto-calculate tick size from median candle range, targeting ~10 buckets per candle."""
    ranges = []
    for i in range(start, end + 1):
        r = highs[i] - lows[i]
        if r > 0:
            ranges.append(r)

    if not ranges:
        return 1.0

    ranges.sort()
    median_range = ranges[len(ranges) // 2]

    # Target: ~10 buckets per average candle → divide median by 10
    raw = median_range / 10.0

    if raw <= 0:
        return 1.0

    # Round to a "nice" number
    magnitude = 10 ** math.floor(math.log10(raw))
    normalized = raw / magnitude

    if normalized <= 1.5:
        nice = 1
    elif normalized <= 3.5:
        nice = 2
    elif normalized <= 7.5:
        nice = 5
    else:
        nice = 10

    return nice * magnitude


def _compute_value_area(
    buckets: list[TPOBucket],
    poc_index: int,
    target_pct: float = 0.6826,
) -> tuple[int, int]:
    """Compute value area indices by expanding outward from POC.

    Uses the CME method: starting from POC, alternately add the pair of
    rows (above vs below) with the higher combined TPO count.
    """
    total = sum(b.count for b in buckets)
    if total == 0:
        return poc_index, poc_index

    target_tpos = int(total * target_pct) - buckets[poc_index].count
    max_idx = len(buckets) - 1
    val_idx = poc_index
    vah_idx = poc_index

    for _ in range(max_idx + 1):
        if target_tpos <= 0:
            break

        # Get TPO counts for candidates above and below
        up1 = buckets[vah_idx + 1].count if vah_idx + 1 <= max_idx else 0
        up2 = buckets[vah_idx + 2].count if vah_idx + 2 <= max_idx else 0
        dn1 = buckets[val_idx - 1].count if val_idx - 1 >= 0 else 0
        dn2 = buckets[val_idx - 2].count if val_idx - 2 >= 0 else 0

        up_sum = up1 + up2
        dn_sum = dn1 + dn2

        if vah_idx >= max_idx and val_idx <= 0:
            break

        if vah_idx >= max_idx:
            # Can only expand down
            if dn1 > 0:
                target_tpos -= dn1
                val_idx -= 1
            else:
                break
        elif val_idx <= 0:
            # Can only expand up
            if up1 > 0:
                target_tpos -= up1
                vah_idx += 1
            else:
                break
        elif up_sum > dn_sum:
            # Expand up (take 2 rows if possible, else 1)
            if vah_idx + 2 <= max_idx:
                target_tpos -= up_sum
                vah_idx += 2
            else:
                target_tpos -= up1
                vah_idx += 1
        elif dn_sum > up_sum:
            # Expand down
            if val_idx - 2 >= 0:
                target_tpos -= dn_sum
                val_idx -= 2
            else:
                target_tpos -= dn1
                val_idx -= 1
        else:
            # Tie — expand toward the midpoint
            mid = len(buckets) // 2
            if abs(vah_idx - mid) <= abs(val_idx - mid):
                if vah_idx + 1 <= max_idx:
                    target_tpos -= up1
                    vah_idx += 1
                else:
                    target_tpos -= dn1
                    val_idx -= 1
            else:
                if val_idx - 1 >= 0:
                    target_tpos -= dn1
                    val_idx -= 1
                else:
                    target_tpos -= up1
                    vah_idx += 1

    return val_idx, vah_idx


def compute_profiles(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    times: list[float],
    timeframe: str,
    value_area_pct: float = 0.6826,
    max_sessions: int = 10,
) -> list[TPOProfile]:
    """Compute Market Profile TPO for each session.

    Args:
        highs, lows, closes: OHLC price arrays
        times: Unix timestamps (seconds)
        timeframe: Candle timeframe string (1m, 5m, 15m, 1H, 4H, D, W)
        value_area_pct: Value area percentage (default 68.26%)
        max_sessions: Maximum number of sessions to return

    Returns:
        List of TPOProfile objects, most recent last
    """
    n = len(closes)
    if n < 2:
        return []

    sessions = _get_session_boundaries(times, timeframe)
    if not sessions:
        return []

    # Limit to most recent sessions
    sessions = sessions[-max_sessions:]

    profiles: list[TPOProfile] = []

    for start_idx, end_idx, label in sessions:
        # Find session high/low
        session_high = max(highs[start_idx:end_idx + 1])
        session_low = min(lows[start_idx:end_idx + 1])

        if session_high <= session_low:
            continue

        # Auto tick size for this session
        tick_size = _auto_tick_size(highs, lows, start_idx, end_idx)
        if tick_size <= 0:
            continue

        # Build price buckets
        bucket_low = math.floor(session_low / tick_size) * tick_size
        bucket_high = math.ceil(session_high / tick_size) * tick_size
        num_buckets = max(1, int(round((bucket_high - bucket_low) / tick_size)))

        # Safety cap
        if num_buckets > 200:
            tick_size = (bucket_high - bucket_low) / 100
            num_buckets = 100

        buckets: list[TPOBucket] = []
        for j in range(num_buckets):
            price = bucket_low + j * tick_size
            buckets.append(TPOBucket(price_level=round(price, 10)))

        # Count TPOs per bucket
        num_candles = end_idx - start_idx + 1
        for ci in range(start_idx, end_idx + 1):
            letter_idx = ci - start_idx
            letter = TPO_LETTERS[letter_idx % len(TPO_LETTERS)] if letter_idx < len(TPO_LETTERS) else str(letter_idx)

            for b in buckets:
                bucket_top = b.price_level + tick_size
                # Candle touches this bucket if low < bucket_top AND high >= bucket_bottom
                if lows[ci] < bucket_top and highs[ci] >= b.price_level:
                    b.count += 1
                    b.letters.append(letter)

        # Find POC (bucket with max count, closest to mid if tie)
        if not buckets:
            continue

        max_count = max(b.count for b in buckets)
        mid_price = (session_high + session_low) / 2
        poc_idx = 0
        poc_dist = float("inf")
        for i, b in enumerate(buckets):
            if b.count == max_count:
                dist = abs(b.price_level + tick_size / 2 - mid_price)
                if dist < poc_dist:
                    poc_dist = dist
                    poc_idx = i

        # Compute value area
        val_idx, vah_idx = _compute_value_area(buckets, poc_idx, value_area_pct)

        # Tag zones
        for i, b in enumerate(buckets):
            if i == poc_idx:
                b.zone = "poc"
            elif val_idx <= i <= vah_idx:
                b.zone = "value"
            else:
                b.zone = "outside"

        # Check if this is the current (still open) session
        is_last = (end_idx == n - 1)

        profile = TPOProfile(
            session_label=label,
            start_time=times[start_idx],
            end_time=0.0 if is_last else times[end_idx],
            tick_size=tick_size,
            poc=buckets[poc_idx].price_level + tick_size / 2,
            vah=buckets[vah_idx].price_level + tick_size,
            val=buckets[val_idx].price_level,
            poc_count=max_count,
            total_tpos=sum(b.count for b in buckets),
            buckets=buckets,
        )
        profiles.append(profile)

    return profiles
