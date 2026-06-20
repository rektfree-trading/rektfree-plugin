---
name: sessioncard
description: >-
  "Session Potential" card for ONE trading session (Asia / London / New York) of
  a crypto symbol. Use whenever the user asks what a specific session tends to do
  — its long/short direction skew, how often it makes the day's high or low, WHEN
  within the session the high/low forms, whether it breaks the prior session's
  high/low (session breakouts / sweeps), or how far it expands — for a crypto
  symbol (BTC, ETH, SOL, etc.). Phrases like "London session profile", "what does
  NY usually do", "does London break Asia's range", "when does the London high
  form". Pairs with the `get_session_card` MCP tool, which fetches deep Binance
  1H history and returns the bundled per-session card.
---

# Session Potential Card (per-session profile)

You are the analyst. The `get_session_card` MCP tool (server `rektfree`) does the
computation — it fetches deep 1H Binance candles, buckets them into
Asia/London/New York sessions per UTC day, and bundles four "Session Potential"
views for the chosen session into one card. Your job is to **interpret** them
into a clear, decision-oriented session profile. Never just echo the numbers.

## Workflow

1. **Fetch.** Call `get_session_card` with `symbol` (e.g. `BTCUSDT`), `session`
   (`asia` / `london` / `new_york`), and `days` if the user names a window
   (capped at 365). Crypto needs no key; forex/indices work with an OANDA token.
2. **Interpret.** Read the five blocks against the questions below.
3. **Synthesize.** Produce the structured output below, leading with the most
   actionable edge for that session.

## Sample-window caveat (state this every time)

The tool samples only the **last ~N days** it fetches live
(`window.usable_days`), NOT the full history the hosted dashboard aggregates.
Always cite the top-level `sample_size` + `confidence` (HIGH >=50 / MEDIUM >=20 /
LOW >=5 / INSUFFICIENT) and each block's `n`; treat these as a recent snapshot.

## Payload key

- `direction` — `long_pct` / `short_pct` for days this session was present
  (long = up_leg >= down_leg), plus `by_day_of_week` (per-DOW long/short split).
- `hod_lod` — `hod_pct` (this session printed the day's HIGH), `lod_pct` (the
  LOW), `both_pct` (both extremes), `neither_pct`, with `n`.
- `timing` — `long_expected` / `short_expected`, each with a `high_window` and
  `low_window` (HH:MM-HH:MM UTC) and `high_peak_hour` / `low_peak_hour`: WHEN
  inside the session the high vs low tends to form, conditioned on the day's
  direction.
- `breakouts` — vs the PRIOR intraday session's H/L (london vs asia, new_york vs
  london): `extension_rate`, the grid (`only_h_pct` / `only_l_pct` / `both_pct` /
  `neither_pct`), and the ordering when both break (`h_then_l_pct` /
  `l_then_h_pct`). **`null` for asia** (no intraday previous session).
- `extension` — this session's own H-L range distribution: `range` and
  `range_pct` blocks (median / mean / p25 / p75) with `n`.

## Output shape

```
SESSION CARD — SYMBOL / SESSION (n=N, CONFIDENCE)
DIRECTION
- Long X% / short Y% on days this session prints; standout DOW: <day>

HOD / LOD POTENTIAL
- Makes the day's high X%, low Y%, both Z%, neither W%

TIMING (intra-session)
- High usually forms HH-HH UTC, low HH-HH UTC (note long- vs short-day shift)

BREAKOUTS vs prior session   (omit for asia)
- Breaks prior H/L E% of days; grid split; typical order (h_then_l / l_then_h)

EXTENSION
- Typical range: median range_pct% (p25-p75); outlier tail

IMPLICATION
- How to position into and through this session given the above

SAMPLE: window.usable_days days, n=N — recent snapshot, not full history
```

## Interpretation guardrails

- **Direction + HOD/LOD together = the session's role.** A session with high
  `lod_pct` and a long day-skew is the "low-of-day, then reverse up" session —
  fade its low. High `hod_pct` + short skew = the high-of-day, then fade down.
- **Timing makes it tradable.** "London makes the low" is far more useful with
  the `low_window` — that's the hour to look for the sweep + reversal.
- **Breakouts = continuation vs trap.** A high `extension_rate` with a clear
  `h_then_l` / `l_then_h` order is a sweep-then-reverse tell (it breaks one side
  of the prior range first, then the other). `neither_pct` high = inside/range
  session that respects the prior range.
- **Asia has no breakouts block** — don't invent one; focus on direction, HOD/LOD
  and extension for Asia.
- **`range_pct` over raw `range`.** The percent is comparable across price
  regimes; a wide session implies wider stops/targets.
- **Always anchor to sample size and confidence.**
