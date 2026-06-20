---
name: volatility
description: >-
  Volatility & range context for crypto. Use whenever the user asks about
  volatility, ATR (average true range), ADR (average daily range), realized or
  historical volatility, Bollinger Bands / band width / a squeeze, whether the
  market is expanding or contracting / compressed or coiling, "how much room is
  left to move" / is the daily range exhausted, "is it about to move" / breakout
  anticipation, or how to size a position / set stops and targets by volatility
  for a crypto symbol (BTC, ETH, SOL, etc.). Pairs with the `get_volatility` MCP
  tool, which fetches Binance candles and returns the computed metrics.
---

# Volatility & Range Analysis

You are the analyst. The `get_volatility` MCP tool (server `rektfree`) does the
computation — it fetches Binance intraday candles (ATR / Bollinger / realized
vol) and daily candles (ADR) and returns the metrics. Your job is to
**interpret** them into a clear, decision-oriented read for position sizing,
stop/target distances, and whether a move is likely or already exhausted. Never
just echo the JSON.

## Workflow

1. **Fetch.** Call `get_volatility` with the `symbol` (e.g. `BTCUSDT`) and an
   optional intraday `timeframe` (default `1h`). Crypto only — forex pairs
   (containing `_`) return an error. ATR/Bollinger/realized-vol use the chosen
   timeframe; ADR always uses daily candles.
2. **Interpret.** Read the returned metrics against the rules in
   [reference.md](reference.md) — the full volatility playbook (ATR-based
   stops/targets, % of ADR used, squeeze/expansion detection).
3. **Synthesize.** Produce the structured output below. Lead with the state and
   the single most actionable implication (e.g. "compressed, expect a move" or
   "range nearly exhausted, late-entry risk").

## Payload key

`get_volatility` returns:

- `atr` — `{value, pct, period, method}`. `pct` = ATR / last price × 100.
  `method: "simple"` (simple mean of true ranges, not Wilder's smoothing).
- `adr` — `{value, pct, days, today_range, pct_of_adr_used}`. `pct_of_adr_used`
  = today's range ÷ ADR × 100. **The key "is there room left?" number.**
- `realized_vol` — `{annualized_pct, window, annualization}`. Stdev of log
  returns over `window` periods, annualized by `sqrt(periods/yr)`.
- `bollinger` — `{width, squeeze, percentile, period}`. `width` =
  (upper − lower) / mid on a 20-period band; `percentile` is where current width
  sits in its recent range (low = compressed); `squeeze: true` when in the
  bottom ~25%.
- `state` — `{label, reason}`. `expanding` / `contracting` / `neutral`.

## Output shape

```
VOLATILITY STATE
- State: [Expanding / Contracting / Neutral] — [one-line reason]
- ATR-[period] ([timeframe]): [value] ([pct]% of price)
- ADR-[days]: [value] ([pct]%) — today [today_range], [pct_of_adr_used]% used
- Realized vol (annualized): [pct]%
- Bollinger width: [value] — [squeeze? / normal] (percentile [x])

IMPLICATIONS
- Suggested stop: ~1× ATR = [value]  (min 0.5× = [value], wide 1.5× = [value])
- Realistic target: 2–3× ATR = [range]
- Room left today: [pct_of_adr_used]% of ADR used → [room / exhausted]
- Position sizing: [smaller in expansion / room to size in contraction]

READ
- [Squeeze → breakout imminent? Expansion → trend/pullback entries?
   Range exhausted → wait / fade? One clear call.]
```

## Interpretation guardrails

- **ATR is your unit of risk.** Stop ~1× ATR (0.5× = too tight, gets noise-hit;
  1.5× = wide/swing). Target 2–3× ATR for acceptable R:R. A target > 3× ATR for
  the timeframe is likely unrealistic — flag it.
- **% of ADR used is the room gauge.** < 50% → room to move; ~100%+ → daily
  range largely spent, late entries carry exhaustion/mean-reversion risk.
- **Squeeze = compression = expansion likely.** Low BBW percentile + a squeeze
  flag often precedes a strong breakout — but direction is unknown, so it lowers
  confidence in either side until structure confirms. Pair with the levels/SMC
  skills for direction.
- **Expansion ≠ chase.** Ranges growing / trending favors pullback entries in the
  trend; but extreme expansion (ATR ≫ average, or > ~2× ATR move) often precedes
  mean reversion — don't chase the last leg.
- **Volatility scales size, not direction.** Higher realized vol / wider ATR →
  smaller position for the same dollar risk; compression → room to size up.
- **Annualized realized vol** is a regime gauge (crypto often ~40–90%); compare
  it to the asset's own norm, not forex/equities.

See [reference.md](reference.md) for the complete definitions and rules.
