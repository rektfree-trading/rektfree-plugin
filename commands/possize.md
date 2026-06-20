---
description: Calculate a risk-based position size and R:R from account equity, risk %, entry, and stop (or an ATR-derived stop). Works for crypto and USD-quoted forex/metals/indices.
argument-hint: [equity] [risk%] [entry] [stop] [target?]
---

Turn the trader's account and trade parameters into a concrete position size and
risk read.

Request: `$ARGUMENTS`

Steps:

1. Parse the request for: account equity, risk percent (default 1%), entry price,
   stop price, and an optional target. The user may give these in plain English
   ("$10k account, 1% risk, long BTC entry 63000 stop 61500 target 67000"). If a
   stop isn't given but a symbol and an ATR multiple are, pass `symbol` +
   `stop_atr_mult` so the tool derives the stop from ATR.
2. Call the `calc_position_size` MCP tool (server: `rektfree`) with the parsed
   values. Pass `leverage` if the user mentions it.
3. Interpret the returned JSON. Lead with the position size (units + notional),
   the dollar risk, and — if a target was given — the R:R and the breakeven
   win-rate. Note the stop source (explicit vs ATR-derived).
4. State the caveats the payload carries: sizing is exact only when the quote
   currency is the account currency (USDT crypto, `*_USD` pairs) — for cross
   pairs the per-unit risk is in the quote currency; no fees/slippage modeled.
5. If the tool returns an `error` (bad equity/risk/entry, or a stop on the wrong
   side), say what's wrong and how to fix it.

Keep it tight — a trader should be able to place the order from your answer.
