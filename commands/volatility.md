---
description: Compute and interpret volatility & range context (ATR, ADR + % used, realized vol, Bollinger squeeze, expansion/contraction) for a crypto symbol. Use for stop/target sizing and "is it about to move?" calls.
argument-hint: [SYMBOL] [timeframe]
---

Read the volatility and range state for the requested crypto market and deliver
a trader-facing call on position sizing, stop/target distances, and whether a
move is likely or already exhausted.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. A second token is the intraday timeframe for
   ATR/Bollinger/realized-vol (default `1h`); ADR always uses daily candles.
2. Call the `get_volatility` MCP tool (server: `rektfree`) with that symbol and
   timeframe.
3. Interpret the JSON using the volatility skill. Do NOT dump the raw numbers —
   synthesize a read: the state (expanding/contracting/neutral) and why, how much
   of today's ADR is already used (room left vs exhausted), ATR-based stop and
   target suggestions (~1× ATR stop, 2–3× ATR target), the squeeze flag (breakout
   anticipation), and what it implies for position sizing.
4. If the tool returns an `error` (e.g. a forex pair, an unknown symbol, or too
   few candles), say so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should be able to size and place
a trade from it.
