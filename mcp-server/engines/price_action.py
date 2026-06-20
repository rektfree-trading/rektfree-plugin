"""
Candlestick / price-action pattern detection over raw OHLC candles.

Pure stdlib (``math`` only) — no ``app.*``, no I/O, no Binance. Every detector
takes plain candle dicts (``{open, high, low, close, ...}``) and is individually
testable. The public entry point is :func:`detect_patterns`, which scans a list
of candles (oldest→newest) and returns a list of detection dicts the tool layer
serializes for the model.

Design notes
------------
- Candlesticks are inherently *relative* — a "long" wick only means something
  versus that candle's own range, and "small" body only versus recent ranges.
  So thresholds are expressed as **ratios** (body/range, wick/range), and the
  few absolute comparisons (engulfing, harami) compare bodies directly.
- Thresholds are module constants so they're easy to audit and tune. They are
  the standard textbook values; each is documented at its definition.
- A pattern detection is *just a shape*. Whether it matters depends on
  **context** (is it at a key level? after a sweep? aligned with structure?) —
  that judgement lives in the skill, not here.
"""

from __future__ import annotations

import math

# ───────────────────────── thresholds (documented) ─────────────────────────
# All thresholds are fractions of a candle's own total range (high - low),
# unless noted. They follow standard candlestick conventions.

# Body is "small" (doji-ish) when it's at most this fraction of the range.
DOJI_BODY_RATIO = 0.10
# Body is "small" for a spinning top / star middle (looser than a doji).
SMALL_BODY_RATIO = 0.30
# A wick is "long" when it's at least this fraction of the range. Used for
# hammer (lower) and shooting star (upper) rejection candles.
LONG_WICK_RATIO = 0.60
# The opposite wick of a pin bar must be at most this fraction of the range
# (a clean hammer has almost no upper wick, a shooting star almost no lower).
SHORT_WICK_RATIO = 0.20
# Marubozu: wicks are tiny on both ends, body fills the candle.
MARUBOZU_WICK_RATIO = 0.05
# Body is "large" (dominant) when it's at least this fraction of the range —
# used to qualify the long candles in three-soldiers / three-crows.
LARGE_BODY_RATIO = 0.60
# Star middle candles must gap/separate; we use a small-body test plus a
# requirement that the third candle closes well into the first candle's body.
STAR_PENETRATION = 0.50  # close must reclaim ≥ half of candle 1's body

# Directions
BULLISH = "bullish"
BEARISH = "bearish"
NEUTRAL = "neutral"


# ───────────────────────── per-candle geometry ─────────────────────────────

def body(c: dict) -> float:
    """Absolute body size |close - open|."""
    return abs(c["close"] - c["open"])


def rng(c: dict) -> float:
    """Total range high - low (guarded ≥ 0)."""
    return max(c["high"] - c["low"], 0.0)


def upper_wick(c: dict) -> float:
    """Distance from the top of the body to the high."""
    return c["high"] - max(c["open"], c["close"])


def lower_wick(c: dict) -> float:
    """Distance from the bottom of the body to the low."""
    return min(c["open"], c["close"]) - c["low"]


def is_bull(c: dict) -> bool:
    """True if the candle closed above its open."""
    return c["close"] > c["open"]


def is_bear(c: dict) -> bool:
    """True if the candle closed below its open."""
    return c["close"] < c["open"]


def body_ratio(c: dict) -> float:
    """Body as a fraction of range (0 when range is 0)."""
    r = rng(c)
    return body(c) / r if r > 0 else 0.0


def _ratio(part: float, c: dict) -> float:
    """Safe ``part / range`` (0 when range is 0)."""
    r = rng(c)
    return part / r if r > 0 else 0.0


# ───────────────────────── single-candle patterns ──────────────────────────

