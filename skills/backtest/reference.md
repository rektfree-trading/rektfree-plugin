# Backtest — Reference Playbook

This skill answers "how often does X lead to Y?" for a crypto asset by rebuilding
its historical events and outcomes from a recent 1H sample and aggregating the
relevant rate. It grounds analysis in what has actually happened for the symbol
over the sampled window, not generic theory — and it is honest about sample size,
because a rate with no `n` is a guess wearing a percent sign.

The natural-language question is parsed by Claude (this skill) into structured
conditions; the `run_backtest` tool only does the data work.

## Tool payload

`run_backtest(symbol, event_type, session?, day_of_week?, direction?,
sweep_side?, htf_bias?, range_state?, days?)` returns:

```
{
  "symbol": "BTCUSDT",
  "conditions": { ...echoed active filters... },
  "window": { "candles", "timeframe", "from", "to", "days" },
  "matched": { "n": <int> },
  "outcomes": { ...rates 0–100 + "n" + "confidence"... },
  "day_of_week": { "Monday": {"count", "<label>_pct"}, ... },  // session events only
  "notes": [ ...sample-window + ignored-condition caveats... ]
}
```

All session times are UTC: **Asia 00:00–08:00**, **London 08:00–13:00**,
**New York 13:00–21:00** — the same buckets the session engine uses.

## Event-type vocabulary and the outcome each measures

| event_type        | "X" (the condition)            | "Y" (the outcome rate)                    |
|-------------------|--------------------------------|-------------------------------------------|
| `session_range`   | a session's range/direction    | `bullish_rate` (+ avg_range_pct)          |
| `asia_sweep`      | London sweeps Asia's H/L       | `reversal_rate` (closed back inside)      |
| `london_sweep`    | NY sweeps London's H/L         | `reversal_rate`                           |
| `ny_continuation` | NY vs London direction         | `continuation_rate` / `reversal_rate`     |
| `power_of_3`      | tight Asia → London sweep → run| `success_rate` (distribution ≥1.5× Asia)  |
| `smc_ob_test`     | an order block forms           | `retest_rate`, `hold_rate_when_retested`  |
| `smc_fvg_test`    | a fair-value gap forms         | `fill_rate`, `avg_fill_pct`               |
| `smc_bos_test`    | a break of structure           | `continuation_rate`, `avg_max_move_pct`   |
| `smc_choch_test`  | a change of character          | `reversal_rate`, `avg_max_move_pct`       |
| `smc_eq_test`     | equal highs/lows form          | `sweep_rate`, `reversal_rate_when_swept`  |
| `smc_sweep_test`  | a liquidity sweep              | `success_rate`, `avg_max_move_pct`        |

## Condition keys

- `session` — `asia`/`london`/`new_york`. Only meaningful with `session_range`.
- `day_of_week` — `Monday`..`Sunday`. **Session events only**; on SMC events the
  filter is ignored (no formation date in the keyless engine) and noted.
- `direction` — `bullish`/`bearish`. Session/NY/P3 direction, or SMC structure
  bias.
- `sweep_side` — `high`/`low`/`both`. Sweep side, and Power-of-3 manipulation
  side.
- `htf_bias` — `bullish`/`bearish`. SMC structure bias (same as the SMC event's
  direction).
- `range_state` — **accepted but ignored** (no tight/wide tagging here).
- `macro_present` — **not a tool param; unsupported** (no macro/news data).
- `days` — lookback (1H candles), capped at 365. Default ~180.

## Mapping rules (NL question → conditions)

1. **One `event_type` per question.** The event_type already encodes the
   session relationship — do NOT also set `session` for sweep/continuation
   events. Use `session` ONLY with `session_range`.
   - "how often does London sweep Asia" → `asia_sweep`
   - "does NY sweep London" → `london_sweep`
   - "NY continuation rate" → `ny_continuation`
   - "London session bullish %" → `session_range`, `session=london`
2. **Sweep side = the side taken.** "London sweeps Asia *high*" → `asia_sweep`,
   `sweep_side=high`. "which side does NY take" → omit `sweep_side`, read the
   `swept_high`/`swept_low` split.
3. **Never filter by the outcome.** "how often does the OB *hold*" → run
   `smc_ob_test` (no filter) and read `hold_rate_overall` /
   `hold_rate_when_retested`. Filtering on the outcome forces 100%.
4. **SMC names.** BOS continuation → `smc_bos_test`; OB retest/hold →
   `smc_ob_test`; FVG fill → `smc_fvg_test`; CHoCH reversal → `smc_choch_test`;
   equal high/low sweep → `smc_eq_test`; "does the liquidity sweep work" →
   `smc_sweep_test`.
5. **Weekday on a sweep/continuation** → set `day_of_week`; the breakdown also
   appears in `day_of_week` regardless.

## Reading the outcome

- **`confidence` buckets** mirror the hosted backtester: HIGH ≥50, MEDIUM ≥20,
  LOW ≥5, INSUFFICIENT <5.
- **Reversal rate is the edge on sweeps**, not the sweep rate. A 50% reversal is
  a coin flip; a 70% reversal with healthy `n` is a fade edge.
- **Hold-when-retested vs overall hold.** `hold_rate_when_retested` answers "if
  price comes back, does the zone hold?"; `hold_rate_overall` folds in zones that
  were never retested.
- **Day-of-week buckets** are thin by construction (one event family, split 7
  ways) — flag any weekday with `count < 8`.

## Caveats to state every time

- **Recent sample, not full history.** Cite `window.days` and `matched.n`. The
  hosted dashboard aggregates over far more data and its rates will differ.
- **No macro, no news.** `macro_present` is unsupported; `range_state` is
  ignored. Surface these from `notes` when relevant.
- **Small n = noise.** Below `n=5` (INSUFFICIENT), report the count, not a rate
  as if it were an edge.

## Consistency

With no extra filter, an `event_type`'s headline rate matches the corresponding
`/sessions` or `/smcstats` figure for the same symbol and window (e.g.
`london_sweep` `reversal_rate` equals `compute_session_stats`'s
`sweeps.london_sweep.reversal_rate`). Filters narrow the set, so rates then move.
