---
description: Detect and interpret candlestick / price-action patterns (doji, hammer, engulfing, stars, inside/outside bars) for a crypto symbol — in context, not in isolation.
argument-hint: [SYMBOL] [TIMEFRAME]
---

Read the recent candlestick price action for the requested crypto market and
deliver a trader-facing interpretation of the patterns — but only the ones that
matter **in context**.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`).
   Accept friendly forms ("btc" → `BTCUSDT`, "eth" → `ETHUSDT`, "sol" →
   `SOLUSDT`). The second token, if present, is the timeframe (default `1h`):
   one of 1m/5m/15m/1h/4h/1d/1w.
2. Call the `get_price_action` MCP tool (server: `rektfree`) with that symbol
   and timeframe.
3. Interpret the JSON using the price action skill. Do NOT dump the raw pattern
   list. A candlestick pattern is just a *shape* — its meaning depends entirely
   on **where** it appears:
   - A bullish engulfing / hammer at a key support level or after a liquidity
     sweep = a real reversal signal.
   - The same pattern in the middle of nowhere = noise; ignore it.
   So lead with the recent-candle `summary` (direction, body size, current
   candle geometry), then surface only the **most recent, highest-quality**
   patterns and explain what each implies *given the location* (`high`/`low`
   tells you where it sits — cross-reference levels/SMC if the user cares).
4. If the tool returns an `error` (forex pair, unknown symbol, no data), say so
   plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented. Flag indecision (doji/spinning top/inside
bar = compression, wait for a break) vs conviction (marubozu / engulfing /
three-soldiers = momentum). A trader should be able to act on it.
