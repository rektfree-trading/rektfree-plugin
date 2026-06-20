---
description: Forward-looking pre-session trading brief for a crypto market — where we are in the trading day, the levels that matter for the session ahead, the session's statistical tendencies, bias, positioning, and a watch-list / if-then game plan.
argument-hint: [SYMBOL]
---

Produce a forward-looking PRE-SESSION brief for the requested crypto market.
Unlike `/analyze` (a snapshot read of *now*), this brief is about the session
**ahead**: anchor to the trading-day clock, then frame the levels, stats, and
plan a trader should walk into the next session with.

Request: `$ARGUMENTS`

Steps:

1. **Anchor the clock first.** Call `get_session_clock` (server `rektfree`, no
   args). It tells you the current session + phase, what session is next and how
   long until it, and whether a killzone is active or imminent. The whole brief
   is framed around the **upcoming** session this returns.

2. Parse the symbol. First token = Binance symbol (default `BTCUSDT`); accept
   "btc"→`BTCUSDT`, "eth"→`ETHUSDT`, "sol"→`SOLUSDT`. A forex pair (`_`) isn't
   supported — say so and suggest a crypto symbol.

3. Gather the read via the **synthesis** skill / the analysis tools (prefer
   running them together):
   - `analyze_smc` on a **higher timeframe** (`4h`/`1d`) for HTF bias **and** on
     the entry timeframe (`1h`/`15m`) for structure.
   - `get_levels` — the D/W/M + session level map (note prior-session and
     prior-day H/L: those are the liquidity the next session hunts).
   - `get_market_profile` (entry TF) — POC / VAH / VAL.
   - `get_derivatives` — funding / OI / long-short / taker positioning.
   - `compute_session_stats` — **the heart of a pre-session brief**: this
     symbol's actual sweep rates, NY continuation, Power-of-3, day-of-week edge.
     Cite the real numbers (e.g. "London sweeps Asia 70% of days here").
   - `scan_confluence` — the deterministic structural grade.
   If any single tool errors (rate limit, thin data), continue with the rest and
   note the gap — never abort the whole brief.

4. Synthesize forward, using the **brief** skill (and the synthesis playbook for
   the cross-referencing). Lead with where we are in the day and what's coming,
   then the levels that matter *for that session*, the statistical tendencies
   that shape it, the bias, positioning, and a concrete if-then plan. Map the
   stats to the upcoming session: into London → cite the Asia-sweep rate and
   which side; into NY → cite the continuation rate; into Asia/post-NY → frame
   accumulation and tomorrow's setup. Tie killzone timing from the clock to the
   plan ("London Open KZ in 90m — watch for the Asia sweep then").

5. Output the **brief** skill's pre-session format: SESSION CLOCK, BIAS &
   CONTEXT, KEY LEVELS FOR THE SESSION, STATISTICAL EDGE, POSITIONING, SESSION
   PLAYBOOK, WATCH-LIST / IF-THEN PLAN, and RISKS. Every plan branch needs an
   invalidation. Respect `scan_confluence`'s `min_score` — if nothing aligns,
   the honest answer is "no clean setup into this session; here's the watch-list."

Keep it tight, forward-looking, and actionable — a trader should be able to set
alerts and a plan off this before the session opens. This plugin has no
macro/news feed, so always remind the user to check the economic calendar for
the session window.
