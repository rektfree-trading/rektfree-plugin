# Price Action — Reference Playbook

This skill reads raw candlestick price action: it detects the standard
candlestick patterns on recent candles and describes what price has actually
done. Candlestick patterns are micro-structure — they reveal the short-term
battle between buyers and sellers. But they are **only meaningful in context**:
a pattern at a key level, after a liquidity sweep, or aligned with the larger
structure carries weight; the same pattern in the middle of nowhere is noise.

## Tool payload

`get_price_action` returns
`{ "symbol", "timeframe", "last_price", "summary": {...}, "patterns": [...] }`.

`summary`:

| Field | Meaning |
|---|---|
| `last_close` | Most recent close |
| `direction` | Net direction over the lookback (bullish/bearish/neutral) |
| `bull_candles` / `bear_candles` | Count of up/down candles in the lookback |
| `avg_body_ratio` | Average body/range over the lookback (conviction proxy) |
| `current_body_pct` | Current candle body as % of its range |
| `current_upper_wick_ratio` / `current_lower_wick_ratio` | Current candle wicks as fraction of range |

Each entry in `patterns`: `{ pattern, key, index, time, direction, span, high,
low }`. `index` is the position of the *last* candle in the pattern; `time` is
its timestamp; `span` is how many candles it covers (1/2/3); `high`/`low` are
that candle's extremes (use them to place the pattern and check for level
confluence). Patterns are ordered oldest→newest (most recent last, capped ~20).

---

## Pattern definitions

### Single-candle

- **Doji** — open ≈ close (tiny body, < ~10% of range). Indecision; buyers and
  sellers in balance. At a key level / after a trend = potential reversal.
- **Hammer / Hanging man** — long lower wick (≥ ~60% of range), tiny upper wick,
  small body near the top. *Rejection of lower prices.* A **hammer** at the
  bottom of a down move = bullish reversal; the identical shape at the top of an
  up move is a **hanging man** = bearish warning. The tool reports the shape
  (bullish); you flip it by location.
- **Shooting star / Inverted hammer** — long upper wick, tiny lower wick, small
  body near the bottom. *Rejection of higher prices.* A **shooting star** at a
  top = bearish reversal; the same shape at a bottom is an **inverted hammer** =
  potential bullish reversal. Tool reports the shape (bearish); flip by location.
- **Marubozu** — full body, almost no wicks. Strong conviction: bullish (close
  at high) = aggressive buying, bearish (close at low) = aggressive selling.
- **Spinning top** — small body with long wicks on *both* sides. Indecision,
  similar to a doji but with a real (small) body.

### Two-candle

- **Bullish / Bearish engulfing** — the current real body fully engulfs the
  prior real body, in the opposite direction. The strongest two-candle reversal
  signal — momentum has flipped.
- **Bullish / Bearish harami** — the inverse: a small current body contained
  inside the prior (large) body. Loss of momentum / indecision after a move;
  weaker than engulfing, needs confirmation.
- **Piercing line / Dark cloud cover** — **Piercing line** (bullish): after a
  down candle, the current candle opens lower but closes back above the midpoint
  of the prior body. **Dark cloud cover** (bearish) is the mirror at a top.

### Three-candle

- **Morning star / Evening star** — **Morning star** (bullish): long bearish
  candle, then a small indecision candle gapping down, then a long bullish
  candle closing back into the upper half of candle 1. **Evening star** is the
  bearish mirror at a top. Three-candle reversals — more reliable than single
  candles.
- **Three white soldiers / Three black crows** — three consecutive large-bodied
  candles in the same direction, each opening within the prior body and closing
  progressively further. Strong trend / continuation (or exhaustion if very
  extended).

### Range / structure

- **Inside bar** — current candle's high and low are both within the prior
  candle's range. Compression / coiling — a break of either side is the signal,
  not the inside bar itself.
- **Outside bar** — current range engulfs the prior range on both ends.
  Expansion; often a sweep of both sides' liquidity. Directional by close.

---

## Detection thresholds (as implemented)

All ratios are fractions of a candle's own range (`high - low`):

- Doji body ≤ **0.10** of range; small-body (spinning top / star middle) ≤ **0.30**.
- "Long" wick (hammer/star) ≥ **0.60**; the opposite wick must be ≤ **0.20**.
- Marubozu: both wicks ≤ **0.05** of range.
- Three-soldiers/crows: each body ≥ **0.60** of range.
- Engulfing / harami / piercing compare *bodies* directly (no ratio).

These are the standard textbook values — treat detections as candidates, not
verdicts.

---

## The context rule (most important)

**Price-action patterns only matter WITH context.** Before you call a pattern
meaningful, confirm at least one of:

1. **At a key level** — the pattern's `high`/`low` sits on a daily/weekly/monthly
   or session level (cross-reference the levels skill). A hammer at PDL is a
   signal; a hammer mid-range is noise.
2. **After a liquidity sweep** — the candle wicked beyond a prior swing high/low
   (grabbed stops) then rejected. A bullish engulfing right after a sweep of the
   lows is high-quality.
3. **Aligned with structure (SMC)** — the pattern agrees with the larger trend
   or fires at an order block / FVG / after a CHoCH. A bearish engulfing into a
   bearish OB in a bearish trend is a clean continuation/entry trigger.

If none of those hold, the pattern is **unconfirmed** — say so. Reversal
patterns also need a *prior move to reverse* (check the summary `direction`); an
"evening star" with no uptrend in front of it is not a reversal.

---

## How to interpret

### Trending price action
- Consecutive same-direction candles, growing range, high `avg_body_ratio` =
  strong trend. Three soldiers/crows and marubozus confirm it.
- Pullbacks smaller than impulses = healthy trend → continuation entries.

### Ranging / indecision
- Alternating candles, dojis, spinning tops, inside bars, low `avg_body_ratio` =
  no clear bias. Fade extremes or wait for a break.

### Reversal price action
- Large move → rejection candle (pin bar / engulfing / star) **at a key level
  with a sweep** = counter-trend setup with a tight stop beyond the extreme.

---

## Output Format

```
RECENT PRICE ACTION ([symbol] [timeframe])
- Direction: [trending up/down / ranging / reversing]  (from summary)
- Last close: [price] | recent bull/bear: [n]/[n] | avg body: [ratio]
- Current candle: body [x]% | upper wick [r] | lower wick [r]

KEY PATTERNS (recent, by significance)
- [pattern] @ [time/price] → [what it implies] | context: [at level / after sweep / mid-range = noise]
- ...

READ
- Conviction vs indecision: [marubozu/engulfing = momentum | doji/inside = wait]
- Confirmed signals: [only those at a level / sweep / structure]
- What to watch: [the level or break that validates or kills the read]
```
