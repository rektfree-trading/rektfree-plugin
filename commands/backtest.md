---
description: Backtest a historical pattern for a crypto symbol — "how often does X lead to Y?" Parse the question into structured conditions, run the in-memory frequency study, and interpret the rates with their sample size and caveats.
argument-hint: [natural-language pattern question, e.g. "how often does NY continue London on Mondays for ETH?"]
---

Answer a "how often does X lead to Y?" question for a crypto market with a
recent-sample frequency study. YOU parse the natural-language question into the
structured conditions the tool needs, run it, and deliver an honest, numbers-
with-sample-size read — never a bare percentage.

Request: `$ARGUMENTS`

Steps:

1. **Pick the symbol.** Default `BTCUSDT`. Accept friendly forms: "btc" →
   `BTCUSDT`, "eth" → `ETHUSDT`, "sol" → `SOLUSDT`. Forex pairs are not
   supported (the tool rejects `_` symbols).

2. **Parse the question into ONE `event_type` + optional filters.** This is the
   key step — the tool takes structured params, not prose. Map the question to:
   - `event_type` (required) — one of:
     `session_range`, `asia_sweep` (London sweeps Asia), `london_sweep`
     (NY sweeps London), `ny_continuation`, `power_of_3`, `smc_ob_test`,
     `smc_fvg_test`, `smc_bos_test`, `smc_choch_test`, `smc_eq_test`,
     `smc_sweep_test`.
   - optional: `session` (only with `session_range`), `day_of_week`
     (`Monday`..`Sunday`), `direction` (`bullish`/`bearish`), `sweep_side`
     (`high`/`low`/`both`), `htf_bias` (SMC bias), `days` (lookback).

   Mapping rules (mirror the hosted parser):
   - The `event_type` already implies the session for sweep/continuation events
     — do NOT also set `session`. "London sweeps Asia" → `asia_sweep`. "NY
     sweeps London" → `london_sweep`. "NY continuation" → `ny_continuation`.
     Use `session` ONLY with `session_range` ("London session direction" →
     `session_range`, `session=london`).
   - Sweep direction names the side that was TAKEN: "London sweeps Asia high" →
     `asia_sweep`, `sweep_side=high`. "NY sweeps London low" → `london_sweep`,
     `sweep_side=low`. If the question compares high vs low ("which side"),
     OMIT `sweep_side` to get both.
   - NEVER add an outcome filter (reversal/held/filled/continuation). The tool
     computes the rate from the unfiltered set — filtering by the outcome would
     bias it to 100%.
   - "BOS continuation" → `smc_bos_test`; "OB hold/retest" → `smc_ob_test`;
     "FVG fill" → `smc_fvg_test`; "CHoCH reversal" → `smc_choch_test`; "equal
     high/low sweep" → `smc_eq_test`; "liquidity sweep works" → `smc_sweep_test`.

3. **Call `run_backtest`** (server: `rektfree`) with `symbol`, `event_type`, and
   only the filters the question actually specified (plus `days` if named).

4. **Interpret with the `backtest` skill.** Do NOT dump raw JSON. State the
   headline rate IN CONTEXT — always with the sample size `matched.n` and the
   `outcomes.confidence` bucket. If there's a `day_of_week` breakdown, call out
   the standout weekday (and warn on thin per-day buckets). Translate the rate
   into a positioning read ("NY continues London 52% — barely a coin flip, no
   continuation edge here").

5. **State the caveats every time.** These are a RECENT live sample (cite
   `window.days`), NOT the full-history dashboard figures. There is NO macro/news
   data — if the user asked about macro, say it's unsupported. Surface any
   `notes` about ignored conditions (e.g. `day_of_week` ignored on SMC events,
   `range_state`/`macro_present` ignored). A rate from `n<5` is noise, not edge.

6. **Handle empties/errors.** If you don't set `event_type`, the tool returns
   the list of valid types — pick one and re-call. On an `error` (forex pair,
   unknown symbol, too few candles), say so plainly and suggest a valid crypto
   symbol.

Keep it concise and decision-oriented: the rate, the sample, the edge (or lack
of one), the caveat.
