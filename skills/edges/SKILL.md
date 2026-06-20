---
name: edges
description: >-
  Edge discovery / pattern mining for crypto. Use whenever the user wants to
  "find edges", asks "what works best", "what are the strongest setups", "which
  conditions win most", "discover patterns", "what should I avoid", or asks
  about "anti-patterns" / losing setups for a crypto symbol (BTC, ETH, SOL,
  etc.). Pairs with the `discover_edges` MCP tool, which mines deep Binance 1H
  history, labels every SMC + session event with its win/loss and context, then
  grid-searches and ranks the conditions by edge_score.
---

# Edge Discovery Analysis

You are the analyst. The `discover_edges` MCP tool (server `rektfree`) does the
mining — it fetches deep 1H Binance candles, reuses the SMC and session
detectors to label every order-block / FVG / BOS / CHoCH / equal-level /
liquidity-sweep outcome plus session sweeps, NY continuation and Power-of-3, then
grid-searches single- and pairwise-dimension filters and ranks each cell. Your
job is to **interpret** the ranked edges into a clear, decision-oriented read.
Never just echo the list.

## Workflow

1. **Mine.** Call `discover_edges` with the `symbol` (e.g. `BTCUSDT`), plus
   `days` / `min_samples` if the user names a window or wants stricter filtering.
   Crypto only — forex pairs (containing `_`) return an error.
2. **Interpret.** Read the payload against the rules in
   [reference.md](reference.md) — what edge_score / baseline / sqrt(n) mean and
   how to read a cell as a tradeable edge vs noise.
3. **Synthesize.** Surface the strongest 2–4 **edges** and 1–2 **anti-patterns**,
   each translated into action and each with its `n` and win_rate-vs-baseline.

## How the ranking works (so you read it right)

- **baseline** = the event type's overall win rate (e.g. all FVGs fill 57% of
  the time). It's the reference every filtered cell is measured against.
- **win_rate** = the cell's win rate under its filters.
- **edge_score = (win_rate − baseline) × sqrt(n)**. Positive = the condition
  wins MORE than baseline (an edge); negative = it wins LESS (an anti-pattern).
- **Why sqrt(n)?** Lift alone is misleading: "100% of 4" has a +huge lift but
  near-zero reliability. Multiplying by sqrt(n) discounts thin samples so a
  durable "62% of 130" outranks a flukey "90% of 6". The list is already sorted
  for you (edges strongest-positive first; anti_patterns most-negative first) —
  trust the order, but still read each `n`.

## Overfitting caveat (state this every time)

This is **recent-sample exploration, not gospel**:
- The tool samples only the **last ~N days** it fetched live (`window.days`,
  default ~180), NOT the full history the hosted dashboard mines. Numbers differ.
- A grid-search tests **many cells**, so by chance alone some will look like
  edges (multiple-comparisons / overfitting). `min_samples` + sqrt(n) blunt this
  but don't remove it.
- Every surfaced edge is a **hypothesis to validate forward**, not a guarantee.
  Be especially skeptical of a high edge_score riding on a small `n`.
- There is **no macro dimension** here.

## Payload key

- `baselines.{event_type}` — overall win rate per pattern (0–100). Win means:
  OB held, FVG filled, BOS continued, CHoCH/EQ reversed, sweep succeeded, session
  sweep reversed (faded), NY continued London, Power-of-3 distribution ran.
- `edges[]` / `anti_patterns[]` — each
  `{event_type, filters, n, win_rate, baseline, edge_score}`. `filters` is the
  condition combo (e.g. `{session: london, side: both}`).

## Output shape

```
STRONGEST EDGES
- <event_type> when <filters>: win_rate% vs baseline% (n=N, score) → action
- ... (top 2–4 by edge_score)

AVOID (ANTI-PATTERNS)
- <event_type> when <filters>: win_rate% vs baseline% (n=N) → why to skip
- ... (top 1–2)

SAMPLE & CAVEAT: window.days days, recent snapshot. Mined edges are hypotheses
to validate, not guarantees — low-n cells especially.
```

## Interpretation guardrails

- **Read the lift, not just the rate.** A 60% cell is only an edge if baseline is
  lower. Always quote win_rate **vs baseline**.
- **edge_score blends lift × sample.** Don't re-rank by raw win_rate — a higher
  win_rate on tiny `n` is weaker, which is exactly why it sits lower.
- **Pairwise > single isn't automatically better.** A two-filter cell with a
  bigger score but a small `n` is more overfit-prone than a single-filter cell.
- **Anti-patterns are real edges too** — "don't take this setup here" saves more
  than a marginal long.
- **Never present a mined edge as a rule.** Frame as "worth testing", cite `n`,
  and attach the recent-sample caveat every time.

See [reference.md](reference.md) for the complete definitions and rules.
