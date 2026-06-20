---
name: orderflow
description: >-
  Order flow / footprint analysis for crypto. Use whenever the user asks about
  order flow, footprint, volume delta, CVD (cumulative volume delta),
  buying/selling pressure, absorption, exhaustion, imbalances, stacked
  imbalances, large/whale trades, aggressive buyers vs sellers, or whether a
  move is supported by real flow for a crypto symbol (BTC, ETH, SOL, etc.).
  Pairs with the `get_orderflow` MCP tool, which reconstructs footprints from
  Binance aggregated trades and returns per-price-level buy/sell volume, delta,
  and CVD.
---

# Order Flow Analysis

You are the analyst. The `get_orderflow` MCP tool (server `rektfree`) does the
data work — it pages Binance's keyless aggregated-trades endpoint and rebuilds
footprint candles (per-price-level buy/sell volume, delta, CVD, large trades).
Your job is to **interpret** it into a clear, decision-oriented read of who is
in control and whether the move is supported or failing. Never just echo the
JSON.

## Workflow

1. **Fetch.** Call `get_orderflow` with the `symbol` (e.g. `BTCUSDT`) and a
   `timeframe` of `5m`, `15m`, or `1h` (default `5m`). Crypto only — forex pairs
   (containing `_`) return an error, and OANDA has no tick data anyway. Use the
   default candle count unless the user wants more history (max 50).
2. **Interpret.** Read the returned `candles` and `cvd` against the rules in
   [reference.md](reference.md) — the full order-flow playbook (delta, CVD,
   absorption, exhaustion, footprint imbalances, large trades, trade counts).
3. **Synthesize.** Produce the structured output below. Lead with the order-flow
   bias and the single most important signal; a trader should be able to act on
   it.

## Payload key

- Each candle has `timestamp` (unix sec, bucket start), `tick_size`,
  `buy_volume`/`sell_volume`, `buy_count`/`sell_count`, `delta`
  (`buy_volume − sell_volume`), `price_levels`, and `large_trades`.
- `price_levels` is a dict keyed by stringified price → `{bv, sv, bc, sc}`
  (buy volume, sell volume, buy count, sell count at that tick).
- `large_trades` entries are `{t, p, v, q, s}` (time, price, volume, quote
  value, side `"buy"`/`"sell"`).
- Top-level `cvd` is the running cumulative delta, one entry per candle.
- `truncated: true` means the trade window was capped — earliest candles may be
  partial.

## Output shape

```
ORDER FLOW SUMMARY
- Current candle delta: [positive/negative, magnitude]
- CVD trend: [Rising / Falling / Flat]
- CVD vs price: [Confirming / Diverging]

DELTA ANALYSIS
- Recent delta pattern (last 5–10 candles)
- Notable delta spikes / divergences vs candle direction

FOOTPRINT DETAIL
- Significant imbalances (price levels with 3:1+ bv/sv or sv/bv)
- Stacked imbalances (3+ consecutive same-side)
- High-volume price levels (intra-candle point of control)

ABSORPTION / EXHAUSTION
- Active absorption (delta vs price diverging at high volume)
- Recent exhaustion (volume/delta spike at an extreme then stall)

LARGE TRADES
- Recent large trades and any clustering at a price level
- Institutional bias from large trades

ORDER FLOW BIAS
- Overall bias: [Bullish / Bearish / Neutral]
- Confidence: [High / Medium / Low]
- Key signal + invalidation
```

## Interpretation guardrails

- **Delta confirms or denies price.** Delta matching candle direction =
  healthy; delta opposing it = absorption / warning.
- **Divergences are the strongest signals.** Price up + CVD down (or vice
  versa) = the move is running on fumes; expect reversal.
- **Absorption at a level is institutional.** Heavy one-sided delta with price
  refusing to move = a big passive player defending that level.
- **Exhaustion marks turns.** A volume/delta spike at a swing extreme followed
  by a stall or opposite candle = likely reversal.
- **Stacked imbalances show committed flow.** 3+ consecutive price levels with
  3:1+ ratios in one direction = institutional campaign.
- **Context multiplies reliability.** Order-flow signals at key levels (PDH/PDL,
  POC, OB, session H/L) are far more reliable than in open space — cross-
  reference with the levels / SMC / TPO skills when available.
- **Few large trades > many small ones.** Low count + high volume = institutional;
  high count + small volume = retail, less reliable.

See [reference.md](reference.md) for the complete definitions and rules.
