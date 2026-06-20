---
name: levels
description: >-
  Key time-based price levels for crypto. Use whenever the user asks about
  support/resistance, daily/weekly/monthly highs and lows (PDH/PDL/PWH/PWL/
  PMH/PML), session highs and lows (Asia/London/New York), period opens, where
  liquidity is resting, price targets, or bias from levels for a crypto symbol
  (BTC, ETH, SOL, etc.). Pairs with the `get_levels` MCP tool, which fetches
  Binance candles and returns the computed level map.
---

# Key Levels Analysis

You are the analyst. The `get_levels` MCP tool (server `rektfree`) does the
computation — it fetches Binance 15m candles and returns the time-based level
map. Your job is to **interpret** it into a clear, decision-oriented read of
support, resistance, liquidity, and bias. Never just echo the JSON list.

## Workflow

1. **Fetch.** Call `get_levels` with the `symbol` (e.g. `BTCUSDT`). Crypto only
   — forex pairs (containing `_`) are not supported and the tool returns an
   error. No timeframe argument: levels are time-based (daily/weekly/monthly/
   session).
2. **Interpret.** Read the returned `levels` list and `last_price` against the
   rules in [reference.md](reference.md) — the full levels playbook (significance
   hierarchy, sweeps vs breaks, opens as bias filters, confluence).
3. **Synthesize.** Produce the structured output below. Lead with bias and the
   nearest high-confluence level; a trader should be able to act on it.

## Label key

The `levels` list uses compact labels:
- `D` / `W` / `M` = current day / week / month High & Low.
- `pD` / `pW` / `pM` = **previous** day / week / month (PDH/PDL, PWH/PWL,
  PMH/PML) — usually the most actionable references.
- `D Open` = today's open; `Mon Open` = weekly (Monday) open — bias filters.
- Session names (`Asia`, `London`, `New York`) are today's sessions; a `p`
  prefix (`pAsia`, `pLondon`, `pNew York`) marks the prior day's sessions.

## Output shape

```
KEY LEVELS MAP
- Monthly: PMH, PML, (current M H/L if relevant)
- Weekly: PWH, PWL, Mon Open
- Daily: PDH, PDL, D Open
- Sessions: Asia / London / NY highs & lows (today + prior where useful)

BIAS FROM LEVELS
- vs Mon Open / D Open → bullish/bearish per period

LEVEL INTERACTIONS
- Nearest resistance above last_price (ordered by proximity)
- Nearest support below last_price (ordered by proximity)
- Confluence zones: where levels stack within ~0.1–0.3%
- Untested levels price hasn't reached → potential targets

LIQUIDITY TARGETS
- Above price / below price (resting stops)
- Most likely next target + why
```

## Interpretation guardrails

- **Hierarchy:** Monthly > Weekly > Daily > Session > Opens. Higher-period
  levels override lower ones when they conflict.
- **Stacked levels amplify.** When a session H/L aligns with PDH/PDL or a
  weekly level inside a tight band, treat it as a high-probability reaction zone.
- **Sweeps vs breaks.** A wick beyond a level that closes back inside =
  liquidity sweep = reversal signal. A close beyond with momentum = breakout.
- **Opens are bias filters, not entries.** Above the weekly/daily open = bullish
  for that period; below = bearish. Don't trade the open itself in isolation.
- **Levels are zones, not ticks.** Expect reactions within ~0.1–0.3% of a level.
- **Don't hide stops behind obvious levels** — PDH/PDL and session extremes get
  hunted; they're targets, not safe stop locations.

See [reference.md](reference.md) for the complete definitions and rules.
