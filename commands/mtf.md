---
description: Multi-timeframe (MTF) structural alignment for a crypto symbol — runs SMC on Daily + 4H + entry timeframe and reports whether they align. Use for higher-timeframe bias and trade direction.
argument-hint: [SYMBOL] [entry-timeframe]
---

Build the multi-timeframe picture for the requested crypto market: state the
higher-timeframe bias first, then show how the entry timeframe sits within it.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. First token = Binance symbol (default `BTCUSDT`); accept
   "btc"→`BTCUSDT`, etc. Second token = entry timeframe (default `1h`). Forex
   pairs (`_`) are not supported.
2. Call `analyze_smc` (server: `rektfree`) on **`1d`**, **`4h`**, and the entry
   timeframe — run them together.
3. Interpret with the `mtf` skill: read each timeframe's bias and key structures,
   classify alignment (Full / Partial / Conflict), and give the implication. HTF
   structure overrides LTF; use HTF OBs/FVGs as targets/entry zones.
4. If a higher timeframe has too few candles, say so and weight it less.

Lead with the HTF bias and a clear go/no-go on direction. Keep it tight.
