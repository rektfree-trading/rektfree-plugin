---
name: peakpoints
description: >-
  Peak Points statistics for crypto — which session prints the day's high (HOD)
  and which prints the day's low (LOD). Use whenever the user asks which session
  makes the high or low of the day, when the high/low of the day usually forms,
  whether Asia/London/New York tends to set the daily extreme, "if X made the
  low which session makes the high", or about the HOD/LOD session distribution
  for a crypto symbol (BTC, ETH, SOL, etc.). Pairs with the
  `compute_peak_points_stats` MCP tool, which fetches deep Binance 1H history and
  returns the HOD×LOD marginals + joint matrix.
---

# Peak Points (HOD-session × LOD-session) Statistics

You are the analyst. The `compute_peak_points_stats` MCP tool (server `rektfree`)
does the computation — it fetches deep 1H Binance candles, buckets them into
Asia/London/New York sessions per UTC day, and for each completed day records
which session printed the day's HIGH (HOD) and which printed the day's LOW (LOD).
Your job is to **interpret** the marginals and the joint matrix into a clear,
decision-oriented read. Never just echo the numbers.

## Workflow

1. **Fetch.** Call `compute_peak_points_stats` with the `symbol` (e.g.
   `BTCUSDT`), and `days` if the user names a window (capped at 365 — 1H data is
   light). Crypto needs no key; forex/indices work when an OANDA token is set.
2. **Interpret.** Read the marginals first, then the joint matrix for the
   conditional edges.
3. **Synthesize.** Produce the structured output below. Lead with the most
   actionable conditional ("when Asia makes the low, NY makes the high X%").

## Sample-window caveat (state this every time)

The tool samples only the **last ~N days** it fetches live
(`window.usable_days`), NOT the full history the hosted dashboard aggregates. So:
- Always cite `sample_size` and the `confidence` label (HIGH >=50 / MEDIUM >=20 /
  LOW >=5 / INSUFFICIENT).
- Treat these as a **recent snapshot**, not the long-run truth.
- A clean 80% cell off 6 days is noise; the same off 200 days is signal.

## Payload key

- `hod_marginals_pct.{asia,london,new_york}` — P(this session printed the day's
  HIGH). `lod_marginals_pct` — same for the day's LOW.
- `matrix_pct[HOD][LOD]` — the JOINT probability. Outer key = session that made
  the HIGH; inner key = session that made the LOW. To answer "if Asia made the
  low, which session makes the high?", read **down the `asia` LOD column**:
  `matrix_pct["london"]["asia"]`, `matrix_pct["new_york"]["asia"]`, etc., and
  renormalise across that column. The diagonal (same session made both extremes)
  is usually small.
- `matrix` / `hod_marginals` / `lod_marginals` — the raw counts behind the
  percentages.
- `by_direction.bullish_day` / `by_direction.bearish_day` — the same matrix block
  (with its own `sample_size` + `confidence`) split by the day's net direction.

## Output shape

```
PEAK POINTS PROFILE — SYMBOL (n=N, CONFIDENCE)
HIGH OF DAY
- Most often prints in <session> (X%); runner-up <session> (Y%)
LOW OF DAY
- Most often prints in <session> (X%); runner-up <session> (Y%)

CONDITIONAL EDGE (joint matrix)
- When <session> makes the LOW, <session> makes the HIGH Z% of the time → <play>
- Strongest joint cell: HOD=<s> × LOD=<s> at W%

DIRECTION SPLIT
- Bullish vs bearish days differ in where the extremes land (if notable)

IMPLICATION
- Where to expect the day's high/low to form, and how to position around it

SAMPLE: window.usable_days days, n=N — recent snapshot, not full history
```

## Interpretation guardrails

- **Marginals vs joint.** Marginals tell you the single most likely HOD/LOD
  session; the joint matrix tells you the *pairing*, which is where the real edge
  is (the high and low sessions are correlated, not independent).
- **Read the LOD column for "low-first" plays** and the HOD row for "high-first"
  plays. Renormalise the cells you're comparing so the conditional sums to 100%.
- **The diagonal is the inside-day case.** A non-trivial diagonal means one
  session is regularly engulfing the others' ranges — a range/inside-day tell.
- **Pair with session timing.** Knowing NY usually makes the high is more
  tradable alongside *when* in NY it forms — that's the `get_session_card` tool.
- **Always anchor to sample size and confidence.**
