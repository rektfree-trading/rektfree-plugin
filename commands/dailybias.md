---
description: Compute and interpret the TTrades daily (or weekly) bias for a crypto symbol — direction, draw-on-liquidity target, and historical hit rates.
argument-hint: [SYMBOL] [D|W]
---

Determine today's directional bias for the requested crypto market and deliver a
trader-facing read: which way to lean, the draw-on-liquidity target, and how
reliable the bias has been.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. If a `W` token is present, use weekly bias;
   otherwise daily (`D`). Bias is time-based, so no timeframe is needed.
2. Call the `get_daily_bias` MCP tool (server: `rektfree`) with that symbol and
   `period`.
3. Interpret the JSON using the dailybias skill. Do NOT dump the raw entries —
   synthesize: the current bias and the rule that produced it, the draw-on-
   liquidity target (PDH if bullish, PDL if bearish) and the invalidation side,
   whether that target has been reached today, and what the success /
   close-through stats say about how much to trust the bias.
4. If the tool returns an `error` (e.g. a forex pair, or an unknown symbol), say
   so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should know which way to lean
and the target before the session opens.
