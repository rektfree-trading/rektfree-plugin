---
name: pdhpdl
description: >-
  Previous-day-high / previous-day-low (PDH/PDL) touch statistics for crypto.
  Use whenever the user asks about PDH/PDL, the previous day's high or low, prior
  day levels, "does it sweep the previous day high/low", "does the prior high
  hold", how often yesterday's high/low gets taken out, or whether a sweep of the
  previous day's level reverses or holds, for a crypto symbol (BTC, ETH, SOL,
  etc.). Pairs with the `compute_pdh_pdl_stats` MCP tool, which fetches deep
  Binance 1H + daily history and returns the aggregated PDH/PDL touch stats.
---

# PDH / PDL Touch Statistics

You are the analyst. The `compute_pdh_pdl_stats` MCP tool (server `rektfree`)
does the computation — it fetches deep 1H + daily Binance candles, takes each
day's *previous* day high (PDH) and low (PDL), checks whether today's intraday
price reached them, and returns aggregated rates. Your job is to **interpret**
them into a clear, decision-oriented read. Never just echo the numbers.

## Workflow

1. **Fetch.** Call `compute_pdh_pdl_stats` with the `symbol` (e.g. `BTCUSDT`),
   and `days` if the user names a window. Crypto only — forex pairs (containing
   `_`) return an error.
2. **Interpret.** Read the payload against the rules in
   [reference.md](reference.md) — how to read sweep rates, the reversal-vs-hold
   distinction, and the outcome mix as edges.
3. **Synthesize.** Produce the structured output below. Lead with the most
   actionable edge (usually the dominant sweep side and its reversal rate).

## Sample-window caveat (state this every time)

The tool samples only the **last ~N days** it fetches live (`window.days`,
default ~90), NOT the full history the hosted dashboard aggregates. So:
- Always cite the sample size (`window.days`, each block's `n`).
- Treat these as a **recent snapshot**, not the long-run truth.
- Be cautious with thin samples (a weekday bucket with <8 days).

## Payload key

- `pdh` / `pdl` — each with `sweep_rate` (% of days price reached the level),
  `sweep_count`, `reversal_rate_when_swept` (swept then closed back inside —
  rejection / liquidity grab), `hold_rate_when_swept` (swept then accepted
  beyond the level — breakout), `avg_touch_time` (UTC HH:MM), and `n` (days).
- `outcomes` — mutually exclusive day classification: `pdh_only_pct`,
  `pdl_only_pct`, `both_pct`, `neither_pct`, plus `n`.
- `day_of_week.{Mon..Sun}` — per-weekday `pdh_pct`, `pdl_pct`, `both_pct`,
  `neither_pct`, and `count`.

## Output shape

```
PDH / PDL SWEEP DYNAMICS
- PDH swept X% of days — reversal Y% / hold Z% (avg touch HH:MM UTC)
- PDL swept X% of days — reversal Y% / hold Z% (avg touch HH:MM UTC)
- Which side gets hunted more, and the directional read

DAY CLASSIFICATION
- pdh_only X% / pdl_only X% / both X% / neither X%
- What the "neither" rate says about range-bound days

DAY-OF-WEEK EDGE
- Standout weekdays for PDH or PDL sweeps

IMPLICATION
- How to position: fade the sweep (high reversal) vs trade the breakout (high hold)

SAMPLE: window.days days, n=N — recent snapshot, not full history
```

## Interpretation guardrails

- **Sweep rate ≠ edge by itself.** A high sweep rate means *expect the level to
  be reached*; the tradeable edge is `reversal_rate_when_swept` (fade it back
  inside) vs `hold_rate_when_swept` (trade the breakout).
- **Reversal-heavy PDH = sell-side liquidity above.** If PDH is swept often and
  reverses, the prior high is a liquidity pool — fade the grab. Symmetric for PDL.
- **Hold-heavy = real breakouts.** A high `hold_rate_when_swept` means taking the
  prior level tends to lead to acceptance/continuation — don't blindly fade.
- **`neither` rate = inside days.** A high neither rate means price often stays
  within yesterday's range — expect mean-reversion, smaller targets.
- **`both` rate = volatile / two-sided days.** When both PDH and PDL get taken,
  the day raided liquidity on both ends — be wary of whipsaw.
- **Always anchor to sample size.** Don't state a 100% reversal rate off 4 sweeps
  as if it were a law.

See [reference.md](reference.md) for the complete definitions and rules.
