"""
Smart Money Concepts (SMC) analysis engine.
Ported from LuxAlgo's PineScript indicator.

Detects:
- Market Structure: Break of Structure (BOS) and Change of Character (CHoCH)
- Order Blocks (OB): Bullish and Bearish
- Fair Value Gaps (FVG): Bullish and Bearish
- Equal Highs/Lows (EQH/EQL)
- Premium/Discount/Equilibrium zones
- Strong/Weak Highs and Lows
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal

logger = logging.getLogger(__name__)

BULLISH = 1
BEARISH = -1


@dataclass
class Pivot:
    level: float = 0.0
    last_level: float = 0.0
    crossed: bool = False
    bar_index: int = 0
    timestamp: float = 0.0  # unix seconds


@dataclass
class StructureBreak:
    type: str  # "BOS" or "CHoCH"
    bias: int  # BULLISH or BEARISH
    level: float
    start_time: float  # unix seconds
    end_time: float
    start_index: int
    end_index: int


@dataclass
class OrderBlock:
    high: float
    low: float
    timestamp: float
    bar_index: int
    bias: int  # BULLISH or BEARISH
    mitigated: bool = False


@dataclass
class FairValueGap:
    top: float
    bottom: float
    mid: float
    bias: int  # BULLISH or BEARISH
    timestamp: float
    bar_index: int
    mitigated: bool = False


@dataclass
class EqualLevel:
    level: float
    prev_time: float
    curr_time: float
    prev_index: int
    curr_index: int
    type: str  # "EQH" or "EQL"


@dataclass
class SwingLabel:
    """HH, HL, LH, LL labels at swing pivots."""
    label: str  # "HH", "HL", "LH", "LL"
    price: float
    timestamp: float
    bar_index: int
    bias: int  # BULLISH or BEARISH


@dataclass
class LiquiditySweep:
    """Liquidity grab — price takes out a level then reverses."""
    level: float
    sweep_price: float  # how far past the level price went
    timestamp: float
    bar_index: int
    type: str  # "WICK" or "RETEST"
    bias: int  # direction of expected reversal after sweep
    pivot_time: float = 0.0  # timestamp of the original pivot


@dataclass
class BreakerBlock:
    """A mitigated order block that flips — failed support becomes resistance."""
    high: float
    low: float
    timestamp: float
    bar_index: int
    bias: int  # BULLISH = bullish breaker (old bear OB flipped), BEARISH = opposite


@dataclass
class SweepArea:
    """Extending box showing sweep zone (LuxAlgo style)."""
    top: float
    bottom: float
    start_time: float
    start_index: int
    direction: int   # 1 = upward sweep, -1 = downward sweep
    bias: int         # BULLISH or BEARISH (expected reversal direction)
    broken: bool = False
    end_time: float = 0.0


@dataclass
class SMCResult:
    """Complete SMC analysis result for an asset/timeframe."""
    structures: list[StructureBreak] = field(default_factory=list)
    order_blocks: list[OrderBlock] = field(default_factory=list)
    fair_value_gaps: list[FairValueGap] = field(default_factory=list)
    equal_levels: list[EqualLevel] = field(default_factory=list)
    swing_labels: list[SwingLabel] = field(default_factory=list)
    fractal_labels: list[SwingLabel] = field(default_factory=list)  # William's Fractal swing points
    liquidity_sweeps: list[LiquiditySweep] = field(default_factory=list)
    sweep_areas: list[SweepArea] = field(default_factory=list)
    breaker_blocks: list[BreakerBlock] = field(default_factory=list)
    # Per-candle trend bias for candle coloring (1=bullish, -1=bearish)
    candle_trends: list[int] = field(default_factory=list)
    swing_high: float = 0.0
    swing_low: float = 0.0
    swing_high_time: float = 0.0
    swing_low_time: float = 0.0
    trend_bias: int = 0  # BULLISH or BEARISH
    strong_high: float = 0.0
    strong_low: float = 0.0
    weak_high: float = 0.0
    weak_low: float = 0.0


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    """Calculate Average True Range."""
    atrs = [0.0] * len(highs)
    if len(highs) < 2:
        return atrs

    trs = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    if len(trs) == 0:
        return atrs

    # Simple moving average for first period
    if len(trs) >= period:
        atrs[period] = sum(trs[:period]) / period
        for i in range(period + 1, len(highs)):
            atrs[i] = (atrs[i - 1] * (period - 1) + trs[i - 1]) / period
    else:
        avg = sum(trs) / len(trs)
        for i in range(1, len(highs)):
            atrs[i] = avg

    return atrs


def _find_pivots(
    highs: list[float],
    lows: list[float],
    times: list[float],
    lookback: int,
) -> tuple[list[tuple[int, float, float]], list[tuple[int, float, float]]]:
    """Find pivot highs and lows — matches PineScript ta.pivothigh/ta.pivotlow.

    PineScript comparison rules:
      - Left bars: pivot >= left neighbors (ties OK → only strictly greater rejects)
      - Right bars: pivot > right neighbors (ties reject → first occurrence preferred)

    Returns (pivot_highs, pivot_lows) as lists of (index, price, timestamp).
    """
    pivot_highs = []
    pivot_lows = []

    for i in range(lookback, len(highs) - lookback):
        # Pivot high: center must be >= all left, > all right
        is_high = True
        for j in range(i - lookback, i):
            if highs[j] > highs[i]:       # left: reject only if strictly higher
                is_high = False
                break
        if is_high:
            for j in range(i + 1, i + lookback + 1):
                if highs[j] >= highs[i]:   # right: reject if equal or higher
                    is_high = False
                    break
        if is_high:
            pivot_highs.append((i, highs[i], times[i]))

        # Pivot low: center must be <= all left, < all right
        is_low = True
        for j in range(i - lookback, i):
            if lows[j] < lows[i]:          # left: reject only if strictly lower
                is_low = False
                break
        if is_low:
            for j in range(i + 1, i + lookback + 1):
                if lows[j] <= lows[i]:     # right: reject if equal or lower
                    is_low = False
                    break
        if is_low:
            pivot_lows.append((i, lows[i], times[i]))

    return pivot_highs, pivot_lows


def analyze(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    times: list[float],
    swing_length: int = 50,
    internal_length: int = 5,
    eql_threshold: float = 0.1,
    eql_length: int = 3,
    max_order_blocks: int = 10,
    max_fvgs: int = 20,
) -> SMCResult:
    """
    Run full SMC analysis on OHLC data.

    Args:
        opens, highs, lows, closes: OHLC price arrays
        times: Unix timestamp (seconds) for each bar
        swing_length: Lookback for swing structure detection
        internal_length: Lookback for internal structure detection
        eql_threshold: ATR multiplier threshold for equal highs/lows
        eql_length: Lookback for equal highs/lows
        max_order_blocks: Max order blocks to return
        max_fvgs: Max fair value gaps to return

    Returns:
        SMCResult with all detected features
    """
    n = len(closes)
    if n < swing_length * 2 + 1:
        return SMCResult()

    result = SMCResult()
    atrs = _atr(highs, lows, closes, 200)

    # ─── Swing Structure (BOS / CHoCH) ───
    swing_pivot_highs, swing_pivot_lows = _find_pivots(highs, lows, times, swing_length)
    _detect_structure(closes, times, swing_pivot_highs, swing_pivot_lows, result, internal=False)

    # ─── Internal Structure ───
    int_pivot_highs, int_pivot_lows = _find_pivots(highs, lows, times, internal_length)
    _detect_structure(closes, times, int_pivot_highs, int_pivot_lows, result, internal=True)

    # ─── Order Blocks ───
    _detect_order_blocks(highs, lows, closes, times, result, atrs, max_order_blocks)

    # ─── Fair Value Gaps ───
    _detect_fvgs(highs, lows, closes, times, result, atrs, max_fvgs)

    # ─── Equal Highs / Lows ───
    # Use the same swing pivots we already detected for structure
    _detect_equal_levels_from_pivots(
        swing_pivot_highs, swing_pivot_lows, atrs, eql_threshold, result
    )

    # ─── Trailing Swing High/Low + Strong/Weak + Premium/Discount range ───
    if swing_pivot_highs and swing_pivot_lows:
        # For premium/discount: use the last swing high and last swing low
        # This represents the current "range" the market is working within
        last_sh = swing_pivot_highs[-1]
        last_sl = swing_pivot_lows[-1]

        result.swing_high = last_sh[1]
        result.swing_high_time = last_sh[2]
        result.swing_low = last_sl[1]
        result.swing_low_time = last_sl[2]

        # If the swing range doesn't contain current price, expand it
        current_price = closes[-1]
        if current_price > result.swing_high:
            result.swing_high = max(highs[-50:])
            idx = n - 50 + highs[-50:].index(result.swing_high)
            result.swing_high_time = times[idx]
        if current_price < result.swing_low:
            result.swing_low = min(lows[-50:])
            idx = n - 50 + lows[-50:].index(result.swing_low)
            result.swing_low_time = times[idx]

        # Strong/Weak: in a bearish trend, the high that started the move is "strong"
        # and the low is "weak" (expected to break). Vice versa for bullish.
        if result.trend_bias == BULLISH:
            result.strong_low = result.swing_low
            result.weak_high = result.swing_high
        else:
            result.strong_high = result.swing_high
            result.weak_low = result.swing_low

    # ─── 1. Swing Point Labels (HH, HL, LH, LL) ───
    _detect_swing_labels(swing_pivot_highs, swing_pivot_lows, result)

    # ─── 1b. William's Fractal swing points ───
    _detect_fractal_labels(highs, lows, times, result)

    # ─── 2. Liquidity Sweeps (LuxAlgo style: wicks + outbreaks & retest) ───
    _detect_liquidity_sweeps(highs, lows, closes, times, result, int_pivot_highs, int_pivot_lows, internal_length)

    # ─── 3. Breaker Blocks (mitigated OBs that flip) ───
    _detect_breaker_blocks(highs, lows, closes, times, result, atrs, max_order_blocks)

    # ─── 4. Candle trend coloring ───
    result.candle_trends = _compute_candle_trends(closes, times, int_pivot_highs, int_pivot_lows)

    return result


def _detect_structure(
    closes: list[float],
    times: list[float],
    pivot_highs: list[tuple[int, float, float]],
    pivot_lows: list[tuple[int, float, float]],
    result: SMCResult,
    internal: bool,
):
    """Detect BOS and CHoCH from pivot points."""
    trend = 0  # 0 = undefined, BULLISH or BEARISH
    last_high = Pivot()
    last_low = Pivot()

    # Process pivots in chronological order
    all_pivots = []
    for idx, price, ts in pivot_highs:
        all_pivots.append((idx, "high", price, ts))
    for idx, price, ts in pivot_lows:
        all_pivots.append((idx, "low", price, ts))
    all_pivots.sort(key=lambda x: x[0])

    for idx, ptype, price, ts in all_pivots:
        if ptype == "high":
            last_high.last_level = last_high.level
            last_high.level = price
            last_high.crossed = False
            last_high.bar_index = idx
            last_high.timestamp = ts
        else:
            last_low.last_level = last_low.level
            last_low.level = price
            last_low.crossed = False
            last_low.bar_index = idx
            last_low.timestamp = ts

    # Now scan for structure breaks
    last_high = Pivot()
    last_low = Pivot()
    trend = 0

    for idx, ptype, price, ts in all_pivots:
        if ptype == "high":
            last_high.last_level = last_high.level
            last_high.level = price
            last_high.crossed = False
            last_high.bar_index = idx
            last_high.timestamp = ts
        else:
            last_low.last_level = last_low.level
            last_low.level = price
            last_low.crossed = False
            last_low.bar_index = idx
            last_low.timestamp = ts

        # Check for bullish break (close crosses above previous high)
        if last_high.level > 0 and not last_high.crossed:
            # Find bars after the pivot that cross the level
            for i in range(idx + 1, min(idx + 50, len(closes))):
                if closes[i] > last_high.level:
                    tag = "CHoCH" if trend == BEARISH else "BOS"
                    last_high.crossed = True
                    trend = BULLISH
                    result.structures.append(StructureBreak(
                        type=tag,
                        bias=BULLISH,
                        level=last_high.level,
                        start_time=last_high.timestamp,
                        end_time=times[i],
                        start_index=last_high.bar_index,
                        end_index=i,
                    ))
                    break

        # Check for bearish break
        if last_low.level > 0 and not last_low.crossed:
            for i in range(idx + 1, min(idx + 50, len(closes))):
                if closes[i] < last_low.level:
                    tag = "CHoCH" if trend == BULLISH else "BOS"
                    last_low.crossed = True
                    trend = BEARISH
                    result.structures.append(StructureBreak(
                        type=tag,
                        bias=BEARISH,
                        level=last_low.level,
                        start_time=last_low.timestamp,
                        end_time=times[i],
                        start_index=last_low.bar_index,
                        end_index=i,
                    ))
                    break

    result.trend_bias = trend


def _detect_order_blocks(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    times: list[float],
    result: SMCResult,
    atrs: list[float],
    max_obs: int,
):
    """Detect order blocks from structure breaks."""
    for sb in result.structures[-max_obs * 2:]:
        if sb.bias == BULLISH:
            # Bullish OB: find the lowest low candle before the break
            search_start = max(0, sb.start_index - 10)
            search_end = sb.start_index + 1
            if search_start >= search_end:
                continue
            min_low = min(lows[search_start:search_end])
            min_idx = search_start + lows[search_start:search_end].index(min_low)
            ob = OrderBlock(
                high=highs[min_idx],
                low=lows[min_idx],
                timestamp=times[min_idx],
                bar_index=min_idx,
                bias=BULLISH,
            )
            # Check if mitigated
            for i in range(min_idx + 1, len(closes)):
                if lows[i] < ob.low:
                    ob.mitigated = True
                    break
            result.order_blocks.append(ob)
        else:
            # Bearish OB: find the highest high candle before the break
            search_start = max(0, sb.start_index - 10)
            search_end = sb.start_index + 1
            if search_start >= search_end:
                continue
            max_high = max(highs[search_start:search_end])
            max_idx = search_start + highs[search_start:search_end].index(max_high)
            ob = OrderBlock(
                high=highs[max_idx],
                low=lows[max_idx],
                timestamp=times[max_idx],
                bar_index=max_idx,
                bias=BEARISH,
            )
            for i in range(max_idx + 1, len(closes)):
                if highs[i] > ob.high:
                    ob.mitigated = True
                    break
            result.order_blocks.append(ob)

    # Keep only unmitigated + most recent
    result.order_blocks = [ob for ob in result.order_blocks if not ob.mitigated][-max_obs:]


def _detect_fvgs(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    times: list[float],
    result: SMCResult,
    atrs: list[float],
    max_fvgs: int,
):
    """Detect Fair Value Gaps (3-candle imbalance)."""
    for i in range(2, len(closes)):
        # Bullish FVG: candle 3 low > candle 1 high (gap up)
        if lows[i] > highs[i - 2]:
            fvg = FairValueGap(
                top=lows[i],
                bottom=highs[i - 2],
                mid=(lows[i] + highs[i - 2]) / 2,
                bias=BULLISH,
                timestamp=times[i - 1],
                bar_index=i - 1,
            )
            # Check if mitigated (price came back down into the gap)
            for j in range(i + 1, len(closes)):
                if lows[j] < fvg.bottom:
                    fvg.mitigated = True
                    break
            result.fair_value_gaps.append(fvg)

        # Bearish FVG: candle 3 high < candle 1 low (gap down)
        if highs[i] < lows[i - 2]:
            fvg = FairValueGap(
                top=lows[i - 2],
                bottom=highs[i],
                mid=(lows[i - 2] + highs[i]) / 2,
                bias=BEARISH,
                timestamp=times[i - 1],
                bar_index=i - 1,
            )
            for j in range(i + 1, len(closes)):
                if highs[j] > fvg.top:
                    fvg.mitigated = True
                    break
            result.fair_value_gaps.append(fvg)

    # Keep only unmitigated + most recent
    result.fair_value_gaps = [f for f in result.fair_value_gaps if not f.mitigated][-max_fvgs:]


def _detect_equal_levels_from_pivots(
    pivot_highs: list[tuple[int, float, float]],
    pivot_lows: list[tuple[int, float, float]],
    atrs: list[float],
    threshold: float,
    result: SMCResult,
):
    """Detect Equal Highs/Lows by comparing consecutive swing pivots.

    Uses percentage-based threshold: two swing points are "equal" if they're
    within threshold% of each other (e.g. 0.3% for BTC = ~$200 at $66k).
    """
    pct_threshold = 0.003  # 0.3% of price

    # Compare consecutive swing highs
    for i in range(1, len(pivot_highs)):
        prev_idx, prev_price, prev_time = pivot_highs[i - 1]
        curr_idx, curr_price, curr_time = pivot_highs[i]

        avg_price = (curr_price + prev_price) / 2
        if avg_price > 0 and abs(curr_price - prev_price) / avg_price < pct_threshold:
            result.equal_levels.append(EqualLevel(
                level=avg_price,
                prev_time=prev_time,
                curr_time=curr_time,
                prev_index=prev_idx,
                curr_index=curr_idx,
                type="EQH",
            ))

    # Also compare non-consecutive (i vs i-2, i-3) for wider patterns
    for i in range(2, len(pivot_highs)):
        for j in range(max(0, i - 3), i):
            prev_idx, prev_price, prev_time = pivot_highs[j]
            curr_idx, curr_price, curr_time = pivot_highs[i]
            # Skip if already matched as consecutive
            if j == i - 1:
                continue
            avg_price = (curr_price + prev_price) / 2
            if avg_price > 0 and abs(curr_price - prev_price) / avg_price < pct_threshold:
                result.equal_levels.append(EqualLevel(
                    level=avg_price,
                    prev_time=prev_time,
                    curr_time=curr_time,
                    prev_index=prev_idx,
                    curr_index=curr_idx,
                    type="EQH",
                ))

    # Compare consecutive swing lows
    for i in range(1, len(pivot_lows)):
        prev_idx, prev_price, prev_time = pivot_lows[i - 1]
        curr_idx, curr_price, curr_time = pivot_lows[i]

        avg_price = (curr_price + prev_price) / 2
        if avg_price > 0 and abs(curr_price - prev_price) / avg_price < pct_threshold:
            result.equal_levels.append(EqualLevel(
                level=avg_price,
                prev_time=prev_time,
                curr_time=curr_time,
                prev_index=prev_idx,
                curr_index=curr_idx,
                type="EQL",
            ))

    # Non-consecutive lows
    for i in range(2, len(pivot_lows)):
        for j in range(max(0, i - 3), i):
            prev_idx, prev_price, prev_time = pivot_lows[j]
            curr_idx, curr_price, curr_time = pivot_lows[i]
            if j == i - 1:
                continue
            avg_price = (curr_price + prev_price) / 2
            if avg_price > 0 and abs(curr_price - prev_price) / avg_price < pct_threshold:
                result.equal_levels.append(EqualLevel(
                    level=avg_price,
                    prev_time=prev_time,
                    curr_time=curr_time,
                    prev_index=prev_idx,
                    curr_index=curr_idx,
                    type="EQL",
                ))


def _detect_swing_labels(
    pivot_highs: list[tuple[int, float, float]],
    pivot_lows: list[tuple[int, float, float]],
    result: SMCResult,
):
    """Label each swing pivot as HH, HL, LH, or LL."""
    # Process highs
    for i in range(1, len(pivot_highs)):
        prev_price = pivot_highs[i - 1][1]
        curr_idx, curr_price, curr_time = pivot_highs[i]
        label = "HH" if curr_price > prev_price else "LH"
        result.swing_labels.append(SwingLabel(
            label=label,
            price=curr_price,
            timestamp=curr_time,
            bar_index=curr_idx,
            bias=BULLISH if label == "HH" else BEARISH,
        ))

    # Process lows
    for i in range(1, len(pivot_lows)):
        prev_price = pivot_lows[i - 1][1]
        curr_idx, curr_price, curr_time = pivot_lows[i]
        label = "HL" if curr_price > prev_price else "LL"
        result.swing_labels.append(SwingLabel(
            label=label,
            price=curr_price,
            timestamp=curr_time,
            bar_index=curr_idx,
            bias=BULLISH if label == "HL" else BEARISH,
        ))


def _detect_fractal_labels(
    highs: list[float],
    lows: list[float],
    times: list[float],
    result: SMCResult,
    n: int = 2,
):
    """Detect swing points using William's Fractal (n=2).

    Handles equal/flat bars by extending the left-side check up to n+4 bars,
    matching the classic PineScript implementation.
    """
    length = len(highs)
    if length < n + 3:
        return

    # Detect fractal highs
    fractal_highs: list[tuple[int, float, float]] = []  # (index, price, timestamp)
    for i in range(n, length - n):
        h = highs[i]
        # Basic: 2 bars each side strictly lower
        up = (highs[i - 2] < h and highs[i - 1] < h and
              highs[i + 1] < h and highs[i + 2] < h)
        # Extended: handle equal bars to the right (up to 4 extra bars)
        if not up and i + 3 < length:
            up = (highs[i + 3] < h and highs[i + 2] < h and
                  highs[i + 1] == h and
                  highs[i - 1] < h and highs[i - 2] < h)
        if not up and i + 4 < length:
            up = (highs[i + 4] < h and highs[i + 3] < h and
                  highs[i + 2] == h and highs[i + 1] <= h and
                  highs[i - 1] < h and highs[i - 2] < h)
        if not up and i + 5 < length:
            up = (highs[i + 5] < h and highs[i + 4] < h and
                  highs[i + 3] == h and highs[i + 2] == h and highs[i + 1] <= h and
                  highs[i - 1] < h and highs[i - 2] < h)
        if up:
            fractal_highs.append((i, h, times[i]))

    # Detect fractal lows
    fractal_lows: list[tuple[int, float, float]] = []
    for i in range(n, length - n):
        l = lows[i]
        down = (lows[i - 2] > l and lows[i - 1] > l and
                lows[i + 1] > l and lows[i + 2] > l)
        if not down and i + 3 < length:
            down = (lows[i + 3] > l and lows[i + 2] > l and
                    lows[i + 1] == l and
                    lows[i - 1] > l and lows[i - 2] > l)
        if not down and i + 4 < length:
            down = (lows[i + 4] > l and lows[i + 3] > l and
                    lows[i + 2] == l and lows[i + 1] >= l and
                    lows[i - 1] > l and lows[i - 2] > l)
        if not down and i + 5 < length:
            down = (lows[i + 5] > l and lows[i + 4] > l and
                    lows[i + 3] == l and lows[i + 2] == l and lows[i + 1] >= l and
                    lows[i - 1] > l and lows[i - 2] > l)
        if down:
            fractal_lows.append((i, l, times[i]))

    # Label HH/LH from fractal highs
    for i in range(1, len(fractal_highs)):
        prev_price = fractal_highs[i - 1][1]
        curr_idx, curr_price, curr_time = fractal_highs[i]
        if curr_price > prev_price:
            label = "HH"
            bias = BULLISH
        elif curr_price < prev_price:
            label = "LH"
            bias = BEARISH
        else:
            label = "EH"
            bias = 0
        result.fractal_labels.append(SwingLabel(
            label=label,
            price=curr_price,
            timestamp=curr_time,
            bar_index=curr_idx,
            bias=bias,
        ))

    # Label HL/LL from fractal lows
    for i in range(1, len(fractal_lows)):
        prev_price = fractal_lows[i - 1][1]
        curr_idx, curr_price, curr_time = fractal_lows[i]
        if curr_price > prev_price:
            label = "HL"
            bias = BULLISH
        elif curr_price < prev_price:
            label = "LL"
            bias = BEARISH
        else:
            label = "EL"
            bias = 0
        result.fractal_labels.append(SwingLabel(
            label=label,
            price=curr_price,
            timestamp=curr_time,
            bar_index=curr_idx,
            bias=bias,
        ))


def _detect_liquidity_sweeps(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    times: list[float],
    result: SMCResult,
    pivot_highs: list[tuple[int, float, float]],
    pivot_lows: list[tuple[int, float, float]],
    swing_length: int = 5,
):
    """Detect liquidity sweeps — LuxAlgo "Only Wicks" mode.

    For each pivot high:
      - If close > pivot → pivot is mitigated (done, removed)
      - If high > pivot AND close < pivot → WICK SWEEP (bearish)
        Creates a sweep area box from [sweep_high, pivot_level] extending right.

    For each pivot low:
      - If close < pivot → pivot is mitigated (done, removed)
      - If low < pivot AND close > pivot → WICK SWEEP (bullish)
        Creates a sweep area box from [pivot_level, sweep_low] extending right.

    Sweep area boxes extend rightward until price closes beyond the box
    boundary (broken) or max 300 bars.
    """
    n = len(closes)
    if n < swing_length * 2 + 1:
        return

    # Per-pivot state: [price, bar_index, timestamp, mitigated, wicked]
    PRC, BIX, TS, MIT, WIC = 0, 1, 2, 3, 4

    active_highs: list[list] = []
    active_lows: list[list] = []

    # Build confirmation lookup: pivot confirmed swing_length bars after it
    ph_by_confirm: dict[int, list[list]] = {}
    for idx, price, ts in pivot_highs:
        confirm = idx + swing_length
        if confirm < n:
            ph_by_confirm.setdefault(confirm, []).append(
                [price, idx, ts, False, False]
            )
    pl_by_confirm: dict[int, list[list]] = {}
    for idx, price, ts in pivot_lows:
        confirm = idx + swing_length
        if confirm < n:
            pl_by_confirm.setdefault(confirm, []).append(
                [price, idx, ts, False, False]
            )

    for i in range(n):
        # Activate newly confirmed pivots
        if i in ph_by_confirm:
            active_highs.extend(ph_by_confirm[i])
        if i in pl_by_confirm:
            active_lows.extend(pl_by_confirm[i])

        # ── Pivot highs ──
        remove_h = []
        for j, ph in enumerate(active_highs):
            if ph[MIT]:
                remove_h.append(j)
                continue
            if i - ph[BIX] > 2000:
                remove_h.append(j)
                continue

            # Close above pivot → mitigated immediately (Only Wicks mode)
            if closes[i] > ph[PRC]:
                ph[MIT] = True
                continue

            # Wick sweep: high wicks above pivot but close stays below → bearish
            if not ph[WIC] and highs[i] > ph[PRC] and closes[i] < ph[PRC]:
                result.liquidity_sweeps.append(LiquiditySweep(
                    level=ph[PRC], sweep_price=highs[i],
                    timestamp=times[i], bar_index=i,
                    type="WICK", bias=BEARISH,
                    pivot_time=ph[TS],
                ))
                result.sweep_areas.append(SweepArea(
                    top=highs[i], bottom=ph[PRC],
                    start_time=times[i], start_index=i,
                    direction=1, bias=BEARISH,
                ))
                ph[WIC] = True

        for j in reversed(remove_h):
            active_highs.pop(j)

        # ── Pivot lows ──
        remove_l = []
        for j, pl in enumerate(active_lows):
            if pl[MIT]:
                remove_l.append(j)
                continue
            if i - pl[BIX] > 2000:
                remove_l.append(j)
                continue

            # Close below pivot → mitigated immediately (Only Wicks mode)
            if closes[i] < pl[PRC]:
                pl[MIT] = True
                continue

            # Wick sweep: low wicks below pivot but close stays above → bullish
            if not pl[WIC] and lows[i] < pl[PRC] and closes[i] > pl[PRC]:
                result.liquidity_sweeps.append(LiquiditySweep(
                    level=pl[PRC], sweep_price=lows[i],
                    timestamp=times[i], bar_index=i,
                    type="WICK", bias=BULLISH,
                    pivot_time=pl[TS],
                ))
                result.sweep_areas.append(SweepArea(
                    top=pl[PRC], bottom=lows[i],
                    start_time=times[i], start_index=i,
                    direction=-1, bias=BULLISH,
                ))
                pl[WIC] = True

        for j in reversed(remove_l):
            active_lows.pop(j)

    # ── Extend sweep area boxes & check breaks ──
    for sa in result.sweep_areas:
        for i in range(sa.start_index + 2, min(sa.start_index + 300, n)):
            if sa.direction == 1 and closes[i] > sa.top:
                sa.broken = True
                sa.end_time = times[i]
                break
            if sa.direction == -1 and closes[i] < sa.bottom:
                sa.broken = True
                sa.end_time = times[i]
                break
        if not sa.broken:
            sa.end_time = times[-1]

    # Keep all sweep areas (broken ones stop at end_time, unbroken extend to edge)
    # No cap — return all sweeps for full history export
    result.sweep_areas = result.sweep_areas[-20:]


def _detect_breaker_blocks(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    times: list[float],
    result: SMCResult,
    atrs: list[float],
    max_breakers: int,
):
    """Detect breaker blocks: order blocks that got mitigated and flipped.
    
    A bullish OB that gets mitigated (price breaks below) becomes a bearish breaker.
    A bearish OB that gets mitigated (price breaks above) becomes a bullish breaker.
    """
    n = len(closes)

    for sb in result.structures:
        if sb.bias == BULLISH:
            # Find bearish OB origin (highest candle before this bullish break)
            search_start = max(0, sb.start_index - 10)
            search_end = sb.start_index + 1
            if search_start >= search_end:
                continue
            max_high = max(highs[search_start:search_end])
            max_idx = search_start + highs[search_start:search_end].index(max_high)
            ob_high = highs[max_idx]
            ob_low = lows[max_idx]

            # Check if this OB was previously mitigated (price went above it)
            # then came back — making it a bullish breaker
            mitigated = False
            for i in range(max_idx + 1, sb.end_index):
                if highs[i] > ob_high:
                    mitigated = True
                    break

            if mitigated:
                # Check it's still relevant (price hasn't gone far past it)
                still_valid = False
                for i in range(sb.end_index, min(sb.end_index + 30, n)):
                    if lows[i] <= ob_high and closes[i] >= ob_low:
                        still_valid = True
                        break

                if still_valid:
                    result.breaker_blocks.append(BreakerBlock(
                        high=ob_high,
                        low=ob_low,
                        timestamp=times[max_idx],
                        bar_index=max_idx,
                        bias=BULLISH,
                    ))

        else:  # BEARISH structure break
            search_start = max(0, sb.start_index - 10)
            search_end = sb.start_index + 1
            if search_start >= search_end:
                continue
            min_low = min(lows[search_start:search_end])
            min_idx = search_start + lows[search_start:search_end].index(min_low)
            ob_high = highs[min_idx]
            ob_low = lows[min_idx]

            mitigated = False
            for i in range(min_idx + 1, sb.end_index):
                if lows[i] < ob_low:
                    mitigated = True
                    break

            if mitigated:
                still_valid = False
                for i in range(sb.end_index, min(sb.end_index + 30, n)):
                    if highs[i] >= ob_low and closes[i] <= ob_high:
                        still_valid = True
                        break

                if still_valid:
                    result.breaker_blocks.append(BreakerBlock(
                        high=ob_high,
                        low=ob_low,
                        timestamp=times[min_idx],
                        bar_index=min_idx,
                        bias=BEARISH,
                    ))

    result.breaker_blocks = result.breaker_blocks[-max_breakers:]


def _compute_candle_trends(
    closes: list[float],
    times: list[float],
    int_pivot_highs: list[tuple[int, float, float]],
    int_pivot_lows: list[tuple[int, float, float]],
) -> list[int]:
    """Compute per-candle trend bias based on internal structure.
    
    Returns list of BULLISH/BEARISH for each candle.
    Used for coloring candles green/red based on internal trend.
    """
    n = len(closes)
    trends = [0] * n

    # Build structure break points in order
    trend = 0
    last_high_level = 0.0
    last_low_level = 0.0
    last_high_crossed = True
    last_low_crossed = True

    # Merge pivots chronologically
    all_pivots = []
    for idx, price, ts in int_pivot_highs:
        all_pivots.append((idx, "high", price))
    for idx, price, ts in int_pivot_lows:
        all_pivots.append((idx, "low", price))
    all_pivots.sort(key=lambda x: x[0])

    change_points: list[tuple[int, int]] = []  # (bar_index, new_trend)

    for idx, ptype, price in all_pivots:
        if ptype == "high":
            last_high_level = price
            last_high_crossed = False
        else:
            last_low_level = price
            last_low_crossed = False

    # Re-scan for structure breaks
    last_high_level = 0.0
    last_low_level = 0.0

    for idx, ptype, price in all_pivots:
        if ptype == "high":
            last_high_level = price
            last_high_crossed = False
        else:
            last_low_level = price
            last_low_crossed = False

        # Check crosses in subsequent bars
        if last_high_level > 0 and not last_high_crossed:
            for i in range(idx + 1, min(idx + 10, n)):
                if closes[i] > last_high_level:
                    last_high_crossed = True
                    if trend != BULLISH:
                        trend = BULLISH
                        change_points.append((i, BULLISH))
                    break

        if last_low_level > 0 and not last_low_crossed:
            for i in range(idx + 1, min(idx + 10, n)):
                if closes[i] < last_low_level:
                    last_low_crossed = True
                    if trend != BEARISH:
                        trend = BEARISH
                        change_points.append((i, BEARISH))
                    break

    # Fill trend array
    current_trend = 0
    cp_idx = 0
    for i in range(n):
        while cp_idx < len(change_points) and change_points[cp_idx][0] <= i:
            current_trend = change_points[cp_idx][1]
            cp_idx += 1
        trends[i] = current_trend

    return trends
