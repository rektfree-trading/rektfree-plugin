---
name: candles
description: >-
  Raw OHLCV candle data for any supported market. Use whenever the user wants the
  actual prices — "show me candles", "the last N candles", "pull the price data",
  "what were the actual prices", recent highs/lows or the last close, or candle
  data to eyeball structure or run your own arithmetic on. Works for crypto
  (Binance, no key) and forex/metals/indices (OANDA, underscore symbols like
  EUR_USD / XAU_USD / NAS100_USD). Pairs with the `get_candles` MCP tool — the
  data primitive every other tool in the plugin builds on.
---

# Raw OHLCV Candles

You are the analyst. The `get_candles` MCP tool (server `rektfree`) is the
lowest-level data primitive — it fetches actual bars and returns clean,
ISO-stamped OHLCV. It does **no** interpretation; everything else in the plugin
derives its numbers FROM candles, and this returns the candles themselves. Your
job is to read them usefully, not dump every row unless asked.

## Workflow

1. **Parse.** First token = `symbol` (default `BTCUSDT`; accept "btc" →
   `BTCUSDT`, "eth" → `ETHUSDT`). Crypto = no separator. Forex/metals/indices use
   the **underscore** form → routes to OANDA: `EUR_USD`, `XAU_USD`,
   `NAS100_USD`. Second token = `timeframe` (default `1h`;
   1m/5m/15m/1h/4h/1d/1w, aliases like `h1` accepted). Third = `limit` (default
   200, capped at 1000).
2. **Call** `get_candles(symbol, timeframe, limit)`.
3. **Read concisely by default.** Summarize the recent action — range
   (high/low), `last_price`, the window covered, and any notable candles (big
   moves, rejections, gaps). **Do not paste every row** unless the user
   explicitly wants the raw data, in which case give a compact table.
4. **Errors.** If the payload has an `error` (unknown symbol, bad timeframe, or a
   forex symbol with no `RF_OANDA_TOKEN` set), say so; for a token issue point to
   `/forex` setup.

## Payload key

`get_candles` returns:

- `symbol`, `timeframe` — echoed back (timeframe normalized).
- `count` — number of candles returned.
- `first`, `last` — ISO-UTC timestamps of the oldest and newest bar (the window).
- `last_price` — close of the newest candle.
- `candles` — array, **oldest → newest**, each `{time, time_iso, open, high,
  low, close, volume}`.

## Output shape (concise default)

```
[SYMBOL] [timeframe] — [count] candles, [first] → [last]
- Last price: [last_price]
- Window high / low: [max high] / [min low]
- Notable: [biggest candle / rejection / gap, with its time_iso]
- [one-line read of recent structure if useful]
```

For a raw request, instead give a compact table of `time_iso, O, H, L, C, V`
(newest last), trimmed to a sensible count.

## Interpretation guardrails

- **The newest candle is usually still forming.** The last bar is partial — its
  high/low/close keep changing until the period closes. Treat it as provisional;
  don't call a high/low "the" high/low off an unclosed candle, and flag this when
  it matters (e.g. a "new high" that's just the live bar).
- **Concise unless asked.** Reading 200 bars to a user as a wall of numbers is
  noise. Default to range + last + standout candles; reserve the full table for
  an explicit "give me the raw rows / the data."
- **Symbol format is load-bearing.** No underscore → Binance crypto; underscore →
  OANDA forex/metals/indices. A forex symbol with no `RF_OANDA_TOKEN` errors —
  that's a setup issue, not a bad request.
- **Candles are the primitive, not the analysis.** If the user actually wants
  volatility, levels, sessions, structure, etc., the dedicated tool/skill is
  better than hand-reading raw bars — use this when they want the prices
  themselves or to sanity-check what another tool reported.
- **Mind the window vs limit.** `count × timeframe` is roughly how far back the
  data reaches; a "last week" question on `1h` needs ~168 candles. Don't infer
  trends from a window that's too short for the question.
