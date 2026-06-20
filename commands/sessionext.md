---
description: Measure how often and how far a crypto symbol's sessions extend beyond the prior session's range (London vs Asia, NY vs London) and read the range-expansion edge.
argument-hint: [SYMBOL]
---

Compute the session-extension statistics for the requested crypto market and
deliver a trader-facing read of range expansion — how often London pushes past
Asia's range, how often NY pushes past London's, which side gets extended, how
far the overshoot runs, and which session prints the day's high/low.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. If the user names a lookback ("last 60 days"),
   pass it as `days`; otherwise leave the default.
2. Call the `compute_session_extension_stats` MCP tool (server: `rektfree`)
   with that symbol (and `days` if specified).
3. Interpret the JSON using the sessionext skill. Do NOT dump the raw numbers —
   synthesize a structured read: the extension rate for London (vs Asia) and NY
   (vs London), which side gets extended more (only_h vs only_l), the typical
   overshoot size (`avg_overshoot_multiple` of the prior range), each session's
   range distribution (median vs outliers), the long/short day split, and which
   session most often prints HOD/LOD. Translate each into a stance (e.g. "NY
   extends London 97% of days, overshoots ~1.2× London's range → London's range
   is rarely the day's range; plan for NY expansion").
4. ALWAYS state the sample window. The tool reports `window.days` and each
   block's `n` — a recent live snapshot (~90 days by default), NOT the
   full-history figures the hosted dashboard shows. Say so, and treat thin
   samples with caution.
5. If the tool returns an `error` (forex pair, unknown symbol, too few days),
   say so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should be able to act on the
expansion edge.
