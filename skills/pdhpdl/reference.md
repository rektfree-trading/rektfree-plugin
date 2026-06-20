# PDH / PDL Touch Statistics — Reference Playbook

This skill analyzes how the **previous day's high (PDH)** and **previous day's
low (PDL)** behave as liquidity levels: how often each gets swept, and whether
the sweep reverses (rejection / liquidity grab) or holds (acceptance /
breakout). These statistics ground analysis in what has actually happened for a
specific crypto asset over the sampled window, rather than generic theory.

## Concept

PDH and PDL are among the most-watched intraday reference levels. Yesterday's
high and low are obvious resting places for stop orders and breakout entries, so
price is frequently drawn to them to take liquidity. The key questions a trader
asks are:

1. **Does today reach the prior level at all?** → the **sweep rate**.
2. **When it does, does price reject and come back inside (a liquidity grab to
   fade) or accept and run (a breakout to trade with)?** → **reversal vs hold**.

The level convention here is the **UTC calendar day** (`rth_convention:
utc_day`): PDH/PDL come from yesterday's daily (D1) candle high/low, and the
touch test runs over today's 1H candles. For crypto (24/7) every calendar day
has a prior day; the engine simply walks back to the most recent D1 candle
before today.

## Tool payload

`compute_pdh_pdl_stats` returns:

```
{
  "symbol": "BTCUSDT",
  "window": { "candles", "from", "to", "days", "rth_convention", "note" },
  "pdh": { "n", "sweep_rate", "sweep_count",
           "reversal_rate_when_swept", "hold_rate_when_swept", "avg_touch_time" },
  "pdl": { ...same shape... },
  "outcomes": { "n", "pdh_only_pct", "pdl_only_pct", "both_pct", "neither_pct" },
  "day_of_week": { "Monday": {...}, ... }
}
```

### Sample window — read this first

`window.days` is the **live sample length** (default ~90 days), and `window.note`
restates it. The hosted product computes these same stats over its FULL candle
history, so its dashboard rates will differ from this tool's snapshot. **Always
cite the sample size** (`window.days`, each block's `n`) and treat thin buckets
(a weekday with only a handful of days) with caution.

### Field reference

| Field | Meaning |
|---|---|
| `pdh.sweep_rate` | % of days price reached the previous day's high |
| `pdh.sweep_count` | Raw count of days the high was swept |
| `pdh.reversal_rate_when_swept` | Of swept-PDH days, % that closed back **below** PDH (rejection / failed breakout / liquidity grab) |
| `pdh.hold_rate_when_swept` | Of swept-PDH days, % that closed **at/above** PDH (acceptance / breakout held) |
| `pdh.avg_touch_time` | Average UTC time-of-day the high was first reached |
| `pdl.*` | Symmetric for the previous day's low (reversal = closed back above PDL) |
| `outcomes.pdh_only_pct` | % of days that touched only the high |
| `outcomes.pdl_only_pct` | % that touched only the low |
| `outcomes.both_pct` | % that took both ends (two-sided liquidity raid) |
| `outcomes.neither_pct` | % that stayed inside yesterday's range (inside day) |
| `day_of_week.{d}` | Per-weekday `pdh_pct`, `pdl_pct`, `both_pct`, `neither_pct`, `count` |

Note: `reversal_rate_when_swept` + `hold_rate_when_swept` sum to 100% per side
(every swept day either closed back inside or stayed beyond the level).

## How to interpret

**Sweep rate** (e.g. "PDL swept 68% of days")
- High sweep rate = expect the level to be reached. The level acts as a magnet;
  it is *not* by itself a fade signal — pair it with the reversal rate.

**Reversal rate when swept**
- High (> 60%) = the sweep is usually a **liquidity grab** — price spikes
  through the level, takes stops, and reverses back inside. Fade the sweep:
  enter on the reclaim, stop beyond the wick, target the opposite side / midpoint.
- Low (< 40%) = sweeps usually **hold** — taking the prior level leads to
  acceptance and continuation. Don't fade; trade the breakout retest instead.

**Hold rate when swept** is the complement — a high hold rate is a breakout-prone
asset, a low hold rate is a fade-the-grab asset.

**Side skew**
- If PDH is swept far more than PDL (or reverses far more), the prior **high** is
  the dominant liquidity pool → bias toward upside grabs then bearish reversals.
  Symmetric if PDL dominates.

**Outcome mix**
- High `neither_pct` = frequent **inside days** → mean-reversion regime, smaller
  targets, fade extremes of yesterday's range.
- High `both_pct` = two-sided **raid days** → whipsaw risk; wait for the second
  sweep before committing.

**Day-of-week** — some weekdays run liquidity more than others (e.g. a Monday
gap-fill or a Friday range expansion). Use the per-weekday `count` to weight
confidence.

## Analysis output format

```
PDH / PDL EDGE

SWEEP DYNAMICS:
- PDH: swept X% (n=N) — reversal Y% / hold Z%, avg touch HH:MM UTC
- PDL: swept X% (n=N) — reversal Y% / hold Z%, avg touch HH:MM UTC
- Dominant liquidity side: [high/low] → [directional read]

DAY CLASSIFICATION:
- pdh_only X% / pdl_only X% / both X% / neither X%
- Regime read: [range-bound / breakout-prone / two-sided]

DAY-OF-WEEK EDGE:
- [Standout weekdays]

IMPLICATION FOR CURRENT SETUP:
- [Fade the sweep vs trade the breakout, given the reversal/hold split]

SAMPLE: window.days days, n=N — recent snapshot, not full history
```

Always cite the specific numbers. "PDH gets swept and reverses 71% of the time on
BTCUSDT (n=58)" is far more valuable than "the previous high often gets swept."
