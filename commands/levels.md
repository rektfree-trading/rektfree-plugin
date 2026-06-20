---
description: Compute and interpret key time-based price levels (D/W/M H-L-O + session H/L) for a crypto symbol. Use for support/resistance, liquidity targets, and bias.
argument-hint: [SYMBOL]
---

Map the key price levels for the requested crypto market and deliver a
trader-facing read of support, resistance, liquidity, and bias.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. Levels are time-based, so no timeframe is needed.
2. Call the `get_levels` MCP tool (server: `rektfree`) with that symbol.
3. Interpret the JSON using the levels skill. Do NOT dump the raw list —
   synthesize a structured read: the level map (monthly/weekly/daily/session),
   bias from opens (price above/below each open), nearest support/resistance to
   `last_price`, confluence zones where levels stack, and the most likely next
   liquidity target with reasoning.
4. If the tool returns an `error` (e.g. a forex pair, or an unknown symbol), say
   so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should be able to act on it.
