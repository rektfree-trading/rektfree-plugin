---
name: sessionext
description: >-
  Session-extension / range-expansion statistics for crypto. Use whenever the
  user asks how far a session runs or how often it expands beyond a prior
  session — "session extension", "how far does it run", "range expansion beyond
  session", "does London break Asia's range", "does NY extend London", how often
  a session prints the day's high/low, long-vs-short day split, or per-session
  range distributions for a crypto symbol (BTC, ETH, SOL). Pairs with the
  `compute_session_extension_stats` MCP tool, which fetches deep Binance 1H
  history and returns the extension rates and range distributions.
---

# Session-Extension Analysis

You are the analyst. The `compute_session_extension_stats` MCP tool (server
`rektfree`) does the computation — it fetches deep 1H Binance candles, buckets
them into Asia/London/New York sessions per UTC day, and measures how often and
how far each session pushes BEYOND the prior session's range. Your job is to
**interpret** it into a clear read of the range-expansion edge. Never just echo
the numbers.

## Workflow

1. **Fetch.** Call `compute_session_extension_stats` with the `symbol` (e.g.
   `BTCUSDT`), and `days` if the user names a window. Crypto only — forex pairs
   (containing `_`) return an error.
2. **Interpret.** Read the payload against the rules in
   [reference.md](reference.md) — what an extension is, how to read the grid and
   the overshoot multiple.
3. **Synthesize.** Produce the structured output below. Lead with the strongest
   extension edge (usually NY-vs-London), then the side skew, overshoot size,
   range distributions, and HOD/LOD potential.

## Sample-window caveat (state this every time)

The tool samples only the **last ~N days** it fetches live (`window.days`,
default ~90), NOT the full history the hosted dashboard aggregates. So:
- Always cite the sample size (each block's `n`).
- Treat figures as a **recent snapshot**, not the long-run truth.
- Be cautious with thin samples.

## Payload key

- `extensions.{london,new_york}` — does the session break the PRIOR session's
  range? `vs_prior_session` names the prior; `extension_rate` is % of days it
  broke at all; `only_h_pct`/`only_l_pct`/`both_pct`/`neither_pct` is the grid;
  `h_then_l_pct`/`l_then_h_pct` is the ordering when both broke;
  `avg_overshoot` (USDT) and `avg_overshoot_multiple` (× the prior session's
  range) size the push. Each carries `n`.
- `session_range.{asia,london,new_york}` — the session's own H−L distribution
  (`range` raw, `range_pct`), each an `extension_block`
  (median/mean/min/max/p25/p75 + sample_size + confidence).
- `daily_direction` — `long_day_pct` vs `short_day_pct` (up_leg ≥ down_leg),
  plus avg up/down legs.
- `hod_lod.sessions.{s}` — per-session `hod_pct` / `lod_pct` (probability that
  session prints the day's high / low), each with `n`.

## Output shape

```
EXTENSION EDGE
- London extends Asia: X% (high A% / low B%), overshoot ~M× Asia range
- NY extends London: X% (high A% / low B%), overshoot ~M× London range
- Side skew read (which extreme gets pushed more)

RANGE DISTRIBUTION
- Per session: median range% and the p25–p75 spread (typical vs outlier days)

DAY DIRECTION
- Long X% / short Y% — net directional lean

HOD / LOD POTENTIAL
- Which session most often prints the day high / low

SAMPLE: window.days days, n per block — recent snapshot, not full history
```

## Interpretation guardrails

- **High NY extension of London = London's range rarely caps the day.** Plan for
  NY expansion; don't treat the London range as the day's range.
- **The overshoot multiple matters more than the rate.** A 90% extension rate
  with a 0.2× overshoot is shallow probing; a 0.2× rate with a 2× overshoot is a
  rare-but-violent break. Read both together.
- **Side skew (only_h vs only_l) reveals directional bias** — more high-side
  extensions lean bullish expansion (and vice versa).
- **neither_pct high = the session respects the prior range** — fade the prior
  session's H/L as S/R rather than expecting a break.
- **Anchor to sample size.** Don't state a 100% extension rate off a few days as
  if it were a law.

See [reference.md](reference.md) for complete definitions and rules.