def is_doji(c: dict) -> str | None:
    """Tiny body relative to range → indecision. Returns ``neutral`` or None.

    A doji has open ≈ close. We classify the special long-legged variants
    (hammer/shooting star) separately, so a plain doji here is body-small with
    no single dominant wick.
    """
    if rng(c) <= 0:
        return None
    if body_ratio(c) <= DOJI_BODY_RATIO:
        return NEUTRAL
    return None


def is_marubozu(c: dict) -> str | None:
    """Full-bodied candle with almost no wicks → strong conviction.

    Bullish marubozu (close at/near high) = aggressive buying; bearish
    (close at/near low) = aggressive selling.
    """
    if rng(c) <= 0:
        return None
    if _ratio(upper_wick(c), c) <= MARUBOZU_WICK_RATIO and \
       _ratio(lower_wick(c), c) <= MARUBOZU_WICK_RATIO and \
       body_ratio(c) >= 1 - 2 * MARUBOZU_WICK_RATIO:
        return BULLISH if is_bull(c) else BEARISH
    return None


def is_spinning_top(c: dict) -> str | None:
    """Small body with long wicks on *both* sides → indecision/balance."""
    if rng(c) <= 0:
        return None
    if DOJI_BODY_RATIO < body_ratio(c) <= SMALL_BODY_RATIO and \
       _ratio(upper_wick(c), c) >= 0.25 and _ratio(lower_wick(c), c) >= 0.25:
        return NEUTRAL
    return None


def is_hammer(c: dict) -> str | None:
    """Long lower wick, tiny upper wick → rejection of lower prices (bullish).

    This is the *shape* of a hammer (bullish reversal at a low) and a hanging
    man (bearish reversal at a high) — same geometry, meaning depends on where
    it appears. We return ``bullish`` for the shape; the skill flips it to a
    hanging-man read when it sits at the top of an uptrend.
    """
    if rng(c) <= 0:
        return None
    if _ratio(lower_wick(c), c) >= LONG_WICK_RATIO and \
       _ratio(upper_wick(c), c) <= SHORT_WICK_RATIO and \
       body_ratio(c) <= SMALL_BODY_RATIO:
        return BULLISH
    return None


def is_shooting_star(c: dict) -> str | None:
    """Long upper wick, tiny lower wick → rejection of higher prices (bearish).

    Same geometry as an inverted hammer (bullish-reversal shape at a low). We
    return ``bearish`` for the shape; the skill reads it as an inverted hammer
    when it appears at the bottom of a downtrend.
    """
    if rng(c) <= 0:
        return None
    if _ratio(upper_wick(c), c) >= LONG_WICK_RATIO and \
       _ratio(lower_wick(c), c) <= SHORT_WICK_RATIO and \
       body_ratio(c) <= SMALL_BODY_RATIO:
        return BEARISH
    return None


def single_candle_patterns(c: dict) -> list[tuple[str, str]]:
    """Return all single-candle ``(name, direction)`` matches for candle ``c``.

    Order matters for readability but not correctness — a candle can satisfy
    more than one definition (e.g. a doji that's also a spinning top); we keep
    the most specific and skip the looser duplicate.
    """
    out: list[tuple[str, str]] = []
    m = is_marubozu(c)
    if m:
        out.append(("marubozu", m))
        return out  # marubozu excludes the wick/doji families
    h = is_hammer(c)
    if h:
        out.append(("hammer", h))
    s = is_shooting_star(c)
    if s:
        out.append(("shooting_star", s))
    if h or s:
        return out  # a pin bar is not also a doji/spinning-top
    d = is_doji(c)
    if d:
        out.append(("doji", d))
        return out
    st = is_spinning_top(c)
    if st:
        out.append(("spinning_top", st))
    return out


# ───────────────────────── two-candle patterns ─────────────────────────────

