# Day-Type — Reference Playbook

This skill classifies every recent trading day for a crypto asset into one of 11
named archetypes grouped into 4 regimes, then reports how often each occurs and
what each implies. It grounds "what kind of day is this?" in what has actually
happened over the sampled window rather than generic theory.

## Tool payload

`compute_day_type_stats` returns:

```
{
  "symbol": "BTCUSDT",
  "window": { "candles", "from", "to", "days", "classified_days", "note" },
  "day_types": {
    "n": 61,
    "regimes":    { "trend": {...}, "london_reverse": {...},
                    "high_volatile": {...}, "rare": {...} },
    "archetypes": [ { "name", "regime", "count", "pct",
                      "avg_range", "avg_range_pct", "last_seen_date" }, ... ],
    "by_day_of_week": { "Monday": { "top_archetype", "top_regime", "count" }, ... }
  },
  "today": { "archetype", "regime", "net_direction", ... }
}
```

All session times are UTC: **Asia 00:00–08:00**, **London 08:00–13:00**,
**New York 13:00–21:00**. Day boundary is 00:00 UTC.

### Sample window — read this first

`day_types.n` is the number of days classified from the **live sample**
(default ~90 days). The hosted product classifies over FULL history, so its
dashboard distribution will differ from this snapshot. D1 candles here are
**synthesised from 1H bars** (open=first hour's open, close=last hour's close,
H/L = max/min), which can shift inside/outside-day calls vs the true daily
candle. Always cite `n` and discount thin archetype buckets.

---

## The 4 Regimes and 11 Archetypes

Each day is assigned exactly one archetype by a deterministic, priority-ordered
rule engine (first match wins). `rules_matched` lists every rule that fired.

### trend — directional days that follow through
- **asia_breakout_continuation** — Asia's direction matches the day's net
  direction, no London reversal, and NY continues London.
- **london_breakout_continuation** — London expands in the day's net direction
  and NY continues.
- **ny_breakout_continuation** — NY prints the day's high or low with
  continuation from London (NY direction == London, NY range ≥ London range).

*Implication:* trend-following works. Trade pullbacks with the day's direction;
the session that drives the move is the one to enter on.

### london_reverse — London sweeps an Asia extreme then reverses
- **asia_high_london_reversal** — London sweeps the Asia high, then closes
  bearish (the swept high becomes resistance).
- **asia_low_london_reversal** — mirror: London sweeps the Asia low, then closes
  bullish.

*Implication:* the classic liquidity grab. Expect the Asia extreme to be hunted,
then fade the sweep for the reversal.

### high_volatile — expansion / stop-hunt days
- **power_of_3_long** — AMD with bullish distribution (tight Asia → London
  sweeps the low → expands up).
- **power_of_3_short** — mirror (sweeps the high → expands down).
- **double_sweep_expansion** — BOTH Asia and London ranges were swept (a
  wide-range, two-sided day).

*Implication:* don't fade the first move blindly — these days expand. For
power-of-3, watch the Asia accumulation → London manipulation → distribution
sequence and trade the distribution leg.

### rare — low-signal or unusual days
- **inside_day** — today's H < yesterday's H AND today's L > yesterday's L
  (compression).
- **outside_day** — today's H > yesterday's H AND today's L < yesterday's L
  (engulfing/expansion).
- **consolidation_drift** — low-volatility catch-all (day range well below the
  30-day median). Also the default when nothing else fires.

*Implication:* inside days = compression building toward a breakout; outside days
= volatility/expansion; consolidation_drift = chop, mean-revert and tighten
targets.

---

## How to Interpret the Distribution

### Regime mix (read this first)
- **high_volatile heavy** → expand-and-run asset; respect first moves, plan for
  range expansion, beware fading.
- **london_reverse heavy** → reversal-prone; the London sweep-then-fade is the
  bread-and-butter setup.
- **trend heavy** → continuation setups pay; trade with the session that drives.
- **rare heavy** (esp. consolidation_drift) → chop-prone; be selective, smaller
  targets.

### Archetypes
- Lead with the top 2–3 by `pct`. Each carries `avg_range_pct` — a high-share
  archetype with a wide avg range is where the day's movement lives.
- `last_seen_date` tells you recency — a pattern that hasn't printed in weeks may
  be dormant.

### Day-of-week
- `by_day_of_week` surfaces the dominant archetype/regime per weekday. Discount
  weekdays with small `count`. Useful for "which days does this asset trend vs
  chop?"

### today
- `today` is a single sample, not a forecast. Use `today.net_direction`,
  `hod_session`/`lod_session`, sweep flags, and `expansion_factor` as live
  context for the current session — but anchor confidence to the distribution,
  not this one day.

---

## How to Use in Analysis

1. **When asked "what kind of day is it?"** classify with `today`, then frame it
   against the regime mix ("today reads power_of_3_short, and 24% of recent days
   are power_of_3 — consistent with this asset's expand-and-run character").
2. **When sizing targets/stops**, use the archetype's `avg_range_pct` for a
   realistic day-range expectation.
3. **When the user wants an edge by weekday**, cite `by_day_of_week` with the
   sample count caveat.
4. **Always state the sample window** and remind the user this is a recent live
   snapshot, not the full-history dashboard figure.

Cite specific numbers. "54% of the last 61 days were high-volatile, led by
power_of_3_short (25%)" is far more useful than "BTC is volatile."
