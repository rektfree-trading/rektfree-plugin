---
description: Run an R-multiple backtest — first-touch trade simulation (ATR stop, R-target) over recent history producing an equity curve in R, expectancy, profit factor, win rate, and max drawdown.
argument-hint: [SYMBOL] [event_type] [target_r]
---

Simulate a rule as actual trades and report the edge in R — complementary to
`/backtest` (which answers "how often does X lead to Y?").

Request: `$ARGUMENTS`

Steps:

1. Parse the request for the symbol (default `BTCUSDT`; forex/metals/indices work
   too), the `event_type` (the entry signal), and optional exit params: stop size
   (`stop_atr_mult`, default 1.0), `target_r` (default 2.0), `atr_period`,
   `max_hold_bars`, and `days`. If no `event_type` is given, call the tool once
   with it empty to list the valid session-family event types and ask which one.
2. Call the `backtest_rr` MCP tool (server: `rektfree`) with those params.
3. Interpret the returned JSON (the `backtest` skill's read applies). Lead with
   the verdict: expectancy (R per trade), win rate, profit factor, and max
   drawdown — then the
   sample size `n` and confidence. Describe the equity curve's shape (steady vs
   choppy). Always cite `n`: a curve from a tiny sample is noise, not edge.
4. State the modeling caveats the payload carries: first-touch with stop-priority
   on ambiguous bars, no fees/slippage/funding, recent-live-sample only, and that
   only session-family events are supported (SMC events have no entry timestamp).
5. If the tool returns an `error`, relay it (e.g. unknown event type, too little
   history) and suggest a fix.

Keep it decision-oriented — is this rule worth trading, and at what size?
