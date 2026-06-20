---
description: Compute and interpret session statistics (Asia/London/NY ranges, sweep rates, NY continuation, Power of 3, day-of-week) for a crypto symbol from live history.
argument-hint: [SYMBOL]
---

Compute the session statistics for the requested crypto market and deliver a
trader-facing read of session dynamics — which session moves most, how often
London sweeps Asia, whether NY tends to continue or reverse, and which days of
the week behave differently.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. If the user names a lookback ("last 60 days"),
   pass it as `days`; otherwise leave the default.
2. Call the `compute_session_stats` MCP tool (server: `rektfree`) with that
   symbol (and `days` if specified).
3. Interpret the JSON using the sessions skill. Do NOT dump the raw numbers —
   synthesize a structured read: the volatility ranking of the three sessions,
   the Asia→London and London→NY sweep rates (and which side gets swept more),
   the NY continuation vs reversal tendency, the Power-of-3 occurrence/success
   rate, and any standout day-of-week pattern. Translate each stat into how a
   trader should position (e.g. "London sweeps Asia 70% of days → expect the
   sweep, fade it for the reversal").
4. ALWAYS state the sample window. The tool reports `window.days` and
   `window.candles` — this is a recent live snapshot (~90 days by default), NOT
   the full-history figures the hosted dashboard shows. Say so, and treat small
   samples (low session counts) with appropriate caution.
5. If the tool returns an `error` (e.g. a forex pair, an unknown symbol, or too
   few candles), say so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should be able to act on it.
