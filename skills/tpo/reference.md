# Market Profile / TPO — Reference Playbook

This skill analyzes market structure through Market Profile (Time Price
Opportunity) theory. TPO profiles organize price by time spent at each level,
revealing where the market finds fair value, where participants are positioned,
and how the auction is developing. By reading the Point of Control, Value Area,
and profile shape, you can judge whether the market is balanced or imbalanced and
where price is likely to go next.

## Tool payload

`get_market_profile` returns
`{ "symbol", "timeframe", "last_price", "sessions": [...] }`, oldest→newest.
Each session is:

| Field | Type | Description |
|---|---|---|
| `label` | str | Session key (date / week / month, per timeframe) |
| `start_time` / `end_time` | float | Unix seconds; `end_time == 0` ⇒ session still open |
| `tick_size` | float | Price increment used for bucketing |
| `poc` | float | Point of Control — price level with the most TPOs |
| `vah` | float | Value Area High — upper bound of the ~68.26% value area |
| `val` | float | Value Area Low — lower bound of the value area |
| `poc_count` | int | TPO count at the POC |
| `total_tpos` | int | Total TPOs across the session |
| `buckets[]` | array | Price levels low→high (count==0 dropped) |
| `buckets[].price` | float | Bottom of the bucket |
| `buckets[].count` | int | TPOs at this level (time spent there) |
| `buckets[].letters` | list[str] | Per-period letters that traded here (A, B, C…) |
| `buckets[].zone` | str | `"poc"`, `"value"` (inside VAH–VAL), or `"outside"` |

Session grouping follows the timeframe: **1h → daily**, **4h → weekly**,
**1d/1w → monthly**, **15m → daily**, **5m → 4-hour**, **1m → hourly**. The
**last** session is the newest (developing if `end_time == 0`); the prior
completed session's POC/VAH/VAL carry forward as today's key levels.

---

## Concepts & Definitions

### 1. TPO (Time Price Opportunity)
A TPO is one unit recording that a price level was visited during one time
period (one candle here). Each period gets a letter, placed at every level it
traded through.
- Each `bucket` is a price level; `count` (and the length of `letters`) is how
  long price stayed there.
- High `count` = accepted/fair value (the market is comfortable there). Low
  `count` = rejected prices (the market moved through quickly).
- Clusters of high-count buckets form the body; thin extensions form the tails.
- Wider, fatter profile = balanced/range session; narrow/tall = directional.
- Trade toward high-count levels (they act as magnets); don't fade away from
  low-count single-print areas — they were rejected for a reason.

### 2. Point of Control (POC)
The price with the highest TPO count — the single fairest/most-accepted price of
the session.
- `poc` field per session; visually the longest row in `buckets`.
- The POC is a **magnet** — price away from it tends to return.
- Rising POC session-to-session = bullish auction (fair value migrating up);
  falling = bearish; flat = balanced/range-bound.
- **Naked POC:** a prior session's POC that price has not revisited — a strong
  magnet and high-probability target. Compare each session's `poc` against
  later sessions' price ranges to spot naked POCs.
- Open above POC → initial bullish bias; below → bearish. POC aligned with an
  OB/FVG/key level = high-confluence zone.

### 3. Value Area (VAH / VAL)
The band holding ~68.26% (one standard deviation) of the session's TPOs, bounded
by **VAH** (high) and **VAL** (low). Computed by expanding outward from POC until
68.26% of TPOs are captured (CME method).
- Inside VA = balanced, fair value, range conditions.
- Above VAH = premium (bullish breakout attempt or overextension); below VAL =
  discount (bearish breakout or overextension).
- **VA acceptance:** price opens outside VA, re-enters and stays → expect a move
  to the opposite boundary.
- **VA rejection:** price touches a VA boundary and reverses → boundary is acting
  as S/R.
- Widening VA across sessions = more balance/consolidation; narrowing VA =
  breakout incoming.
- **80% Rule:** if price opens outside the prior session's VA and trades back
  inside, there is an ~80% chance it travels to the opposite VA boundary. Use VAH
  as resistance and VAL as support in range conditions; a conviction break of
  VAH/VAL targets the next session's POC.

