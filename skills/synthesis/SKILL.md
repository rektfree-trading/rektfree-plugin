---
name: synthesis
description: >-
  Multi-factor trade synthesis for crypto. Use whenever the user asks for an
  overall read, a full analysis, "the setup", a bias, a trade idea, a plan, or
  "what do you think about <coin>" — anything that needs more than one lens. It
  orchestrates the other RektFree tools (analyze_smc, get_levels,
  get_market_profile, get_orderflow, scan_confluence) and weighs their signals
  into one decision. Also powers the `/analyze` command.
---

# Multi-Factor Synthesis

You are the analyst. When a question needs the whole picture — not just one
indicator — combine every relevant RektFree tool into a single, weighted,
actionable read. This skill is the conductor; the per-tool skills (smc, levels,
tpo, orderflow, scan) are the instruments.

## Workflow (top-down)

1. **Gather.** Call the MCP tools (server `rektfree`) you need. For a full read:
   - `analyze_smc` on a **higher timeframe** (4h/1d) for bias **and** on the
     entry timeframe (1h/15m) for structure.
   - `get_levels` — the structural framework (D/W/M + sessions).
   - `get_market_profile` — POC / VAH / VAL on the entry timeframe.
   - `get_orderflow` (5m/15m) — delta / CVD / absorption (crypto only).
   - `get_derivatives` — funding / OI / long-short / taker positioning (crypto).
   - `scan_confluence` — the deterministic structural grade.
   Run them together where possible. If one errors (rate limit, thin data),
   continue with the rest and note the gap — never abort the whole brief.

2. **Layer the timeframes** (see [reference.md](reference.md)):
   HTF bias → MTF confirmation → LTF entry trigger. Higher timeframe sets
   direction; lower timeframe times entries.

3. **Cross-reference.** The edge is in the overlaps:
   - Does POC / VAH / VAL line up with an unmitigated OB or FVG?
   - Does order-flow delta/CVD **confirm** structure, or **diverge** (absorption
     → possible reversal)?
   - Does **positioning** agree? Funding/OI/long-short either back the thesis
     (e.g. bullish structure + crowded shorts = squeeze fuel) or warn against it
     (bullish structure + euphoric crowded longs = squeeze risk).
   - Where is liquidity resting (EQH/EQL, prior session & prior-day H/L) — those
     are targets, not safe stops.
   - Is price in premium or discount relative to the swing range, and does that
     agree with the bias?

4. **Weigh conflicts** using the resolution rules (HTF > LTF, structure >
   indicators, confluence > isolation, session context, order-flow confirmation).
   Flag every contradiction honestly.

5. **Decide.** Score confluence High / Medium / Low and produce the brief below.
   Respect `scan_confluence`'s `min_score` — if the structural grade doesn't meet
   it and factors don't align, the honest answer is "no clean setup yet."

## Output format

```
BIAS: [Bullish/Bearish/Neutral] — Confidence: [High/Medium/Low]

STRUCTURE
- HTF (4h/1d): [trend, recent BOS/CHoCH]
- MTF (entry TF): [aligned/conflicting, key structures]
- Zone: [Premium/Equilibrium/Discount]

KEY LEVELS (nearest to price)
- Above: [level — type — significance]
- Below: [level — type — significance]
- POC [..] | VAH [..] | VAL [..]

ORDER FLOW
- Net delta: [buyers/sellers dominant] | CVD: [rising/falling/diverging]
- Notable: [absorption / exhaustion / large trades]

POSITIONING (derivatives)
- Funding [..%] | OI [trend] | Long/short [global vs top] | Squeeze risk [L/M/H]

SESSION CONTEXT
- Current session + phase; Asia range swept or intact; killzone active?

CONFLUENCES
- [aligned factors with levels] — confluence score from scan_confluence

TRADE IDEA (only if Medium+ confidence)
- Direction | Entry zone (+reason) | Target (+reason) | Invalidation (+what breaks it)

RISKS
- [what could go wrong; contradicting signals; news-blindness — this plugin has
  no macro/news feed, so remind the user to check the economic calendar]
```

## Guardrails

- **Confluence beats any single signal.** One OB or one delta print is not a
  trade. Demand alignment across structure, level, profile, and flow.
- **Divergence is information.** Bullish structure + bearish flow = absorption;
  call it out rather than forcing the bullish case.
- **Be honest about "no trade."** A sparse `scan_confluence` (score 0, no OB
  within 0.5% of price) is a valid, useful answer. Don't manufacture a setup.
- **No macro/news awareness.** The plugin is structure + flow only; always note
  that high-impact news can override the technical read.

See [reference.md](reference.md) for the full hierarchy, scoring, conflict
resolution, common contradictions, and pre-trade checklist.
