---
description: Compute and interpret previous-day-high / previous-day-low (PDH/PDL) touch statistics — how often the prior day's high/low gets swept, and whether the sweep reverses or holds — for a crypto symbol from live history.
argument-hint: [SYMBOL]
---

Compute the PDH/PDL touch statistics for the requested crypto market and deliver
a trader-facing read of how the previous day's high and low behave as liquidity
levels — how often each gets swept, which side gets hunted more, and whether a
sweep tends to *reverse* (rejection / liquidity grab) or *hold* (acceptance /
breakout).

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. If the user names a lookback ("last 60 days"),
   pass it as `days`; otherwise leave the default.
2. Call the `compute_pdh_pdl_stats` MCP tool (server: `rektfree`) with that
   symbol (and `days` if specified).
3. Interpret the JSON using the pdhpdl skill. Do NOT dump the raw numbers —
   synthesize a structured read: the PDH vs PDL sweep rates (and which side gets
   swept more), the reversal-vs-hold rate after each sweep, the outcome mix
   (pdh_only / pdl_only / both / neither), and any standout day-of-week pattern.
   Translate each stat into how a trader should position (e.g. "PDH swept 65% of
   days and reverses 70% of the time → fade the sweep back inside").
4. ALWAYS state the sample window. The tool reports `window.days` and each
   block's `n` — this is a recent live snapshot (~90 days by default), NOT the
   full-history figures the hosted dashboard shows. Say so, and treat small
   samples with appropriate caution.
5. If the tool returns an `error` (a forex pair, an unknown symbol, or too few
   days), say so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should be able to act on it.
