---
name: tpo
description: >-
  Market Profile / TPO analysis for crypto. Use whenever the user asks about
  market profile, TPO, Point of Control (POC), Value Area, VAH/VAL, value-area
  high/low, naked POC, profile shape (P/b/D), initial balance, day type, where
  fair value is, or whether a crypto market (BTC, ETH, SOL, etc.) is balanced vs
  imbalanced. Pairs with the `get_market_profile` MCP tool, which fetches
  Binance candles and returns the computed TPO sessions.
---

# Market Profile / TPO Analysis

You are the analyst. The `get_market_profile` MCP tool (server `rektfree`) does
the computation — it fetches Binance candles, groups them into sessions, and
returns per-session TPO profiles (POC, VAH/VAL, buckets). Your job is to
**interpret** them into a clear, decision-oriented read of fair value, balance,
profile shape, and bias. Never just echo the JSON buckets.

## Workflow

1. **Fetch.** Call `get_market_profile` with the `symbol` (e.g. `BTCUSDT`) and a
   `timeframe` (default `1h`). Crypto only — forex pairs (containing `_`) return
   an error. The timeframe sets the session grouping: 1h → daily sessions,
   4h → weekly, 1d/1w → monthly, 5m/15m → intraday.
2. **Interpret.** Read the returned `sessions`, `last_price`, and the per-session
   `buckets`/`poc`/`vah`/`val` against the rules in
   [reference.md](reference.md) — the full TPO playbook (POC magnet, value-area
   80% rule, profile shapes, initial balance, day types).
3. **Synthesize.** Produce the structured output below. Lead with where price
   sits relative to value and the nearest POC; a trader should be able to act on
   it.

## Label key

Each entry in `sessions` describes one profile (oldest→newest):

- `label` — the session bucket key (e.g. a date `2026-06-19`, a week `2026-W25`,
  or a month `2026-06`, depending on timeframe).
- `poc` — Point of Control: the most-traded price in the session (the magnet).
- `vah` / `val` — Value Area High / Low: the band holding ~68.26% of TPOs.
- `poc_count` — TPO count at the POC; `total_tpos` — TPOs across the session.
- `tick_size` — price increment used for bucketing.
- `start_time` / `end_time` — unix seconds; `end_time` is `0` for the still-open
  **current** session (POC/VAH/VAL are developing, not final).
- `buckets[]` — `{price, count, letters, zone}` per price level, low→high.
  `count` = TPOs at that level (time spent there). `zone` is `"poc"`, `"value"`
  (inside VAH–VAL), or `"outside"`. Empty buckets are omitted.

The newest session is **last** in the list; the second-to-last is the prior
(completed) session whose POC/VAH/VAL carry forward as today's key levels.

## Output shape

```
MARKET PROFILE OVERVIEW
- Prior session POC / VAH / VAL [prices]
- Profile shape: [P (bullish) / b (bearish) / D (balanced) / B (double dist.)]
- Day type: [Normal / Normal Variation / Trend / Double Distribution]

CURRENT SESSION (developing)
- POC / VAH / VAL [prices]
- Initial Balance (first buckets) range + Narrow/Average/Wide assessment

POC ANALYSIS
- Migration across sessions: [Rising / Falling / Flat]
- Naked POCs (prior POCs price hasn't revisited) — high-probability targets
- POC vs last_price: [Above / Below / At]

VALUE AREA ANALYSIS
- last_price location: [Above VAH / Inside VA / Below VAL]
- 80% Rule applicable? (opened outside prior VA, then re-entered)
- VA widening / narrowing across sessions

PROFILE BIAS
- Bias: [Bullish / Bearish / Neutral] + reasoning
- Key levels to watch: POC, VAH, VAL (with naked POCs)
```

## Interpretation guardrails

- **POC is the most important single level** — it is a magnet; price away from it
  tends to return unless it builds value elsewhere.
- **Value Area = fair value.** Inside VA → balanced/range; above VAH → premium;
  below VAL → discount. Trade VAL→VAH in balance, follow conviction breaks.
- **80% Rule:** if price opens outside the prior VA and trades back inside it,
  there is an ~80% chance it reaches the opposite VA boundary.
- **Shape tells the story:** heavy buckets up top + thin lower tail = P (bullish);
  heavy buckets at the bottom + thin upper tail = b (bearish); bell-curve = D
  (balanced); two clusters with a thin gap = B (double distribution, the gap is a
  pivot).
- **Naked POCs are magnets** — a prior session's POC that price hasn't revisited
  is a high-probability target; flag any you can identify across sessions.
- **The current session is developing** (`end_time == 0`) — its POC/VAH/VAL are
  not final; weight the prior completed session's levels for plans.
- **Confluence amplifies** — POC/VAH/VAL aligning with a key level, OB, or FVG is
  a far stronger reaction zone. Buckets are zones, not exact ticks.

See [reference.md](reference.md) for the complete definitions and rules.
