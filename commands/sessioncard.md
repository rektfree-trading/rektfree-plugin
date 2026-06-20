---
description: Compute and interpret the "Session Potential" card for ONE session (asia / london / new_york) of a crypto symbol — direction split, HOD/LOD potential, intra-session timing of the high/low, prior-session breakouts, and range extension — from live history.
argument-hint: [SYMBOL] [SESSION]
---

Compute the Session Potential card for the requested crypto market and session,
and deliver a trader-facing read of what that session tends to DO — whether the
day skews long or short when it's present, how often it sets the day's high/low,
when within the session those extremes form, how often it breaks the prior
session's range, and how far it typically expands.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. The first token is the Binance symbol (default `BTCUSDT`).
   The session is `asia`, `london`, or `new_york` (default `london`); accept
   friendly forms ("ny" / "new york" → `new_york`, "ldn" → `london`). Accept
   "btc" → `BTCUSDT`, etc. If the user names a lookback, pass it as `days`.
2. Call the `get_session_card` MCP tool (server: `rektfree`) with `symbol`,
   `session`, and `days` if specified. 1H data is light, lookback caps at 365.
   Crypto needs no key; forex/indices work when an OANDA token is set.
3. Interpret the JSON using the sessioncard skill. Do NOT dump the raw blocks —
   synthesize a structured read across the five views: the direction skew (+ any
   standout day of week), the HOD/LOD potential, WHEN the session's high vs low
   forms (timing windows, split long/short day), the prior-session breakout grid
   (does it sweep the previous session's high/low, and in what order), and the
   typical vs outlier range expansion. Translate into positioning.
4. ALWAYS state the sample window. The tool reports `window.usable_days`, a
   top-level `sample_size` + `confidence` (HIGH/MEDIUM/LOW/INSUFFICIENT), and an
   `n` on each block — this is a recent live snapshot, NOT the hosted dashboard's
   full-history figures. Say so; discount LOW/INSUFFICIENT samples.
5. Note that for `asia` the `breakouts` block is `null` (Asia has no intraday
   previous session). If the tool returns an `error` (unknown symbol/session,
   forex without an OANDA token, too few days), say so plainly and suggest a
   valid input.

Keep it concise and decision-oriented — a trader should be able to act on it.
