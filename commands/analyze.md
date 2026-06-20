---
description: Full multi-factor analysis of a crypto market — weaves SMC, key levels, Market Profile, order flow, and the confluence score into one trader-grade brief with a bias, plan, and invalidation.
argument-hint: [SYMBOL] [timeframe]
---

Produce a complete, decision-oriented trading brief for the requested crypto
market by combining every analysis tool in this plugin. This is the flagship
read — lead with a bias and a plan, not a data dump.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. First token = Binance symbol (default `BTCUSDT`); accept
   "btc"→`BTCUSDT`, "eth"→`ETHUSDT`, "sol"→`SOLUSDT`. Second token = the entry
   timeframe (default `1h`). If a forex pair (`_`) is given, say it's not
   supported and suggest a crypto symbol.

2. Gather data by calling the MCP tools (server `rektfree`). Prefer running them
   together:
   - `analyze_smc` on a **higher timeframe** (`4h`, or `1d` if the entry TF is
     `4h`) for HTF bias, **and** on the entry timeframe for MTF structure.
   - `get_levels` for the D/W/M + session level map.
   - `get_market_profile` on the entry timeframe for POC / VAH / VAL.
   - `get_orderflow` (use `5m` or `15m`) for delta / CVD / absorption — crypto
     only; skip gracefully if it errors.
   - `get_derivatives` for funding / OI / long-short / taker positioning — adds
     the leverage/squeeze dimension; skip gracefully if it errors.
   - `scan_confluence` for the structural 0–N grade.
   If any single tool errors (rate limit, etc.), continue with the rest and note
   the gap — don't abort the whole brief.

3. Synthesize using the **synthesis skill** (top-down: HTF bias → MTF
   confirmation → entry trigger; weigh conflicts with its resolution rules; score
   confluence High/Medium/Low). Cross-reference the factors: does POC/VAH/VAL
   line up with an OB or FVG? Does order flow confirm or diverge from structure?
   Where is liquidity resting (EQH/EQL, prior session/day H-L)?

4. Output the synthesis skill's brief format: BIAS + confidence, STRUCTURE, KEY
   LEVELS, ORDER FLOW, SESSION CONTEXT, CONFLUENCES, TRADE IDEA (entry / target /
   invalidation, only if medium+ confidence), and RISKS. Respect the confluence
   tool's `min_score` when judging whether an actual setup exists.

Keep it tight and actionable — a trader should be able to act on the brief or
clearly see why there's no trade right now.
