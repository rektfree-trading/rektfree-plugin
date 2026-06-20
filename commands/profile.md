---
description: Compute and interpret a Market Profile / TPO (POC, VAH/VAL, value area) for a crypto symbol. Use for fair value, balance vs imbalance, and where price is drawn next.
argument-hint: [SYMBOL] [timeframe]
---

Build the Market Profile / TPO for the requested crypto market and deliver a
trader-facing read of value, balance, and likely direction.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given); the second is the timeframe (default `1h`). Accept friendly
   forms like "btc" → `BTCUSDT`, "eth" → `ETHUSDT`, "sol" → `SOLUSDT`. Timeframes:
   1m, 5m, 15m, 1h, 4h, 1d, 1w. The timeframe sets the session grouping (1h →
   daily sessions, 4h → weekly, 1d/1w → monthly).
2. Call the `get_market_profile` MCP tool (server: `rektfree`) with that symbol
   and timeframe. Use a `limit` of 500 unless the user asks for a longer or
   shorter lookback; leave `max_sessions` at its default unless asked.
3. Interpret the JSON using the tpo skill. Do NOT just dump the raw buckets —
   synthesize a structured read: the prior session's POC/VAH/VAL, the developing
   current session, POC migration (rising/falling/flat) across sessions, profile
   shape (P/b/D/B) from where the heavy buckets sit, where `last_price` is
   relative to the value area (above VAH / inside VA / below VAL), naked POCs that
   price hasn't revisited, and the most likely next target with reasoning.
4. If the tool returns an `error` (e.g. a forex pair, or an unknown symbol), say
   so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should be able to act on it.
