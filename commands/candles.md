---
description: Fetch raw OHLCV candles for any supported symbol/timeframe (crypto via Binance, forex/metals/indices via OANDA) so Claude can read or compute on the actual prices.
argument-hint: [SYMBOL] [timeframe] [limit]
---

Pull raw candles for the requested market — the data primitive behind everything
else.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. First token is the symbol (default `BTCUSDT`; accept "btc"
   → `BTCUSDT`, "eth" → `ETHUSDT`; forex/metals/indices use the underscore form,
   e.g. `EUR_USD`, `XAU_USD`, `NAS100_USD`). Second token is the timeframe
   (default `1h`); a third is the number of candles (default 200, capped).
2. Call the `get_candles` MCP tool (server: `rektfree`) with those values.
3. Present what the user asked for: if they want a quick read, summarize the
   recent action (range, last price, notable candles) rather than dumping every
   row; if they want the data, give a compact table. Note the newest candle may
   be partial/forming.
4. If the tool returns an `error` (unknown symbol, bad timeframe, or a forex
   symbol with no `RF_OANDA_TOKEN` set), say so and point to `/forex` setup if
   it's a token issue.

Default to a concise read unless the user explicitly wants the raw rows.
