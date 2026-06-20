---
name: daytype
description: >-
  Day-type classification for crypto. Use whenever the user asks what KIND of
  day an asset tends to print — "day type", "trend day", "range day", "reversal
  day", "what kind of day is it", "is today a trend or chop day", how often each
  day archetype occurs, inside/outside days, power-of-3 days, or day-of-week
  day-type tendencies for a crypto symbol (BTC, ETH, SOL, etc.). Pairs with the
  `compute_day_type_stats` MCP tool, which fetches deep Binance 1H history,
  classifies each UTC day, and returns the archetype/regime distribution.
---

# Day-Type Analysis

You are the analyst. The `compute_day_type_stats` MCP tool (server `rektfree`)
does the computation — it fetches deep 1H Binance candles, reconstructs each
day's session events, classifies every UTC day into one of 11 archetypes (4
regimes) with a deterministic rule engine, and returns the aggregated
distribution. Your job is to **interpret** it into a clear read of what kind of
days this asset prints and how to trade them. Never just echo the numbers.

## Workflow

1. **Fetch.** Call `compute_day_type_stats` with the `symbol` (e.g. `BTCUSDT`),
   and `days` if the user names a window. Crypto only — forex pairs (containing
   `_`) return an error.
2. **Interpret.** Read the payload against the rules in
   [reference.md](reference.md) — the archetype/regime taxonomy and how to turn
   each into a stance.
3. **Synthesize.** Produce the structured output below. Lead with the dominant
   regime (the most actionable read), then the top archetypes, then day-of-week
   edges and what `today` implies.

## Sample-window caveat (state this every time)

The tool samples only the **last ~N days** it fetches live (`window.days`,
default ~90), NOT the full history the hosted dashboard classifies. So:
- Always cite the sample size (`day_types.n`).
- Treat the distribution as a **recent snapshot**, not the long-run truth.
- Discount any archetype with only a handful of occurrences.
- D1 candles are **synthesised from 1H bars**, so inside/outside-day edges can
  differ slightly from the true daily candle.

## Payload key

- `day_types.n` — number of classified days (the denominator for every pct).
- `day_types.regimes.{trend,london_reverse,high_volatile,rare}` — `count` and
  `pct` of days in each regime.
- `day_types.archetypes` — list (sorted by pct) of the 11 archetypes, each with
  `pct`, `count`, `avg_range` (USDT), `avg_range_pct`, `last_seen_date`.
- `day_types.by_day_of_week.{weekday}` — the `top_archetype` / `top_regime` and
  `count` for that weekday.
- `today` — the latest day's full classification (`archetype`, `regime`,
  `net_direction`, `hod_session`/`lod_session`, sweep flags, `expansion_factor`,
  `rules_matched`).

## Output shape

```
REGIME MIX
- trend X% | london_reverse Y% | high_volatile Z% | rare W%
- One-line character read (trend-day asset / reversal-prone / chop-prone)

TOP ARCHETYPES
- archetype: X% (avg range R%) — what it implies and how to trade it
- (repeat for the top 2–3 by share)

DAY-OF-WEEK EDGE
- Standout weekdays (e.g. "Tuesdays lean power_of_3_short")

TODAY
- today.archetype (regime) — what to expect for the current session

SAMPLE: day_types.n days over window.days — recent snapshot, not full history
```

## Interpretation guardrails

- **Regime first, archetype second.** A high `high_volatile` share means expand-
  and-run days dominate (don't fade first moves); high `london_reverse` means
  London sweeps then reverses (fade the sweep); high `rare`/`consolidation_drift`
  means chop (mean-revert, tighten targets).
- **Power-of-3 days need a tight Asia** — when `power_of_3_long/short` lead,
  watch for the Asia accumulation → London sweep → distribution sequence.
- **inside_day / outside_day** are about yesterday's range: many inside days =
  compression building (breakout pending); outside days = expansion/volatility.
- **Anchor every call to sample size.** Don't state a 100% weekday tendency off
  3 days as if it were law.
- **`today` is one sample.** Use it as context, not a guarantee.

See [reference.md](reference.md) for the complete archetype definitions and rules.