def is_engulfing(prev: dict, cur: dict) -> str | None:
    """Current real body fully engulfs the prior real body → reversal.

    Bullish: prior bearish, current bullish, current body spans the prior body
    (cur.open ≤ prev.close and cur.close ≥ prev.open). Bearish is the mirror.
    """
    if body(cur) <= 0 or body(prev) <= 0:
        return None
    # Bullish engulfing
    if is_bear(prev) and is_bull(cur) and \
       cur["close"] >= prev["open"] and cur["open"] <= prev["close"]:
        return BULLISH
    # Bearish engulfing
    if is_bull(prev) and is_bear(cur) and \
       cur["open"] >= prev["close"] and cur["close"] <= prev["open"]:
        return BEARISH
    return None


def is_harami(prev: dict, cur: dict) -> str | None:
    """Small current body contained inside the prior (large) body → indecision.

    The inverse of engulfing: the prior candle engulfs the current one, and the
    prior body is large. Direction is the *potential reversal* direction (a
    bullish harami forms after a down move, current candle small bullish).
    """
    if body(cur) <= 0 or body(prev) <= 0:
        return None
    if body(cur) >= body(prev):
        return None
    prev_top = max(prev["open"], prev["close"])
    prev_bot = min(prev["open"], prev["close"])
    cur_top = max(cur["open"], cur["close"])
    cur_bot = min(cur["open"], cur["close"])
    contained = cur_top <= prev_top and cur_bot >= prev_bot
    if not contained:
        return None
    if is_bear(prev) and is_bull(cur):
        return BULLISH
    if is_bull(prev) and is_bear(cur):
        return BEARISH
    return None


def is_piercing_or_darkcloud(prev: dict, cur: dict) -> str | None:
    """Piercing line (bullish) / dark cloud cover (bearish) → reversal.

    Piercing line: prior bearish, current opens below prior low (or close) and
    closes back *above the midpoint* of the prior body but below its open.
    Dark cloud cover is the mirror at a top.
    """
    if body(prev) <= 0 or body(cur) <= 0:
        return None
    prev_mid = (prev["open"] + prev["close"]) / 2.0
    # Piercing line (bullish)
    if is_bear(prev) and is_bull(cur) and \
       cur["open"] < prev["close"] and \
       prev_mid < cur["close"] < prev["open"]:
        return BULLISH
    # Dark cloud cover (bearish)
    if is_bull(prev) and is_bear(cur) and \
       cur["open"] > prev["close"] and \
       prev["open"] < cur["close"] < prev_mid:
        return BEARISH
    return None


def is_inside_bar(prev: dict, cur: dict) -> str | None:
    """Current high/low both inside the prior candle's range → compression."""
    if cur["high"] <= prev["high"] and cur["low"] >= prev["low"]:
        return NEUTRAL
    return None


def is_outside_bar(prev: dict, cur: dict) -> str | None:
    """Current range engulfs the prior range (full high/low) → expansion.

    Directional: closes up = bullish outside bar, closes down = bearish.
    """
    if cur["high"] >= prev["high"] and cur["low"] <= prev["low"] and \
       (cur["high"] > prev["high"] or cur["low"] < prev["low"]):
        if is_bull(cur):
            return BULLISH
        if is_bear(cur):
            return BEARISH
        return NEUTRAL
    return None


def two_candle_patterns(prev: dict, cur: dict) -> list[tuple[str, str]]:
    """Return all two-candle ``(name, direction)`` matches ending at ``cur``."""
    out: list[tuple[str, str]] = []
    e = is_engulfing(prev, cur)
    if e:
        out.append(("engulfing", e))
    else:
        # Harami and engulfing are mutually exclusive (one contains the other).
        ha = is_harami(prev, cur)
        if ha:
            out.append(("harami", ha))
    pc = is_piercing_or_darkcloud(prev, cur)
    if pc:
        out.append(("piercing_darkcloud", pc))
    # Inside vs outside are mutually exclusive.
    ib = is_inside_bar(prev, cur)
    if ib:
        out.append(("inside_bar", ib))
    else:
        ob = is_outside_bar(prev, cur)
        if ob:
            out.append(("outside_bar", ob))
    return out


