---
description: Scan a watchlist of crypto symbols and rank them by Smart Money confluence score. Use to triage the market — "where are the setups right now?"
argument-hint: [SYMBOLS...]
---

Scan the market for the highest-confluence crypto setups and present a ranked,
actionable shortlist.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. If symbols are given (e.g. "btc eth sol" or
   "BTCUSDT, SOLUSDT"), pass them through; accept "btc"→`BTCUSDT`, etc. If none
   are given, leave `symbols` empty to use the default liquid crypto watchlist.
   For non-crypto markets you can pass a single **preset keyword** as the whole
   `symbols` string (case-insensitive): `crypto`, `forex`/`fx`, `metals`, or
   `indices`/`index` — these expand to a curated watchlist. The forex, metals,
   and indices presets (and any individual underscore symbol like `EUR_USD`,
   `XAU_USD`, or an index such as `NAS100_USD`, `SPX500_USD`, `US30_USD`) route
   to OANDA and **need `RF_OANDA_TOKEN`** set; crypto needs no key.
2. Call the `scan_market` MCP tool (server: `rektfree`) with those symbols. If
   the user only wants tradable setups, pass `only_actionable: true`.
3. Interpret the ranked results with the scan/confluence skill. Lead with the
   names that **meet `min_score`** (the actionable ones), each with its
   direction, score, the key factors behind it, and the structural target /
   invalidation. Then briefly note the near-misses. If nothing meets threshold,
   say so plainly — "no A+ setups right now" is a valid, useful answer.
4. Mention any symbols under `errors` (skipped/failed) so the user knows the
   coverage.

Keep it scannable — a ranked shortlist a trader can act on, not a wall of JSON.
