---
description: Probabilistic forecast for the upcoming/current trading session of a crypto symbol — expected range, odds it sweeps the prior session, continuation vs reversal, and projected levels, all from recent session history.
argument-hint: [SYMBOL]
---

Produce a forward read of the **next** trading session for the requested crypto
market — what range to expect, the odds it sweeps the prior session's
high/low, whether NY is likely to continue or reverse London, and the concrete
price levels to watch — built from this symbol's **recent** session history.

This is a **statistical forecast** (frequencies from the recent sample), NOT an
AI prediction and NOT a guarantee.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`).
   Accept friendly forms ("btc" → `BTCUSDT`, "eth" → `ETHUSDT`, "sol" →
   `SOLUSDT`). If the user names a lookback ("last 60 days"), pass it as `days`.
2. Call the `get_session_forecast` MCP tool (server: `rektfree`) with that
   symbol (and `days` if specified). The tool itself anchors **which** session
   is next from the UTC clock — don't compute that yourself.
3. Interpret the JSON using the `forecast` skill. Do NOT dump the raw numbers.
   Lead with the forecast session and its single most actionable edge (usually
   the sweep probability + reversal rate, or the continuation tendency).
   Translate each figure into how a trader should position — e.g. "London
   sweeps the Asia high 70% of days and fades it 57% of the time → expect the
   sweep above `prior_session_high`, watch for the reversal."
4. **Stress probabilities AND sample sizes.** Every number carries an `n`. A
   rate off a small `n` is weak — say so. Never present a frequency as a
   certainty.
5. **State the caveats every time:** these are frequencies over a recent live
   window (`window.days`), not the hosted dashboard's full history; and there is
   **no macro/news input**, so a scheduled event (CPI, FOMC) can override the
   forecast. Treat it as a base rate, not a plan.
6. Note the session-specific gaps: an **Asia** forecast has no `sweep_prob`
   (nothing intraday before it to sweep) and `continuation_prob` is populated
   only for a **New York** forecast.
7. If the tool returns an `error` (forex pair, unknown symbol, too few candles),
   say so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — frame trade ideas around the projected
levels, but always tied back to the probabilities and their `n`.