# ───────────────────────── three-candle patterns ───────────────────────────

def is_star(c1: dict, c2: dict, c3: dict) -> str | None:
    """Morning star (bullish) / evening star (bearish) → reversal.

    Morning: c1 long bearish, c2 small body (indecision) gapping down, c3 long
    bullish closing back into the upper half of c1's body. Evening is the
    mirror at a top.
    """
    if body(c1) <= 0 or body(c3) <= 0:
        return None
    c2_small = body_ratio(c2) <= SMALL_BODY_RATIO
    if not c2_small:
        return None
    c1_mid = (c1["open"] + c1["close"]) / 2.0
    # Morning star (bullish)
    if is_bear(c1) and is_bull(c3) and \
       max(c2["open"], c2["close"]) < c1["close"] and \
       c3["close"] >= c1_mid:
        return BULLISH
    # Evening star (bearish)
    if is_bull(c1) and is_bear(c3) and \
       min(c2["open"], c2["close"]) > c1["close"] and \
       c3["close"] <= c1_mid:
        return BEARISH
    return None


def is_three_soldiers_or_crows(c1: dict, c2: dict, c3: dict) -> str | None:
    """Three white soldiers (bullish) / three black crows (bearish) → strong trend.

    Three consecutive large-bodied candles all the same direction, each opening
    within the prior body and closing progressively higher (soldiers) or lower
    (crows).
    """
    bodies_big = all(body_ratio(c) >= LARGE_BODY_RATIO for c in (c1, c2, c3))
    if not bodies_big:
        return None
    # Three white soldiers
    if is_bull(c1) and is_bull(c2) and is_bull(c3) and \
       c2["close"] > c1["close"] and c3["close"] > c2["close"] and \
       c1["close"] > c2["open"] > c1["open"] and \
       c2["close"] > c3["open"] > c2["open"]:
        return BULLISH
    # Three black crows
    if is_bear(c1) and is_bear(c2) and is_bear(c3) and \
       c2["close"] < c1["close"] and c3["close"] < c2["close"] and \
       c1["close"] < c2["open"] < c1["open"] and \
       c2["close"] < c3["open"] < c2["open"]:
        return BEARISH
    return None


def three_candle_patterns(c1: dict, c2: dict, c3: dict) -> list[tuple[str, str]]:
    """Return all three-candle ``(name, direction)`` matches ending at ``c3``."""
    out: list[tuple[str, str]] = []
    st = is_star(c1, c2, c3)
    if st:
        out.append(("star", st))
    sc = is_three_soldiers_or_crows(c1, c2, c3)
    if sc:
        out.append(("three_soldiers_crows", sc))
    return out


# ───────────────────────── orchestration ───────────────────────────────────

# Human-readable names keyed by (pattern_key, direction). Lets the tool emit
# precise labels (e.g. "bullish engulfing", "hanging man") without the engine
# making a context call it can't make.
_LABELS = {
    ("doji", NEUTRAL): "doji",
    ("marubozu", BULLISH): "bullish marubozu",
    ("marubozu", BEARISH): "bearish marubozu",
    ("spinning_top", NEUTRAL): "spinning top",
    ("hammer", BULLISH): "hammer / hanging man",
    ("shooting_star", BEARISH): "shooting star / inverted hammer",
    ("engulfing", BULLISH): "bullish engulfing",
    ("engulfing", BEARISH): "bearish engulfing",
    ("harami", BULLISH): "bullish harami",
    ("harami", BEARISH): "bearish harami",
    ("piercing_darkcloud", BULLISH): "piercing line",
    ("piercing_darkcloud", BEARISH): "dark cloud cover",
    ("inside_bar", NEUTRAL): "inside bar",
    ("outside_bar", BULLISH): "bullish outside bar",
    ("outside_bar", BEARISH): "bearish outside bar",
    ("outside_bar", NEUTRAL): "outside bar",
    ("star", BULLISH): "morning star",
    ("star", BEARISH): "evening star",
    ("three_soldiers_crows", BULLISH): "three white soldiers",
    ("three_soldiers_crows", BEARISH): "three black crows",
}


