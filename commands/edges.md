---
description: Mine a crypto symbol's recent history for statistically significant edges and anti-patterns (which setups win more / less than baseline), grid-searched and ranked by edge_score.
argument-hint: [SYMBOL]
---

Mine the requested crypto market for statistical edges and deliver a
trader-facing read: which conditions make a setup win **more** than its baseline
(edges), which make it win **less** (anti-patterns to avoid), and how much to
trust each one given its sample size.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. If the user names a lookback ("last 90 days"),
   pass it as `days`; if they want stricter/looser filtering, pass `min_samples`.
2. Call the `discover_edges` MCP tool (server: `rektfree`) with that symbol (and
   `days` / `min_samples` if specified).
3. Interpret the JSON using the edges skill. Do NOT dump the raw list —
   surface the **strongest few** edges and the **strongest few** anti-patterns,
   each translated into how a trader should act, and each with its `n`. For each
   one, state the win_rate vs the baseline so the lift is concrete (e.g.
   "London-sweeps-both reverses 76% vs a 49% baseline, n=46 → strong fade
   signal"). Lead with the highest-`edge_score` items; the ranking already
   blends lift × sample size for you.
4. ALWAYS carry the caveat. These are **recent-sample edges** mined from the
   last `window.days` of live data (default ~180), NOT the full-history figures
   the hosted dashboard would show. A grid-search tests many cells, so some
   apparent edges are luck (multiple-comparisons / overfitting). Frame them as
   **hypotheses to validate forward**, not guarantees — and be especially wary
   of low-`n` cells even when their edge_score looks big.
5. If the tool returns an `error` (a forex pair, an unknown symbol, or too few
   candles), say so plainly and suggest a valid crypto symbol or a deeper window.

Keep it concise and decision-oriented — a trader should leave with 2–4 edges to
test and 1–2 things to avoid, each with its sample size and the exploration
caveat attached.
