---
description: Classify a crypto symbol's recent trading days into archetypes (trend / range / reversal / volatile) and read how often each type occurs and what it implies.
argument-hint: [SYMBOL]
---

Classify the requested crypto market's recent days into the 11 day-type
archetypes (4 regimes: trend / london_reverse / high_volatile / rare) and
deliver a trader-facing read: what KIND of days this asset prints most, how
often, and how to position for each.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`
   if none given). Accept friendly forms like "btc" → `BTCUSDT`, "eth" →
   `ETHUSDT`, "sol" → `SOLUSDT`. If the user names a lookback ("last 60 days"),
   pass it as `days`; otherwise leave the default.
2. Call the `compute_day_type_stats` MCP tool (server: `rektfree`) with that
   symbol (and `days` if specified).
3. Interpret the JSON using the daytype skill. Do NOT dump the raw numbers —
   synthesize a structured read: the regime mix (is this asset trend-day heavy,
   reversal-prone, or chop-prone?), the top 2–3 archetypes by share and what
   each implies, the per-day-of-week tendencies, and what `today`'s
   classification means for the current session. Translate each into a stance
   (e.g. "54% high-volatile days, power-of-3 dominant → expect a London sweep
   then expansion; don't fade the first move blindly").
4. ALWAYS state the sample window. The tool reports `window.days` and
   `day_types.n` — a recent live snapshot (~90 days by default), NOT the
   full-history figures the hosted dashboard shows. Say so, and treat any
   archetype with only a handful of occurrences as noisy. Note also that D1
   candles are synthesised from 1H bars, so inside/outside-day calls can differ
   slightly from the true daily candle.
5. If the tool returns an `error` (forex pair, unknown symbol, too few days),
   say so plainly and suggest a valid crypto symbol.

Keep it concise and decision-oriented — a trader should know what kind of day
to expect and how to trade it.
