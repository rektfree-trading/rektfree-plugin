---
description: Compute and interpret Peak Points statistics — which session prints the day's high (HOD) and which prints the day's low (LOD), as marginals and a joint HOD×LOD matrix — for a crypto symbol from live history.
argument-hint: [SYMBOL]
---

Compute the Peak Points statistics for the requested crypto market and deliver a
trader-facing read of WHERE the day's extremes form — which session (Asia /
London / New York) usually prints the day's HIGH, which prints the day's LOW, and
the conditional/joint relationship between them ("if Asia made the low, which
session usually makes the high?").

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. If the user names a lookback ("last 90 days"),
   pass it as `days`; otherwise leave the default (~120).
2. Call the `compute_peak_points_stats` MCP tool (server: `rektfree`) with that
   symbol (and `days` if specified). 1H data is light, so the lookback caps at
   365 days. Forex/indices are also supported via the hosted router when an
   OANDA token is set.
3. Interpret the JSON using the peakpoints skill. Do NOT dump the raw matrix —
   synthesize a structured read: the HOD marginals (which session most often
   makes the high), the LOD marginals (which session makes the low), then the
   KEY conditional reads from the joint matrix — e.g. "when London makes the low,
   NY makes the high 60% of the time → fade the London low into an NY high." Call
   out the strongest cells and any bullish-vs-bearish-day differences from
   `by_direction`.
4. ALWAYS state the sample window. The tool reports `window.usable_days` and each
   block's `sample_size` + `confidence` (HIGH/MEDIUM/LOW/INSUFFICIENT) — this is a
   recent live snapshot, NOT the full-history figures the hosted dashboard shows.
   Say so, and treat LOW/INSUFFICIENT samples with caution.
5. If the tool returns an `error` (an unknown symbol, a forex pair without an
   OANDA token, or too few days), say so plainly and suggest a valid crypto
   symbol.

Keep it concise and decision-oriented — a trader should be able to act on it.
