---
description: Compute and interpret ETH Profile statistics — how often the next day touches the prior day's POC / VAH / VAL, average touch time, and the RTH-range distribution — for a symbol from live history.
argument-hint: [SYMBOL]
---

Compute the ETH Profile / previous-day value-area statistics for the requested
market and deliver a trader-facing read of how reliably yesterday's profile
levels (POC / VAH / VAL) get revisited the next day — a mean-reversion / magnet
edge — plus when in the day the touch typically lands and how wide the RTH range
runs.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the symbol (default `BTCUSDT`). Accept
   friendly forms ("btc" → `BTCUSDT`, "eth" → `ETHUSDT`, "gold" → `XAU_USD`,
   "nasdaq" → `NAS100_USD`). Forex/index symbols (containing `_`) work when
   `RF_OANDA_TOKEN` is set. If the user names a lookback ("last 60 days") pass it
   as `days`.
2. Call the `compute_eth_profile_stats` MCP tool (server: `rektfree`). This is
   the heaviest stats tool (a TPO profile per day over a chronological walk), so
   `days` defaults to 90 and is hard-capped at 150.
3. Interpret the JSON using the ethprofile skill. Do NOT dump raw numbers —
   synthesize: the prev-day POC / VAH / VAL touch rates (`prev_poc_pct` etc.),
   which level is the strongest magnet, the average touch times
   (`avg_prev_*_touch_time` — early vs late in the session), and the RTH-range
   distribution. Translate into positioning (e.g. "prior POC tagged 85% of days,
   typically by 15:30 UTC → fade toward yesterday's POC early in the session").
4. ALWAYS state the sample window. The tool reports `window.profile_days` and
   `touch.n` — a recent live snapshot, NOT the full-history dashboard figures.
   Say so; treat small samples and `confidence` buckets with caution. Note
   `touch.tpo_quality_normal_pct`: low-TPO days have coarser profiles.
5. For **24/7 crypto the RTH window is synthetic** (13:30-20:00 UTC). Note this
   edge is most meaningful on forex/indices with a real cash session.
6. If the tool returns an `error` (too few days, unknown symbol, or forex without
   an OANDA token), say so plainly and suggest a valid symbol.

Keep it concise and decision-oriented — a trader should be able to act on it.
