---
description: Grade a crypto setup with the 0–N Smart Money confluence score (1H + 4H). Returns a structural go/no-go read with factors, target, and invalidation. No AI, no macro/DB inputs.
argument-hint: [SYMBOL]
---

Scan the requested crypto market for a high-confluence setup and deliver a
trader-facing go/no-go read built on the structural confluence score.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. No timeframe argument — the scan always stacks
   1H entry structure against the 4H bias.
2. Call the `scan_confluence` MCP tool (server: `rektfree`) with that symbol.
3. Interpret the JSON using the scan skill. Do NOT dump the raw factor list —
   synthesize a verdict: the score vs `min_score`, the direction and whether it
   is counter-trend, which confluence factors fired (and which high-value ones
   are missing), and the structural `target` / `invalidation` with the implied
   risk:reward.
4. Lead with the go/no-go call:
   - **Score ≥ `min_score`** (and counter-trend setups ≥ 8) → a qualifying
     structural setup. Describe the entry zone, target, and invalidation.
   - **Score < `min_score`** → no qualifying setup right now. Say so plainly and
     name what is missing (most often: no order block aligned with price, which
     forces score 0).
5. Always state the disclaimer in-line: this is a STRUCTURAL grade only — no AI,
   no macro calendar, no order-flow/derivatives, no avoid-signatures. The
   killzone/silver-bullet factors, if present, carry **zero weight** (kept for
   context after recalibration). Treat the score as a confluence checklist, not
   a black-box signal.
6. If the tool returns an `error` (e.g. a forex pair, or an unknown symbol), say
   so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should be able to act on it,
with the risk clearly framed.
