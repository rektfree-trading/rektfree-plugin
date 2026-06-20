# Session Statistics — Reference Playbook

This skill analyzes the three trading sessions (Asia, London, New York) and the
empirical rates that govern how they interact: session ranges, sweep rates,
NY continuation, and the Power-of-3 pattern. These statistics ground analysis in
what has actually happened for a specific crypto asset over the sampled window,
rather than generic theory.

## Tool payload

`compute_session_stats` returns:

```
{
  "symbol": "BTCUSDT",
  "window": { "candles", "from", "to", "days", "note" },
  "sessions": { "asia": {...}, "london": {...}, "new_york": {...} },
  "sweeps": { "asia_sweep": {...}, "london_sweep": {...} },
  "ny_continuation": {...},
  "power_of_3": {...},
  "day_of_week": { "asia": [...], "london": [...], "new_york": [...] }
}
```

All session times are UTC: **Asia 00:00–08:00**, **London 08:00–13:00**,
**New York 13:00–21:00** (the 21:00–24:00 window is not part of any session).

### Sample window — read this first

`window.days` is the **live sample length** (default ~90 days), and `window.note`
restates it. The hosted product computes these same stats over its FULL candle
history (often a year or more), so its dashboard rates will differ from this
tool's snapshot. **Always cite the sample size** and treat thin buckets (a
weekday with only a handful of sessions) with caution.

### Field reference

| Field | Meaning |
|---|---|
| `sessions.{s}.avg_range` | Mean H−L per session, in quote units (USDT) |
| `sessions.{s}.avg_range_pct` | Mean (H−L)/low × 100 — comparable across assets/price regimes |
| `sessions.{s}.bullish_pct` / `bearish_pct` | % of sessions that closed above / below their open |
| `sessions.{s}.avg_bull_range` / `avg_bear_range` | Avg range on up vs down sessions |
| `sweeps.asia_sweep` | Did **London** take out the **Asia** high or low? |
| `sweeps.london_sweep` | Did **NY** take out the **London** high or low? |
| `sweeps.{x}.sweep_rate` | % of days the sweep occurred (denominator = days the prior session existed) |
| `sweeps.{x}.swept_high` / `swept_low` / `swept_both` | Count by which side was taken |
| `sweeps.{x}.reversal_rate` | Of the sweeps, % that closed back inside the prior range (the fade) |
| `ny_continuation.continuation_rate` | % of days NY closed the same direction as London |
| `ny_continuation.reversal_rate` | % of days NY went the opposite way |
| `power_of_3.occurrence_rate` | % of eligible days (Asia+London present) the AMD pattern formed |
| `power_of_3.success_rate` | Of patterns, % where distribution ran ≥1.5× the Asia range |
| `power_of_3.swept_high` / `swept_low` | Manipulation side (which Asia extreme London swept) |
| `power_of_3.avg_asia_range_pct` | Avg Asia range as % of the average daily range (tightness) |
| `day_of_week.{s}` | Per-weekday list of `avg_range`, `avg_range_pct`, `bullish_pct`, `count` |

---

## Concepts & Definitions

### 1. Trading Sessions

**Asia (00:00–08:00 UTC)** — typically the lowest-volatility session.
Establishes the day's initial range and acts as the **accumulation** phase in
Power of 3. The Asia high/low become key reference levels for the rest of the
day.

**London (08:00–13:00 UTC)** — highest volatility and volume; often sets the
day's directional bias. Frequently sweeps the Asia range (takes out Asia high or
low) before trending. The London-open killzone (07:00–09:00 UTC) is the most
significant entry window.

**New York (13:00–21:00 UTC)** — second-highest volatility. Can continue
London's move OR reverse it. The NY-open killzone (13:00–14:00 UTC) is the key
window. If NY fails to continue London, it is likely a reversal day.

### 2. Killzones

Time windows where institutional activity peaks — optimal entry windows.
- **London Open (07:00–09:00 UTC):** look for a sweep of Asia H/L, then CHoCH
  and entry at an OB/FVG.
