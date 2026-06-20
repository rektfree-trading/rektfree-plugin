---
name: dailybias
description: >-
  TTrades daily/weekly directional bias for crypto. Use whenever the user asks
  about daily bias, today's direction, whether a market is bullish or bearish
  today, the draw on liquidity (DOL), the PDH/PDL (or PWH/PWL) target, or how
  reliable the bias has been, for a crypto symbol (BTC, ETH, SOL, etc.). Pairs
  with the `get_daily_bias` MCP tool, which fetches Binance candles and returns
  the computed bias, target levels, and hit-rate stats.
---

# Daily Bias Analysis

You are the analyst. The `get_daily_bias` MCP tool (server `rektfree`) does the
computation — it fetches Binance 1h candles, groups them into daily (or weekly)
periods, and returns the TTrades bias with its draw-on-liquidity target and
historical hit rates. Your job is to **interpret** it into a clear, decision-
oriented read: which way to lean and the target. Never just echo the JSON.

## Workflow

1. **Fetch.** Call `get_daily_bias` with the `symbol` (e.g. `BTCUSDT`) and
   `period` (`D` daily, default; `W` weekly). Crypto only — forex pairs
   (containing `_`) are not supported and the tool returns an error. No
   timeframe argument: bias is time-based.
2. **Interpret.** Read `current_bias`, `current_reason`, the prev-high/low
   target levels, and `stats` against the rules in [reference.md](reference.md)
   — the full TTrades bias playbook (the six rules, DOL, raid, close-through).
3. **Synthesize.** Produce the structured output below. Lead with the bias, the
   rule behind it, and the DOL target; a trader should be able to act on it.

## How the bias is set

At each new day, the engine compares **yesterday's** close/high/low against the
**day-before's** high/low (PDH/PDL):

- Close above PDH → **bullish**; close below PDL → **bearish**.
- Wicked above PDH but closed back inside → **bearish** (failed breakout).
- Wicked below PDL but closed back inside → **bullish** (failed breakdown).
- Stayed inside PDH/PDL → **continuation** of the prior direction.
- Outside bar closed inside → **no bias** (neutral).

The **draw on liquidity (DOL)** is `current_prev_high` when bullish (target PDH)
and `current_prev_low` when bearish (target PDL). The opposite level is the
invalidation side.

## Output shape

```
DAILY BIAS
- Direction: <bullish/bearish/neutral> — <current_reason>
- Draw on liquidity (target): PDH/PDL @ <price>
- Invalidation side: <opposite level @ price>

CONFIDENCE
- Success rate for this direction: <stats.{bias}.success_rate>% over <count> days
- Close-through rate: <close_through_rate>% (high = genuine moves, low = DOL is a reversal/grab zone)

THE PLAN
- Wait for a manipulation move away from the DOL (often a London-open sweep against the bias)
- Enter in the bias direction at an OB/FVG after a CHoCH
- Target the DOL; invalidate on a close beyond the opposite level
```

## Interpretation guardrails

- **Rules 1–4 are strong** (clear close/wick relationship); **Rule 5** (inside
  day) is a weaker continuation assumption; **Rule 6** (outside bar) is no
  signal — say so.
- **DOL is a target, not a stop.** PDH/PDL get hunted; never hide stops there.
- **Low close-through rate** means the DOL tends to be a liquidity grab and
  reversal zone, not a breakout — temper continuation expectations.
- **Align with structure and sessions.** Bias + matching SMC BOS/CHoCH = high
  confidence; bias against structure = caution. Asia builds the range London
  sweeps in the bias direction.
- **Neutral means stand aside** — no directional edge today.

See [reference.md](reference.md) for the complete definitions and rules.
