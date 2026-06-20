---
description: Run Smart Money Concepts (SMC) analysis on a crypto symbol and interpret it. Use for market structure, order blocks, FVGs, liquidity, and bias.
argument-hint: [SYMBOL] [timeframe]
---

Analyze the Smart Money Concepts structure for the requested crypto market and
deliver a trader-facing read.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given); the second is the timeframe (default `1h`). Accept friendly
   forms like "btc" → `BTCUSDT`, "eth" → `ETHUSDT`, "sol" → `SOLUSDT`. Timeframes:
   1m, 5m, 15m, 1h, 4h, 1d, 1w.
2. Call the `analyze_smc` MCP tool (server: `rektfree`) with that symbol and
   timeframe. Use a `limit` of 500 unless the user asks for a longer or shorter
   lookback.
3. Interpret the JSON using the SMC skill. Do NOT just dump the raw numbers —
   synthesize a structured read: market structure & trend, key zones (unmitigated
   order blocks, fair value gaps), liquidity (equal highs/lows, recent sweeps),
   premium/discount positioning vs the swing range, and the highest-confluence
   levels with an invalidation.
4. If the tool returns an `error` (e.g. a forex pair, or an unknown symbol), say
   so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should be able to act on it.
