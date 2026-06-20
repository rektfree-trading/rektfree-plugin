---
description: Reconstruct and interpret footprint / order-flow (delta, CVD, absorption, imbalances, large trades) for a crypto symbol. Use for buying/selling pressure, divergence, and conviction behind a move.
argument-hint: [SYMBOL] [timeframe]
---

Read the order flow behind price for the requested crypto market and deliver a
trader-facing call on who is in control — buyers or sellers — and whether the
move is supported or about to fail.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. The second token, if present, is the timeframe
   — one of `5m`, `15m`, `1h` (default `5m`). Reject anything else.
2. Call the `get_orderflow` MCP tool (server: `rektfree`) with that symbol and
   timeframe. Use the default candle count unless the user asks for more
   history (max 50).
3. Interpret the JSON using the orderflow skill. Do NOT dump the raw candles —
   synthesize a structured read: per-candle delta and its sign vs candle
   direction, the CVD trend and any price/CVD divergence, footprint imbalances
   and stacked imbalances, absorption/exhaustion signals, and large-trade
   clusters. Lead with the order-flow bias and the single most important signal.
4. If the tool returns an `error` (forex pair, unknown symbol, or an unsupported
   timeframe), say so plainly and suggest a valid crypto symbol + timeframe.
5. If the payload includes `truncated: true`, note that the trade window was
   capped by the request budget so the earliest candle(s) may be partial.

Keep it concise and decision-oriented — a trader should be able to act on it.