- **NY Open (13:00–14:00 UTC):** look for continuation of London's move OR a
  reversal. Confluence with the London session H/L adds significance.

### 3. Power of 3 (AMD)

- **Accumulation (Asia):** smart money accumulates during low volatility. A
  tight Asia range (< 50% of the average daily range) is the springboard.
- **Manipulation (London open):** price sweeps one side of the Asia range (stop
  hunt) — the fake move that traps retail. The `swept_high`/`swept_low` counts
  tell you which side gets hunted more.
- **Distribution (London/NY):** the real directional move away from the
  manipulation zone. "Success" = the move ran ≥1.5× the Asia range.

### 4. Session Relationships

- London takes out Asia **high** then closes below → bearish signal.
- London takes out Asia **low** then closes above → bullish signal.
- NY **continues** London → same bias, enter on pullbacks.
- NY **reverses** London → opposite bias, session H/L rejection.
- Prior-session H/L act as S/R for the current session.

---

## How to Interpret the Rates

### Session ranges
- Rank the three sessions by `avg_range_pct` to find where the movement is.
  Crypto NY is often the most volatile; Asia the least.
- Compare `avg_bull_range` vs `avg_bear_range` — a large skew means down moves
  (or up moves) are sharper, which informs target/stop sizing.

### Sweep rates ("London sweeps Asia X% of days")
- **High sweep rate** = *expect the sweep* — position for the post-sweep move.
  Whether you fade or follow depends on `reversal_rate`.
- **Which side gets swept** (`swept_high` vs `swept_low`) reveals directional
  bias: more high-sweeps → more bearish reversals after; more low-sweeps → more
  bullish reversals after.
- **`reversal_rate`** is the real edge: high reversal rate = classic liquidity
  grab, fade the sweep; low reversal rate = sweeps run, don't fade blindly.

### NY continuation rate
- **> 60%** = NY usually follows London — trade continuation setups.
- **< 50%** = NY frequently reverses London — watch for reversal signals at the
  NY-open killzone.

### Power of 3
- **`occurrence_rate`** tells you how often the asset even sets up the AMD cycle
  (needs a tight Asia). Low occurrence → don't force the framing.
- **`success_rate`** is how often the distribution actually delivered. Note: a
  short live sample can produce a low success rate by chance — anchor to the
  sample size.

### Day-of-week
- Surface the standout days: the widest-range weekday (best for movement), the
  tightest (chop risk), and any strong direction skew. Discount weekdays with
  small `count`.

---

## How to Use in Analysis

1. **When discussing session dynamics**, cite the actual sweep rate, not generic
   "London often sweeps Asia." e.g. "London sweeps Asia 70% of days (high 36 /
   low 23), reversing 57% of the time."
2. **When calling NY direction**, reference the continuation rate.
3. **Before invoking Power of 3**, check `occurrence_rate` — only frame the day
   as AMD if the pattern actually forms often for this asset.
4. **When timing entries**, map to killzones (London 07:00–09:00, NY
   13:00–14:00 UTC).
5. **Always state confidence relative to sample size** — and remind the user
   this is a recent live snapshot, not the full-history dashboard figure.

Cite specific numbers. "London sweeps Asia 70% of days on BTCUSDT over the last
90 days" is far more useful than "London usually sweeps Asia."

---

## Analysis Output Format

```
SESSION VOLATILITY
- Asia: avg_range_pct% | London: %  | NY: %  (ranked most → least)
- Where to trade for movement vs where to expect chop

SWEEP DYNAMICS
- London sweeps Asia: X% of days (high Hx / low Lx / both Bx) — reversal Y%
- NY sweeps London: X% — reversal Y%
- Directional read from the side skew

CONTINUATION vs REVERSAL
- NY continues London: X% → [trade continuation / watch reversal]

POWER OF 3
- Occurrence: X% of eligible days, success: Y%
- Manipulation side skew (high/low) and implication

DAY-OF-WEEK EDGE
- Widest / tightest range days, notable direction skews (discount small samples)

SAMPLE: window.days days, N sessions — recent live snapshot, not full history
```
