---
name: ib
description: >-
  Initial Balance (opening-range) statistics for crypto. Use whenever the user
  asks about the initial balance, IB, the opening range, the first hour of the
  session, IB breakout / breakout rate, opening-range breakout (ORB), how far
  price extends past the opening range, or whether the opening range holds, for a
  crypto symbol (BTC, ETH, SOL, etc.). Pairs with the `compute_ib_stats` MCP
  tool, which fetches deep Binance 5m + 1H history and returns the aggregated IB
  stats.
---

# Initial Balance (Opening-Range) Statistics

You are the analyst. The `compute_ib_stats` MCP tool (server `rektfree`) does the
computation — it fetches deep 5m (with 1H fallback) Binance candles, measures the
**Initial Balance** (the first hour of the RTH session, 13:30-14:30 UTC for
crypto) for each day, walks the rest of the session for breakouts and extensions,
and returns aggregated rates. Your job is to **interpret** them into a clear,
decision-oriented read. Never just echo the numbers.

## Workflow

1. **Fetch.** Call `compute_ib_stats` with the `symbol` (e.g. `BTCUSDT`), and
   `days` if the user names a window. Crypto only — forex pairs (containing `_`)
   return an error. The IB window needs 5-minute candles, so `days` is capped at
   60 (shallower than the session/PDH tools).
2. **Interpret.** Read the payload against the rules in
   [reference.md](reference.md) — how to read IB size, breakout vs hold rate,
   first-break side, and extension multiples as edges.
3. **Synthesize.** Produce the structured output below. Lead with the most
   actionable edge (usually the breakout rate and first-break-side skew).

## Sample-window caveat (state this every time)

The tool samples only the **last ~N days** it fetches live (`window.ib_days`),
NOT the full history the hosted dashboard aggregates. So:
- Always cite the sample size (`window.ib_days`, each block's `n`).
- Treat these as a **recent snapshot**, not the long-run truth.
- Note `window.candle_source_5m_days`: days resolved on the 1H fallback are
  lower-resolution and degrade the IB precision — discount them.

## Payload key

- `window.ib_window_utc` — the IB window (e.g. `13:30-14:30`);
  `window.ib_days` — days with a valid IB.
- `breakouts` — `only_h_pct` / `only_l_pct` / `both_pct` / `neither_pct`
  (mutually exclusive outcomes), `breakout_rate` (any side broke),
  `ib_hold_rate` (= `neither_pct`, price stayed inside the IB all session),
  `first_break_high_pct` / `first_break_low_pct` / `first_break_none_pct`,
  `avg_first_break_time` (UTC HH:MM), and `n`.
- `extension` — distributions (`median`/`mean`/`min`/`max`/`p25`/`p75` + `n`)
  for `ib_size`, `ib_size_pct` (IB range as % of price — comparable across
  regimes), `ib_up_extension`, `ib_down_extension`, `max_extension`, and
  `size_to_extension_ratio` (IB size ÷ max extension; small ratio = price runs
  far beyond the IB).
- `day_of_week.{Mon..Sun}` — per-weekday `avg_ib_size_pct`, `neither_pct`,
  `both_pct`, `count`.

## Output shape

```
INITIAL BALANCE PROFILE
- Typical IB size: median ib_size_pct% (p25–p75 range)
- Breakout rate X% vs IB-hold rate Y%

BREAKOUT DIRECTION
- First break high X% / low Y% — directional skew
- Avg first-break time HH:MM UTC

EXTENSION
- Median up/down extension and max extension
- size_to_extension_ratio: do breakouts run (small ratio) or stall (large ratio)?

DAY-OF-WEEK EDGE
- Standout high/low IB-size or hold days

IMPLICATION
- ORB-trade the breakout vs fade back inside, given the hold rate and extension

SAMPLE: window.ib_days days, n=N — recent snapshot, not full history
```

## Interpretation guardrails

- **High breakout rate = ORB works.** If `breakout_rate` is high and extensions
  are large (small `size_to_extension_ratio`), the opening-range breakout is a
  real edge — trade the break with the IB edge as the stop.
- **High `ib_hold_rate` = range day risk.** If price often stays inside the IB
  all session, ORB entries get chopped — require extra confluence or fade IB
  extremes.
- **First-break side ≠ winning side.** A high `first_break_low_pct` with a high
  `both_pct` often means the *first* break (low) is a fakeout that reverses up —
  read it together with the outcome mix.
- **`ib_size_pct` over raw `ib_size`.** Raw size scales with price; the percent
  is comparable across assets and regimes. A wide IB implies wider stops/targets.
- **`size_to_extension_ratio`:** small (<1) = price runs far past the IB
  (trend-day breakouts); large (>2) = price barely clears the IB (chop).
- **Discount 1H-fallback days.** If `candle_source_5m_days` is well below
  `ib_days`, the IB resolution on those days is coarse — weight confidence down.
- **Always anchor to sample size.** A 100% breakout rate off 6 days is noise.

See [reference.md](reference.md) for the complete definitions and rules.
