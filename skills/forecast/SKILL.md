---
name: forecast
description: >-
  Probabilistic forecast of the upcoming trading session for a crypto symbol.
  Use whenever the user asks what to expect this/next session, the projected or
  expected range, the odds of a sweep ("will it sweep the prior session high",
  "odds of a London sweep"), whether NY will continue or reverse London, or for
  a forward "session forecast / outlook / what's likely next" on a crypto symbol
  (BTC, ETH, SOL, etc.). Pairs with the `get_session_forecast` MCP tool, which
  fetches deep Binance 1H history, anchors the next session off the UTC clock,
  and returns the empirical frequency distributions for that session.
---

# Session Forecast Analysis

You are the analyst. The `get_session_forecast` MCP tool (server `rektfree`)
does the computation — it fetches deep 1H Binance candles, buckets them into
Asia/London/New York sessions, figures out from the UTC clock **which session is
next**, and returns the empirical distributions for that session (expected
range, sweep odds, continuation odds, projected levels). Your job is to
**interpret** them into a clear, forward, decision-oriented read. Never just
echo the numbers.

## This is a statistical forecast, not a prediction (say this)

The forecast is **frequencies over a recent sample** — base rates, not
certainties and not an AI call. The hosted product's similar-session
condition-matching is replaced here by straight aggregation over the recent
window. So:

- **Always read each probability WITH its `n`.** A 70% rate off `n=90` is a
  real edge; a 100% rate off `n=4` is noise. State the `n`.
- **There is no macro/news input.** A scheduled event (CPI, FOMC, etc.) can
  override any of these odds. Frame the forecast as a base rate the trader
  layers their own event-awareness on top of — not a plan.
- **Recent-window caveat:** the tool samples only the last `window.days` (~90 by
  default), so these differ from the hosted dashboard's full-history figures.

## Workflow

1. **Fetch.** Call `get_session_forecast` with the `symbol` (e.g. `BTCUSDT`) and
   `days` if the user names a window. Crypto only — forex pairs (containing `_`)
   return an error. The tool picks the forecast session itself.
2. **Interpret.** Read the payload against the rules in
   [reference.md](reference.md) — how to read expected range, sweep prob +
   reversal rate, continuation rate, and projected levels as a forward plan.
3. **Synthesize.** Produce the structured output below. Lead with the forecast
   session and its single most actionable edge.

## Payload key

- `forecast_session` / `current_session` — the session being forecast (the
  *next* one) vs the live one. `prior_session` is the session whose high/low the
  forecast session would sweep.
- `expected_range` — `median`, plus a `low`/`high` 25th/75th percentile band,
  in **range%** (price-regime-agnostic); `min`/`max` show the extremes seen;
  `n` is the sample.
- `direction` — bullish vs bearish **close** skew of the session, with `n`.
- `sweep_prob` — `prob` the forecast session sweeps the prior session's H/L
  (denominator = days the prior session existed, `n`); `likely_side`
  (high/low/either) is which liquidity gets hunted more; `reversal_rate` is how
  often the sweep closed back inside — the fade edge. **Empty for an Asia
  forecast** (nothing intraday to sweep before it).
- `continuation_prob` — NY `continuation` vs `reversal` % (with `n`). **Only
  populated for a New York forecast.**
- `projected_levels` — `anchor_price` (live price), `projected_high`/
  `projected_low` (the live price ± half the median range), and
  `prior_session_high`/`prior_session_low` (the actual liquidity a sweep would
  target).

## Output shape

```
SESSION FORECAST: [symbol] — [forecast_session] (currently [current_session])
Based on a recent sample (window.days days):

EXPECTED RANGE
- Median [X]% (typical band [low]%–[high]%), n=[N]
- Projected: [projected_low] – [projected_high] off [anchor_price]

SWEEP OUTLOOK  (if forecast_session is london/new_york)
- Sweeps prior [prior_session] H/L [X]% of days (n=[N]); likely side: [high/low]
- Reverses after the sweep [Y]% → the fade setup at [prior_session_high/low]

CONTINUATION  (New York only)
- NY continues London [X]% vs reverses [Y]%, n=[N] → [trade-continuation / fade]

DIRECTION SKEW
- [X]% bullish / [Y]% bearish close, n=[N]

CAVEATS
- Statistical base rates over [window.days] days, NOT a guarantee or AI call
- No macro/news input — a scheduled event can override this
```

## Interpretation guardrails

- **Sweep prob is "expect the sweep"; the edge is the `reversal_rate`.** High
  sweep prob + high reversal rate = fade the sweep at the prior extreme. High
  sweep prob + low reversal rate = the sweep is a continuation breakout.
- **`likely_side` reveals bias.** If the high gets swept far more than the low,
  the post-sweep reversal bias leans bearish (and vice versa).
- **NY continuation < 50% = reversal-prone.** Watch the NY-open killzone for
  London's move to fail; pair with the `sessions` / killzone skill for timing.
- **Project levels, don't promise them.** `projected_high/low` is the median-
  range envelope, not a target — state it as "the session typically reaches
  about here," not "it will hit X."
- **Small `n` = quiet down.** Don't state a rate off a thin sample as if it were
  a law. Asia forecasts and short `days` windows are the usual culprits.
- **Pair with other skills:** `sessions` (the long-run stats behind these odds),
  `levels` (S/R the projected band runs into), `volatility` (is the expected
  range realistic vs current ATR), killzone clock (WHEN the move is timed).

See [reference.md](reference.md) for the complete definitions and rules.
