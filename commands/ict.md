---
description: Run ICT intraday session analysis (DOL, Power of 3 / AMD, Judas Swing, Session Bias) for a crypto symbol and deliver a session game-plan.
argument-hint: [SYMBOL] [TIMEFRAME]
---

Map the ICT intraday session dynamics for the requested crypto market and
deliver a trader-facing game-plan: the draw-on-liquidity target, the AMD phase
read, whether a Judas Swing fired, and the session bias.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. A second token may set the timeframe (default
   `1h`; `15m` also gives clean session boundaries).
2. Call the `get_ict_concepts` MCP tool (server: `rektfree`) with that symbol and
   `timeframe`.
3. Interpret the JSON using the ict skill. Do NOT dump the raw history lists —
   synthesize for the LATEST day: the DOL target and whether it's reached, the
   AMD phases with their clean/messy quality, any Judas Swing (direction +
   whether the reversal confirmed), and the London/NY session bias. Then frame
   the sweep → CHoCH → OB-entry → DOL-target sequence and cross-reference
   against daily bias if relevant.
4. If the tool returns an `error` (e.g. a forex pair, or an unknown symbol), say
   so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should be able to plan the
London/NY session from it.
