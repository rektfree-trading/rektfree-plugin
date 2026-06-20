---
name: backtest
description: >-
  Historical pattern frequency study for crypto — "how often does X lead to Y?"
  Use whenever the user asks to backtest a pattern, or asks "how often does ...",
  "historically when X then Y", "what are the odds of ...", "what's the hit rate
  of <condition>", or any frequency/probability question about a setup (sweeps,
  NY continuation, Power of 3, OB hold, FVG fill, BOS continuation, CHoCH
  reversal, equal-level sweep, liquidity sweep) for a crypto symbol (BTC, ETH,
  SOL). You map the natural-language question into structured conditions and the
  `run_backtest` MCP tool computes the recent-sample rates in memory.
---

# Backtest — Historical Pattern Frequency

You are the analyst AND the query parser. The user asks a "how often does X lead
to Y?" question in plain language. YOU translate it into one `event_type` plus
optional condition filters, call the `run_backtest` MCP tool (server `rektfree`),
and **interpret** the returned rates — always with their sample size. Never echo
raw JSON, and never report a percentage without its `n`.

## What the tool does

`run_backtest` rebuilds, IN MEMORY from deep 1H Binance history, every detected
event with its outcome (the same session + SMC engines behind the
`/sessions` and `/smcstats` tools), filters that set by your structured
conditions, and aggregates the relevant OUTCOME rate. No database, no AI key.

## Workflow

1. **Parse the question → conditions.** Pick exactly ONE `event_type`, then add
   only the filters the question specifies. See the event-type vocabulary and
   mapping rules in [reference.md](reference.md). Critical: the `event_type`
   already implies the session for sweeps/continuation — do NOT also pass
   `session`. NEVER filter by the outcome itself (that biases the rate to 100%).
2. **Call `run_backtest`** with `symbol`, `event_type`, the filters, and `days`
   if the user named a window. Crypto only — forex (`_`) is rejected.
3. **Interpret.** Lead with the headline rate in context, cite `matched.n` and
   `outcomes.confidence`, surface the standout `day_of_week` bucket, and turn
   the number into a positioning read.

## Sample-window caveat (state this every time)

Results are a **recent live sample** (`window.days`), NOT the full-history
figures the hosted dashboard aggregates — so they will differ. Always:
- Cite `matched.n` and the `confidence` bucket. A rate from `n<5` is noise.
- Treat thin per-weekday buckets (<8) with caution.
- There is **no macro/news data** here — `macro_present` is ignored, and
  `range_state` is ignored too. Surface those `notes` if the question relied on
  them.

## Event-type vocabulary (the "X" you can study)

Session family (carry `day_of_week`):
- `session_range` — session direction (bullish %); pair with `session`.
- `asia_sweep` — London sweeps Asia's H/L → **post-sweep reversal rate**.
- `london_sweep` — NY sweeps London's H/L → **post-sweep reversal rate**.
- `ny_continuation` — NY continues vs reverses London → **continuation rate**.
- `power_of_3` — AMD pattern → **distribution success rate**.

SMC family (no `day_of_week` — a weekday filter is noted as ignored):
- `smc_ob_test` — **retest rate** + **hold-when-retested rate**.
- `smc_fvg_test` — **fill rate** + avg fill %.
- `smc_bos_test` — **continuation rate** + avg max move %.
- `smc_choch_test` — **reversal rate** + avg max move %.
- `smc_eq_test` — **sweep rate** + **reversal-when-swept rate**.
- `smc_sweep_test` — **success rate** + avg max move %.

## Output shape

```
PATTERN: <plain-language restatement of X → Y>
RATE: <headline outcome rate>% (n=<matched.n>, confidence=<bucket>)
BREAKDOWN: side / direction split, and standout weekday (session events only)
EDGE: is there a tradeable edge, or is it ~coin-flip? position implication
SAMPLE: <window.days> days, n=<matched.n> — recent snapshot, not full history
        + any ignored conditions (macro/range_state/SMC weekday)
```

## Interpretation guardrails

- **Rate without n is meaningless.** 70% from n=4 is noise; from n=120 it's
  signal. Lead with the rate, immediately qualify with n + confidence.
- **A ~50% rate is no edge.** "NY continues 52%" ≈ coin flip — say so.
- **Sweep events: the edge is the reversal rate, not the sweep itself.** A high
  sweep rate just means *expect the sweep*; the tradeable read is whether it
  fades (reversal) or runs.
- **Don't filter by the outcome.** If asked "how often does the OB hold", run
  `smc_ob_test` and read `hold_rate_overall` / `hold_rate_when_retested` — do
  NOT pass a held filter.
- **SMC weekday questions can't be answered here.** If the user asks "OB hold on
  Mondays", say the keyless engine has no formation date for SMC events; give
  the overall rate instead.

See [reference.md](reference.md) for the full vocabulary, mapping rules, and
payload key.