def _label(key: str, direction: str) -> str:
    return _LABELS.get((key, direction), key.replace("_", " "))


def detect_patterns(candles: list[dict]) -> list[dict]:
    """Scan candles (oldest→newest) and return all pattern detections.

    Each detection is a dict::

        {
          "pattern": "bullish engulfing",   # human label
          "key": "engulfing",               # stable machine key
          "index": 87,                       # index of the *last* candle in the pattern
          "time": 1718000000.0,              # timestamp of that last candle
          "direction": "bullish",
          "span": 2,                          # how many candles the pattern spans
          "high": 65000.0, "low": 64000.0     # the anchoring candle's extremes
        }

    Detections are returned oldest→newest (most recent last). The ``high``/``low``
    are the last candle's extremes so the model can place the pattern on a chart.
    Context (is this at a level? after a sweep?) is intentionally NOT decided
    here — that is the skill's job.
    """
    out: list[dict] = []
    n = len(candles)
    if n == 0:
        return out

    for i in range(n):
        cur = candles[i]
        # Single-candle
        for key, direction in single_candle_patterns(cur):
            out.append(_make(key, direction, i, cur, span=1))
        # Two-candle
        if i >= 1:
            prev = candles[i - 1]
            for key, direction in two_candle_patterns(prev, cur):
                out.append(_make(key, direction, i, cur, span=2))
        # Three-candle
        if i >= 2:
            c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
            for key, direction in three_candle_patterns(c1, c2, c3):
                out.append(_make(key, direction, i, c3, span=3))

    # Stable sort by index keeps multiple hits on the same candle together and
    # the whole list oldest→newest (most recent last).
    out.sort(key=lambda d: (d["index"], d["span"]))
    return out


def _make(key: str, direction: str, index: int, anchor: dict, span: int) -> dict:
    return {
        "pattern": _label(key, direction),
        "key": key,
        "index": index,
        "time": anchor.get("time", 0.0),
        "direction": direction,
        "span": span,
        "high": anchor["high"],
        "low": anchor["low"],
    }


def summarize(candles: list[dict], lookback: int = 10) -> dict:
    """Compact recent-candle summary for the tool payload.

    Returns last close, the recent N-candle net direction, average body/range
    ratio over the lookback, and the current candle's body% and wick ratios.
    """
    if not candles:
        return {}
    last = candles[-1]
    window = candles[-lookback:] if lookback > 0 else candles

    # Net direction over the window: compare last close to window's first open.
    net = last["close"] - window[0]["open"]
    if window[0]["open"] != 0:
        net_pct = net / window[0]["open"] * 100.0
    else:
        net_pct = 0.0
    if net_pct > 0.1:
        direction = BULLISH
    elif net_pct < -0.1:
        direction = BEARISH
    else:
        direction = NEUTRAL

    ratios = [body_ratio(c) for c in window if rng(c) > 0]
    avg_body_ratio = sum(ratios) / len(ratios) if ratios else 0.0

    bulls = sum(1 for c in window if is_bull(c))
    bears = sum(1 for c in window if is_bear(c))

    return {
        "last_close": last["close"],
        "lookback": len(window),
        "net_change_pct": round(net_pct, 4),
        "direction": direction,
        "bull_candles": bulls,
        "bear_candles": bears,
        "avg_body_ratio": round(avg_body_ratio, 4),
        "current_body_pct": round(body_ratio(last) * 100.0, 2),
        "current_upper_wick_ratio": round(_ratio(upper_wick(last), last), 4),
        "current_lower_wick_ratio": round(_ratio(lower_wick(last), last), 4),
    }
