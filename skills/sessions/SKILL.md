---
name: sessions
description: >-
  Session statistics for crypto. Use whenever the user asks about trading
  session behavior (Asia/London/New York), session ranges or volatility, sweep
  rates ("how often does London sweep Asia", "does NY sweep London"), NY
  continuation vs reversal, the Power of 3 / AMD pattern, killzones, or
  day-of-week edges for a crypto symbol (BTC, ETH, SOL, etc.). Pairs with the
  `compute_session_stats` MCP tool, which fetches deep Binance 1H history and
  returns the aggregated session stats.
---

# Session Statistics Analysis

You are the analyst. The `compute_session_stats` MCP tool (server `rektfree`)
does the computation — it fetches deep 1H Binance candles, buckets them into
Asia/London/New York sessions, runs the detectors, and returns aggregated rates.
Your job is to **interpret** them into a clear, decision-oriented read of
session dynamics. Never just echo the numbers.

## Workflow

1. **Fetch.** Call `compute_session_stats` with the `symbol` (e.g. `BTCUSDT`),
   and `days` if the user names a window. Crypto only — forex pairs (containing
   `_`) return an error.
2. **Interpret.** Read the payload against the rules in
   [reference.md](reference.md) — the session playbook (killzones, Power of 3,
   how to read sweep rates and continuation rates as edges).
3. **Synthesize.** Produce the structured output below. Lead with the most
   actionable edge (usually the dominant sweep rate or session-volatility
   ranking); a trader should be able to act on it.

## Sample-window caveat (state this every time)

The tool samples only the **last ~N days** it fetches live (`window.days`,
default ~90), NOT the full history the hosted dashboard aggregates. So:
- Always cite the sample size (`window.days`, session counts).
- Treat these as a **recent snapshot**, not the long-run truth — the dashboard's
  figures will differ.
- Be cautious with thin samples (e.g. a day-of-week bucket with <8 sessions).

## Payload key

- `sessions.{asia,london,new_york}` — `avg_range`, `avg_range_pct`,
  `bullish_pct`/`bearish_pct`. Range% is comparable across price regimes; raw
  range is in quote units (USDT).
- `sweeps.asia_sweep` — did **London** sweep the **Asia** H/L? `sweep_rate` is
  the % of days it happened; `swept_high`/`swept_low`/`swept_both` show which
  side; `reversal_rate` is how often the sweep closed back inside (the fade).
- `sweeps.london_sweep` — did **NY** sweep the **London** H/L? Same fields.
- `ny_continuation` — `continuation_rate` (NY same direction as London) vs
  `reversal_rate`.
- `power_of_3` — `occurrence_rate` (how often the AMD pattern formed),
  `success_rate` (how often distribution ran ≥1.5× the Asia range),
  `swept_high`/`swept_low` (manipulation side).
- `day_of_week.{session}` — per-weekday `avg_range`, `avg_range_pct`,
  `bullish_pct`.

## Output shape

```
SESSION VOLATILITY
- Ranking by avg_range_pct (most → least volatile)
- Which session to trade for movement / which to expect chop

SWEEP DYNAMICS
- London sweeps Asia: X% of days (high Hx / low Lx) — reversal rate Y%
- NY sweeps London: X% — reversal rate Y%
- Directional read: which side gets hunted more

CONTINUATION vs REVERSAL
- NY continues London: X% → trade continuation / watch for reversal

POWER OF 3
- Occurrence: X% of eligible days, success: Y%
- Dominant manipulation side (high/low) and what it implies

DAY-OF-WEEK EDGE
- Standout high/low range days, direction skews

SAMPLE: window.days days, N sessions — recent snapshot, not full history
```

## Interpretation guardrails

- **Sweep rate ≠ edge by itself.** A 70% sweep rate means *expect the sweep*;
  the tradeable edge is the `reversal_rate` after it (fade) vs continuation.
- **High vs low sweep skew reveals bias.** If London sweeps the Asia *high* far
  more than the low, the post-sweep reversal bias is bearish (and vice versa).
- **NY continuation < 50% = reversal-prone.** Watch the NY-open killzone
  (13:00–14:00 UTC) for London's move to fail.
- **Power of 3 needs a tight Asia.** Low `occurrence_rate` = the asset rarely
  accumulates tight enough; don't force the AMD framing.
- **Range% over raw range** when comparing sessions or assets — raw range scales
  with price.
- **Always anchor to sample size.** Don't state a 100% rate off 5 sessions as if
  it were a law.

See [reference.md](reference.md) for the complete definitions and rules.
