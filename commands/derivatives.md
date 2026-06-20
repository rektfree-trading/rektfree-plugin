---
description: Read crypto futures positioning — funding rate, open interest, long/short ratios (global + top-trader), and taker flow. Use for crowding, squeeze risk, and conviction behind a move.
argument-hint: [SYMBOL] [period]
---

Read the futures positioning for the requested crypto market and turn it into a
positioning signal — who's crowded, where a squeeze could fire, and whether
leverage confirms or contradicts the price move.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. First token = Binance perp symbol (default `BTCUSDT`);
   accept "btc"→`BTCUSDT`, "eth"→`ETHUSDT`, "sol"→`SOLUSDT`. Optional second
   token = lookback period (5m/15m/30m/1h/2h/4h/6h/12h/1d, default `1h`). Forex
   pairs (`_`) have no futures data — say so and suggest a crypto symbol.
2. Call the `get_derivatives` MCP tool (server: `rektfree`) with that symbol and
   period.
3. Interpret using the derivatives skill — do NOT dump the JSON. Cover funding
   (bias + squeeze risk), open interest (is the move backed by new positions or
   just an unwind?), long/short ratios (crowded? does the **top-trader** ratio
   diverge from the **global** crowd?), and taker flow (aggressor side; any
   divergence from price). Always cite the actual numbers.
4. Close with a positioning signal: Bullish / Bearish / Neutral + squeeze risk
   (Low / Medium / High), with the specific metric that drives it.

Keep it tight and decision-oriented.
