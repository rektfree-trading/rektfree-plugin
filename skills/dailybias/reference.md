# Daily Bias — Reference Playbook

This skill determines the directional bias for the current trading day (or week)
using the TTrades Daily Bias methodology. It is based on how the previous
period's price action relates to the period before it — specifically whether the
previous day closed above / below / inside the prior day's high and low. Knowing
the bias and its draw-on-liquidity target frames every intraday decision.

## Tool payload

`get_daily_bias` returns:

```
{
  "symbol", "timeframe": "1h", "period": "D" | "W",
  "current_bias": "bullish" | "bearish" | "neutral",
  "current_reason": "...",
  "current_prev_high", "current_prev_low",   // DOL levels
  "entries": [ {timestamp, bias, reason, prev_high, prev_low, hit_prev_high, hit_prev_low}, ... ],
  "stats": {
    "bullish": {count, success_rate, close_through_rate},
    "bearish": {count, success_rate, close_through_rate}
  }
}
```

`current_prev_high` / `current_prev_low` are the reference levels for today's
bias (PDH / PDL on daily, PWH / PWL on weekly). All times are unix seconds, UTC.
The tool fetches ~1000 × 1h candles (~41 days), so the stats sample is roughly a
month of daily periods.

---

## Concepts & Definitions

### 1. Previous Day High / Low (PDH / PDL)
The high and low of the **day before yesterday**. These become the reference
levels for today's bias determination. On weekly timeframe these are Previous
Week High (PWH) and Previous Week Low (PWL).

### 2. Bias Determination Rules

At each new trading day, evaluate how **yesterday's** candle related to PDH/PDL:

**Rule 1 — Close Above PDH → Bullish Bias (target PDH).** Yesterday closed above
PDH — strength through the prior high. Expect continuation higher; DOL is PDH.

**Rule 2 — Close Below PDL → Bearish Bias (target PDL).** Yesterday closed below
PDL — weakness through the prior low. Expect continuation lower; DOL is PDL.

**Rule 3 — Failed to Close Above PDH → Bearish Bias.** Yesterday wicked above
PDH but failed to close above it, low stayed above PDL. Failed breakout /
liquidity grab above — smart money sold the high. Bias flips bearish.

**Rule 4 — Failed to Close Below PDL → Bullish Bias.** Yesterday wicked below PDL
but failed to close below it, high stayed below PDH. Failed breakdown / liquidity
grab below — smart money bought the low. Bias flips bullish.

**Rule 5 — Close Inside → Continuation Bias.** Yesterday's high and low stayed
within PDH/PDL (inside bar). No new information — continue with the prior
direction (bullish if the day before closed above its open, else bearish).

**Rule 6 — Outside Bar Closed Inside → No Bias.** Yesterday made a new high AND a
new low vs PDH/PDL but closed between them. Mixed — no directional bias. Neutral.

### 3. Draw on Liquidity (DOL)
The level price is expected to reach given the bias:
- Bullish → DOL is PDH (`current_prev_high`).
- Bearish → DOL is PDL (`current_prev_low`).
- Neutral → no DOL assigned.

The opposite level is the **invalidation** side (PDL when bullish, PDH when
bearish).

### 4. PDH/PDL Raid
When price reaches PDH or PDL during the day, the level is "raided"
(`hit_prev_high` / `hit_prev_low`). A bullish bias whose PDH is hit, or a bearish
bias whose PDL is hit, was correct (a success).

### 5. Close Through
After reaching the DOL, if price **closes** beyond it (not just wicks) that's a
"close through" — stronger confirmation the move is genuine, not a liquidity grab.

---

## Statistics

- **Success rate** = times DOL hit / times bias assigned × 100. Higher = the
  bias methodology is reliable for this market right now.
- **Close-through rate** = times closed through / times DOL hit × 100. Lower
  means the DOL acts more as a reversal / liquidity-grab zone than a breakout.

Read both together: high success + low close-through = the bias reliably *taps*
the level but often reverses there (target it, don't chase a breakout).

---

## Interpretation Rules

1. **Strong signal:** Rules 1–4 (clear price action vs PDH/PDL).
2. **Weak signal:** Rule 5 (inside day — continuation assumption only).
3. **No signal:** Rule 6 (outside bar — conflicting information).

### Confluence with other skills
- **SMC alignment:** bias direction should match the structural trend
  (BOS/CHoCH). Bullish bias + bullish BOS = high confidence. Bias against
  structure = potential reversal — be cautious.
- **Sessions / ICT:** bias is most actionable during London and NY. Asia builds
  the range London sweeps in the direction of the bias. Daily bias sets the DOL
  the ICT session model (Power of 3 / Judas Swing) targets.
- **Key levels:** PDH/PDL overlap with the "pD High / pD Low" in key levels —
  use them as targets and invalidation zones.

### Trading application
1. Determine the daily bias before/at market open.
2. Wait for the killzone (London Open or NY Open).
3. Look for price to sweep **against** the bias (manipulation / Judas Swing).
4. Enter in the bias direction at an OB/FVG after a CHoCH.
5. Target the DOL (PDH bullish, PDL bearish).
6. Invalidate on a close beyond the manipulation extreme / opposite level.

---

## Output Format

```
DAILY BIAS
- Direction: [bullish/bearish/neutral] — [current_reason]
- Draw on liquidity (target): [PDH/PDL] @ [price]
- Invalidation side: [opposite level] @ [price]
- Raided today? [hit_prev_high/hit_prev_low from latest entry]

CONFIDENCE
- Success rate ([direction]): [stats.{direction}.success_rate]% over [count] periods
- Close-through rate: [close_through_rate]% — [genuine breakouts vs grab/reversal zone]

THE PLAN
- Manipulation to expect: [sweep against bias, e.g. London sweeps low when bullish]
- Entry: OB/FVG after CHoCH in the bias direction
- Target: the DOL | Invalidation: close beyond [opposite level]
```