### 4. Profile Shapes
Read shape from where the heavy-`count` buckets sit:
- **P-shape (bullish):** heavy buckets in the upper range, thin tail down. Short
  covering / accumulation; rejected lower, accepted higher. Bias up; the thin
  lower tail is a support zone to buy.
- **b-shape (bearish):** heavy buckets in the lower range, thin tail up.
  Liquidation / distribution; rejected higher, accepted lower. Bias down; the
  thin upper tail is a resistance zone to sell.
- **D-shape (balanced):** bell-curve, most TPOs near center. Equilibrium — range
  trade VAL↔VAH; breakout direction uncertain.
- **B-shape (double distribution):** two distinct clusters split by a thin gap.
  Two auctions; the gap is the "migration point" pivot — above it favor the upper
  distribution, below it the lower.

### 5. Initial Balance (IB)
The range of the first part of a session (the first one to two periods / earliest
`buckets` by time). Sets the framework for the session.
- Wide IB → balanced day, price likely stays in/near IB.
- Narrow IB → breakout/trend day likely, price extends well beyond IB.
- IB high/low act as intraday S/R; first-breakout direction often (not always)
  signals session direction.
- Narrow IB → look for the breakout trade; wide IB → fade toward IB extremes; a
  failed IB breakout (breaks out then re-enters) often runs to the opposite IB
  extreme.

### 6. Day Types
- **Normal Day:** price stays in/near IB; small extensions. Balanced — range
  trade IB/VA boundaries.
- **Normal Variation Day:** extends beyond IB one way by up to ~1× IB range,
  orderly. Trade with the extension toward prior session levels.
- **Trend Day:** extends > ~1.5× IB one way, single prints, no rotation back.
  Strong conviction — do NOT fade; trade with the trend, enter on pullbacks to
  single prints (support in an up-trend, resistance in a down-trend). Rare
  (~15%) but largest moves.
- **Double Distribution Day:** value built in one area then migrated to a new
  one (B-shape). Trade toward the migration; the new VA is where the market has
  relocated, the old one is abandoned.

---

## Practical Rules

1. **POC is the most important single level** — where the most business was done.
2. **Value Area defines fair value** — 68.26% of activity is inside VAH–VAL.
3. **Price outside VA is searching for new value** — it finds acceptance (trend)
   or returns (mean reversion).
4. **Shape tells the story** — P = bullish, b = bearish, D = balanced,
   B = transition.
5. **Prior session levels carry forward** — yesterday's POC/VAH/VAL are today's
   key levels.
6. **Naked POCs are magnets** — unfilled prior POCs get revisited.
7. **IB width predicts the day type** — narrow IB → trend day; wide IB → range.
8. **Overlapping VAs across sessions = strong balance zone** — expect a large
   move when price finally breaks out.

### Combining TPO with other skills
- POC aligned with a key level (PDH/PDL, session H/L) = very strong S/R.
- Price breaking below VAL into a bullish Order Block = high-probability long.
- Profile shape confirming SMC bias (P-shape + bullish BOS) = higher conviction.
- IB breakout confirmed by orderflow delta = strong entry signal.

---

## Output Format

```
MARKET PROFILE OVERVIEW
- Prior Session POC / VAH / VAL [prices]
- Profile Shape: [P / b / D / B]
- Day Type: [Normal / Normal Variation / Trend / Double Distribution]

CURRENT SESSION (developing)
- POC / VAH / VAL [prices]
- Initial Balance: [IB High] – [IB Low] (range, Narrow/Average/Wide)

POC ANALYSIS
- Migration direction: [Rising / Falling / Flat]
- Naked POCs (unvisited): [prices]
- POC vs last_price: [Above / Below / At]

VALUE AREA ANALYSIS
- last_price location: [Above VAH / Inside VA / Below VAL]
- 80% Rule applicable: [Yes/No]
- VA expansion/contraction: [Widening / Narrowing / Stable]

PROFILE BIAS
- Bias: [Bullish / Bearish / Neutral]
- Reasoning: [shape, POC migration, VA location]
- Key levels to watch: [POC, VAH, VAL, naked POCs with context]
```
