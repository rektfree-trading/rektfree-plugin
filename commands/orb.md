---
description: Compute and interpret Opening Range Breakout (ORB) statistics — first-break side, two-side-break rate, breakout outcome mix, and extension multiples of the opening range — for a symbol from live history.
argument-hint: [SYMBOL] [orb_minutes]
---

Compute the Opening Range Breakout statistics for the requested market and
deliver a trader-facing read of opening-range dynamics — how wide the first N
minutes of the RTH session are, how often that range breaks (above / below /
both / neither), which side breaks first, and how far price extends beyond the
range (as multiples of the range itself).

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the symbol (default `BTCUSDT`). Accept
   friendly forms ("btc" → `BTCUSDT`, "eth" → `ETHUSDT`, "nasdaq" →
   `NAS100_USD`, "gold" → `XAU_USD`). Forex/index symbols (containing `_`) work
   when `RF_OANDA_TOKEN` is set. If the user names a lookback ("last 90 days")
   pass it as `days`; if they name an opening-range length ("5-minute ORB") pass
   it as `orb_minutes` (default 15).
2. Call the `compute_orb_stats` MCP tool (server: `rektfree`) with that symbol
   (and `days` / `orb_minutes` if specified). The window uses 5m candles and is
   hard-capped at 180 days.
3. Interpret the JSON using the orb skill. Do NOT dump raw numbers — synthesize:
   the breakout rate vs the ORB-hold rate, the first-break-side skew (and how it
   reads against the `both_pct`), the avg first-break time, and the extension
   multiples (`orb_up_extension_x_size` / `orb_down_extension_x_size` — how far
   breakouts run relative to the range). Translate into positioning (e.g. "ORB
   breaks 82% of days, low first 58% but both_pct 22% → first low break is often
   a fakeout that reverses up").
4. ALWAYS state the sample window. The tool reports `window.orb_days` and each
   block's `n` — a recent live snapshot, NOT the full-history dashboard figures.
   Say so; treat small samples with caution.
5. For **24/7 crypto the RTH open is synthetic** (13:30 UTC, US equities open).
   Note that ORB is most reliable on forex/indices, which have a real cash open.
6. If the tool returns an `error` (too few days, unknown symbol, or forex without
   an OANDA token), say so plainly and suggest a valid symbol.

Keep it concise and decision-oriented — a trader should be able to act on it.
