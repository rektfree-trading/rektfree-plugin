---
description: Show what the RektFree plugin can do — a categorized map of its tools, commands, and markets.
---

The user wants an overview of what this plugin offers. Present a **scannable,
categorized map** of the RektFree commands — not a JSON dump, and do **not** call
any MCP tool. Group the commands into the buckets below, with a one-line "what
it's for" next to each so a first-run user can find the right entry point fast.

Render it tightly, grouped like this (one line per command, short gloss):

**Flagship reads** — synthesis commands that orchestrate many tools into one brief
- `/analyze` — full multi-factor read for a crypto market (SMC + levels + profile + flow + confluence) → bias, plan, invalidation
- `/brief` — forward-looking pre-session brief: where we are in the trading day, session tendencies, watch-list / if-then plan
- `/strategy` — review your own trades or strategy vs the RektFree framework (attach a broker export or paste trades)

**Structure & SMC**
- `/smc` — Smart Money Concepts: structure, order blocks, FVGs, liquidity, bias
- `/ict` — ICT intraday read: draw-on-liquidity, Power-of-3 / AMD, Judas swing, session bias
- `/dailybias` — TTrades daily/weekly bias + draw-on-liquidity target with hit rates
- `/priceaction` — candlestick / price-action patterns (engulfing, pins, dojis, inside/outside) in context
- `/mtf` — multi-timeframe structural alignment (Daily + 4H + entry TF)

**Levels & value**
- `/levels` — D/W/M H-L-O + session highs/lows: support/resistance and liquidity targets
- `/profile` — Market Profile / TPO: POC, VAH/VAL, value area, where price is drawn
- `/peakpoints` — which session prints the day's high vs low (HOD×LOD matrix)
- `/sessioncard` — "session potential" card for one session: direction split, HOD/LOD odds, timing, breakout tendency

**Flow & positioning**
- `/orderflow` — footprint / order flow: delta, CVD, absorption, large trades
- `/derivatives` — futures positioning: funding, OI, long/short, taker flow → squeeze risk
- `/correlations` — cross-asset correlation vs BTC + regime shift (confirmation / diversification)

**Sessions & timing**
- `/sessions` — session stats: Asia/London/NY ranges, sweep rates, NY continuation, Power-of-3, day-of-week
- `/killzone` — live session & ICT killzone clock: is now good timing for an entry?
- `/forecast` — probabilistic forecast for the next session: expected range, sweep odds, continuation vs reversal
- `/sessionext` — how often / how far a session extends beyond the prior session's range
- `/orb` — Opening Range Breakout stats: first-break side, two-side rate, extension multiples
- `/ethprofile` — prior-day value touch: how often the next day tags prior POC / VAH / VAL
- `/ib` — Initial Balance stats: breakout rate, first-break side, extension, IB-hold
- `/daytype` — day-type archetypes (trend / range / reversal / volatile) and how often each occurs
- `/pdhpdl` — previous-day high/low: sweep rate and whether the sweep reverses or holds

**Scanning**
- `/scan` — grade one symbol with the 0–N Smart Money confluence score (go/no-go)
- `/market` — scan a watchlist and rank symbols by confluence: "where are the setups right now?"

**Stats & backtests**
- `/smcstats` — empirical SMC hit rates (OB hold, FVG fill, BOS continuation, CHoCH reversal, sweep success)
- `/backtest` — "how often does X lead to Y?" in-memory frequency study from a plain-English question
- `/backtestrr` — R-multiple backtest: equity curve in R, expectancy, profit factor, win rate, max drawdown
- `/edges` — mine recent history for statistically significant edges and anti-patterns

**Risk & data**
- `/possize` — risk-based position size + R:R from equity, risk %, entry, stop (crypto & USD forex/metals/indices)
- `/volatility` — ATR / ADR / realized vol / Bollinger squeeze → sizing, stops, "is a move coming?"
- `/candles` — raw OHLCV for any supported symbol/timeframe to read or compute on actual prices

Then close with these three short notes:

- **You can also just ask in plain English.** Skills auto-activate — e.g. "what's
  the setup on ETH?", "is the daily range exhausted?", "where are the setups right
  now?" — no need to remember the slash command.
- **Markets:** crypto works with **no API key** (Binance public data). Forex,
  metals, and stock indices (e.g. `EUR_USD`, `XAU_USD`, `NAS100_USD`) need an
  **OANDA token** — ask "how do I set up forex?" for the one-time setup.
- **First connect:** if the MCP server times out the very first time, reconnect
  once via `/mcp` — every session after that is instant.
- **About / follow:** run `/about` for who builds RektFree and the Decipher
  Telegram channel (live context & session calls).

Keep the whole thing a map, not a manual — short glosses, no walls of prose.
