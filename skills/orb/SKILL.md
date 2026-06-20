---
name: orb
description: >-
  Opening Range Breakout (ORB) statistics. Use whenever the user asks about the
  opening range, ORB, the opening-range breakout, the first 15 minutes of the
  session, how often the opening range breaks (up/down/both/neither), which side
  breaks first, two-sided breaks, or how far price extends past the opening
  range, for any symbol (crypto BTC/ETH/SOL, or forex/indices like EUR_USD,
  NAS100_USD, XAU_USD). Pairs with the `compute_orb_stats` MCP tool, which
  fetches deep 5m history and returns the aggregated ORB stats.
---

# Opening Range Breakout (ORB) Statistics

You are the analyst. The `compute_orb_stats` MCP tool (server `rektfree`) does the
computation — it fetches deep 5m candles, measures the **opening range** (the
first `orb_minutes` of the RTH session) for each day, walks the rest of the
session for the first-break side, two-sided breaks and extensions, and returns
aggregated rates. Your job is to **interpret** them into a clear,
decision-oriented read. Never just echo the numbers.

## Workflow

1. **Fetch.** Call `compute_orb_stats` with the `symbol`, and `days` /
   `orb_minutes` if the user names them. Crypto needs no key; forex/indices
   (underscore symbols) need `RF_OANDA_TOKEN`. 5m history is heavy, so `days` is
   capped at 180.
2. **Interpret.** Read the payload against the rules in
   [reference.md](reference.md) — how to read the breakout rate, first-break
   side, two-sided breaks, and extension multiples as edges.
3. **Synthesize.** Produce the structured output below. Lead with the most
   actionable edge (usually the breakout rate and first-break-side skew).

## Synthetic-open caveat (state this for crypto)

For 24/7 crypto the RTH "open" is a **synthetic** convention pinned to the US
equities open (13:30 UTC). The ORB edge is most meaningful on **forex/indices**,
which have a real cash open. Compute it for crypto, but flag the caveat.

## Sample-window caveat (state this every time)

The tool samples only the **last ~N days** it fetches live (`window.orb_days`),
NOT the full history the hosted dashboard aggregates. Always cite the sample size
(`window.orb_days`, each block's `n`) and treat it as a recent snapshot.

## Payload key

- `window.orb_window_utc` — the opening-range window (e.g. `13:30-13:45`);
  `window.orb_days` — days with a valid ORB; `window.rth_convention`.
- `breakouts` — `outcomes.{only_h,only_l,both,neither}_pct` (mutually
  exclusive), `breakout_rate` (any side broke), `orb_hold_rate` (= neither),
  `two_side_pct` (= both), `first_break_side.{high,low,none}_pct`,
  `avg_first_break_time` (UTC HH:MM), `n`, `confidence`.
- `extension` — distributions (`median`/`mean`/`min`/`max`/`p25`/`p75` +
  `sample_size`/`confidence`) for `orb_size`, `orb_up_extension`,
  `orb_down_extension`, plus **range-relative** `orb_up_extension_x_size` and
  `orb_down_extension_x_size` (extension ÷ opening range — comparable across
  regimes; <1 = price barely clears the range, >2 = it runs).
- `day_of_week.{Mon..Sun}` — per-weekday `avg_orb_size`, `neither_pct`,
  `both_pct`, `count`.

## Output shape

```
OPENING RANGE PROFILE
- ORB window orb_window_utc, typical size (median orb_size, p25–p75)
- Breakout rate X% vs ORB-hold rate Y%

BREAKOUT DIRECTION
- First break high X% / low Y% — directional skew
- Two-side-break rate Z% (fakeout risk)
- Avg first-break time HH:MM UTC

EXTENSION
- Up/down extension as multiples of the range (do breaks run or stall?)

DAY-OF-WEEK EDGE
- Standout break / hold days

IMPLICATION
- Trade the break vs fade back inside, given hold rate + extension + two-side rate

SAMPLE: window.orb_days days, n=N — recent snapshot, not full history
```

## Interpretation guardrails

- **High breakout rate + large extension multiples = ORB works.** Trade the break
  with the opposite ORB edge as the stop.
- **High `orb_hold_rate` = range-day risk.** ORB entries get chopped — require
  extra confluence or fade the extremes.
- **First-break side ≠ winning side.** A high `first_break_side.low_pct` with a
  high `two_side_pct` usually means the *first* break (low) is a fakeout that
  reverses — read first-break and outcome mix together.
- **Range-relative extensions over raw.** `orb_*_extension_x_size` is comparable
  across assets and price regimes; raw extension scales with price.
- **Crypto = synthetic open.** Discount the ORB edge for crypto vs a real-cash
  forex/index open.
- **Anchor to sample size.** A 100% breakout rate off 6 days is noise.

See [reference.md](reference.md) for the complete definitions and rules.
