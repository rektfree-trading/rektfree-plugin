---
description: Compute and interpret empirical SMC hit-rate statistics (OB hold, FVG fill, BOS continuation, CHoCH reversal, EQH/EQL sweep, liquidity-sweep success) for a crypto symbol. Use to ground SMC analysis in what has actually worked.
argument-hint: [SYMBOL]
---

Measure how often Smart Money Concepts patterns actually played out for the
requested crypto market, and deliver a trader-facing read of which patterns are
reliable on this asset right now.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. These stats are 1H-based, so no timeframe is
   needed.
2. Call the `compute_smc_stats` MCP tool (server: `rektfree`) with that symbol.
3. Interpret the JSON using the smcstats skill. Do NOT dump the raw blocks —
   synthesize a read: which patterns are reliable (high rate AND healthy sample
   size `n`), which are noisy or weak, the bullish/bearish split, and the
   concrete implication for an entry on this asset.
4. **Always read each rate together with its `n`.** A 70% rate from n=4 is noise;
   the same rate from n=120 is signal. Flag any block where n is small (< ~15)
   as low-confidence rather than quoting the percentage as fact.
5. State the coverage window (`window.from` → `window.to`). These rates come
   from the last ~3-4 months of 1H candles, not full history, so they will
   differ from the hosted app and reflect the recent regime.
6. If the tool returns an `error` (a forex pair, an unknown symbol, or too few
   candles), say so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should walk away knowing which
SMC patterns to trust on this asset and which to discount.
