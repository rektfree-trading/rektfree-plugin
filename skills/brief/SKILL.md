---
name: brief
description: >-
  Forward-looking pre-session trading brief for crypto. Use whenever the user
  asks for a "brief", a "pre-session" read, a "game plan", "what should I watch",
  "plan for the session" / "plan for the day", or "what's coming up". Unlike a
  snapshot analysis, this frames the session AHEAD: it anchors to the trading-day
  clock (get_session_clock), pulls the read (analyze_smc, get_levels,
  get_market_profile, get_derivatives, get_volatility, get_correlations,
  get_orderflow) plus this symbol's session tendencies
  (compute_session_stats), and produces a bias, watch-list, and if-then plan for
  the upcoming session. Also powers the `/brief` command.
---

# Pre-Session Brief

You are the analyst preparing a trader for the session **ahead** — not narrating
the present. A `/analyze` answers "what is the market doing now?"; a brief
answers "what do I walk into the next session expecting, and what's my plan?"
This skill is the conductor: it anchors to the clock, borrows the synthesis
skill's cross-referencing, and turns it forward into a game plan.

## Workflow (clock → read → plan)

1. **Anchor the clock.** Call `get_session_clock` (server `rektfree`, no args)
   **first**. It returns the current `session`/`phase`, the `next_session` and
   `minutes_until_next_session`, and the active-or-next `killzone`. Everything
   below is framed around the **upcoming** session and killzone this returns.

2. **Gather the read.** Call the analysis tools (run together where possible):
   - `analyze_smc` on a **higher timeframe** (4h/1d) for bias **and** on the
     entry timeframe (1h/15m) for structure.
   - `get_levels` — the D/W/M + session framework. Flag prior-session and
     prior-day H/L: those are the liquidity pools the next session targets.
   - `get_market_profile` — POC / VAH / VAL on the entry timeframe.
   - `get_derivatives` — funding / OI / long-short / taker positioning (crypto).
   - `compute_session_stats` — **the spine of a pre-session brief**: this
     symbol's real sweep rates, NY continuation, Power-of-3, day-of-week edge.
   - `get_volatility` — ATR / ATR% / ADR, % of ADR already used, realized vol,
     squeeze state. This sizes the plan: ~1× ATR stop distance, 2–3× ATR target
     distance, and how much of the daily range is *already spent* (exhaustion).
   - `get_correlations` — per-symbol r vs a base (e.g. BTC for alts). Flag any
     |r| > ~0.5 alignment or divergence that confirms or warns the bias.
   - `get_orderflow` — **crypto only**: delta / CVD / footprint at the levels.
     Skip it for forex/metals/indices (it returns a crypto-only message there).
   - `scan_confluence` — the deterministic structural grade.
   If one errors (rate limit, thin data), continue with the rest and note the
   gap — never abort the whole brief.

3. **Layer the timeframes** (see [reference.md](reference.md)): HTF bias → MTF
   confirmation → LTF trigger. Higher timeframe sets direction; the upcoming
   killzone times the entry.

