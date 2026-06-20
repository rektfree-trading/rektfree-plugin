---
description: Compute and interpret Initial Balance (opening-range) statistics — IB size, breakout rate, first-break side, extension multiples and IB-hold rate — for a crypto symbol from live history.
argument-hint: [SYMBOL]
---

Compute the Initial Balance statistics for the requested crypto market and
deliver a trader-facing read of opening-range dynamics — how wide the first hour
of the RTH session (13:30-14:30 UTC) typically is, how often that range breaks
out (above / below / both / neither), which side breaks first, how far price
extends beyond the IB, and how often the IB simply holds.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. If the user names a lookback ("last 30 days"),
   pass it as `days`; otherwise leave the default.
2. Call the `compute_ib_stats` MCP tool (server: `rektfree`) with that symbol
   (and `days` if specified). Note the IB window needs 5-minute candles, so the
   lookback is capped at 60 days — shallower than the session/PDH tools.
3. Interpret the JSON using the ib skill. Do NOT dump the raw numbers —
   synthesize a structured read: the typical IB size (use `ib_size_pct`, which is
   comparable across price regimes), the breakout rate vs the IB-hold rate, the
   first-break side skew, the up/down extension multiples relative to IB size
   (`size_to_extension_ratio`), and any standout day-of-week pattern. Translate
   each into how a trader should position (e.g. "IB breaks out 80% of days, low
   first 55% → lean for an upside reversal after the low sweep").
4. ALWAYS state the sample window. The tool reports `window.ib_days` and each
   block's `n` — this is a recent live snapshot, NOT the full-history figures the
   hosted dashboard shows. Say so, and treat small samples with caution. Note
   `candle_source_5m_days`: days resolved on the 1H fallback are lower-resolution.
5. If the tool returns an `error` (a forex pair, an unknown symbol, or too few
   days), say so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should be able to act on it.