4. **Map the stats to the upcoming session.** This is what makes it a brief, not
   a snapshot:
   - **Into London** → cite the Asia-sweep rate and *which side* sweeps more,
     and the post-sweep reversal rate (fade vs. continuation).
   - **Into New York** → cite the London-sweep + NY continuation rate; will NY
     continue London or reverse it?
   - **Into Asia / post-NY** → frame accumulation: define the range that London
     will act on, and set up tomorrow.
   Cite real numbers with their sample size ("London sweeps Asia 68% of days,
   n=84") — never generic theory. Treat `compute_session_stats` as a recent
   snapshot, not the long-run law.

5. **Cross-reference** (the synthesis edge): do POC/VAH/VAL line up with an
   unmitigated OB/FVG? Where is resting liquidity (EQH/EQL, prior session/day
   H-L) the next session will hunt? Is price premium/discount, and does that
   agree with the bias? Does positioning back the thesis or warn (crowded longs
   into a bullish setup = squeeze risk)? Use `get_volatility` to convert the
   plan into distances (stop ≈ 1× ATR, targets 2–3× ATR) and to gauge
   exhaustion (% of ADR already used — a session that has spent most of its ADR
   has less room to run). Use `get_correlations` to confirm or warn the bias
   (an aligned base like BTC leading the same way strengthens it; a divergence
   is a caution). For crypto, use `get_orderflow` to see whether delta/CVD
   backs the structural read at the levels.

6. **Plan forward.** Build a concrete **if-then** watch-list keyed to the
   upcoming session and its killzone, every branch with an invalidation. Respect
   `scan_confluence`'s `min_score` — if nothing aligns, the honest brief is "no
   clean setup into this session; here is the watch-list and the triggers."

## Output format

```
SESSION CLOCK
- Now: [session + phase], [Xm] into it | Next: [session] in [Xh Ym]
- Killzone: [active NAME, Ym left | next NAME in Xh Ym]
- This brief frames the [upcoming session] open.

BIAS & CONTEXT
- HTF (4h/1d): [trend, last BOS/CHoCH] — Confidence: [High/Medium/Low]
- Zone: [Premium/Equilibrium/Discount] within the swing range
- Narrative: "Price is [doing X] after [event], heading into [session]."

KEY LEVELS FOR THE SESSION (nearest first)
- Above: [level — type — role: resistance / liquidity target / magnet]
- Below: [level — type — role]
- POC [..] | VAH [..] | VAL [..]
- Liquidity the next session hunts: [prior session/day H-L, EQH/EQL]

VOLATILITY & SIZING
- ATR [..] ([..]% of price) | ADR [..] — [X]% of ADR already used ([room left/exhausted])
- Stop ≈ 1× ATR ([..]) | realistic targets 2–3× ATR ([..] / [..])
- Squeeze: [on/off] — [expansion likely / range-bound risk]

STATISTICAL EDGE (this symbol, recent sample)
- [Upcoming-session tendency with the real rate + sample size]
- [Day-of-week note if notable] | Power-of-3 occurrence/success if relevant

POSITIONING (derivatives)
- Funding [..%] | OI [trend] | Long/short [global vs top] | Squeeze risk [L/M/H]

CROSS-ASSET
- vs [base]: r = [..] — [aligned, confirms bias / diverging, caution]
- [Other notable |r|>0.5 correlation or divergence, or "nothing notable"]

ORDER FLOW (crypto only)
- Delta/CVD [..] | footprint [absorption / initiative at level ..]
- (Forex/metals/indices: "n/a — no tick data")

SESSION PLAYBOOK ([upcoming session])
- Primary scenario for the open + the stat that backs it
- Secondary scenario

WATCH-LIST / IF-THEN PLAN
- IF [price/level/sweep at TIME or killzone] THEN [action] — invalidation [level]
- IF [alternate trigger] THEN [action] — invalidation [level]
- (Only present Medium+ confidence ideas; else "no clean setup — wait for [trigger]")

RISKS
- [what could go wrong; contradicting signals]
- No macro/news feed here — check the economic calendar for the session window.
```

## Guardrails

- **Forward, not present.** Frame everything toward the upcoming session; don't
  just describe the current candle.
- **Cite real stats, not theory.** "London sweeps Asia 68% (n=84)" beats "London
  often sweeps Asia." Always anchor to sample size; thin buckets (<8) are weak.
- **Every plan branch needs an invalidation.** A watch-list item without a "what
  breaks it" line is not a plan.
- **Confluence beats any single signal.** One OB or one funding print is not a
  setup; demand alignment, and be honest about "no trade into this session."
- **Killzone timing is the trigger clock.** Tie if-then branches to the active or
  next killzone from `get_session_clock`.
- **No macro/news awareness.** Structure + flow + stats only; high-impact news
  can override the technical read — always say so.

See [reference.md](reference.md) for the session-by-session playbook, killzone
timing, the Power-of-3 (AMD) framing, and how to build the if-then plan.
