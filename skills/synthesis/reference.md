# Synthesis — Reference Playbook

Combine all available analysis lenses into a comprehensive, actionable trading
brief. Weigh conflicting signals, score confluence, and produce a structured
pre-trade assessment. This is the cross-referencing layer that sits on top of the
single-factor skills (smc, levels, tpo, orderflow, scan).

---

## Analysis Hierarchy

### Step 1 — HTF bias (4h / 1d / 1w)
- Use `analyze_smc` `trend_bias` from the higher timeframe.
- Is price in **premium** or **discount** of the swing range (`swing_high` →
  `swing_low`)? Buy discount, sell premium, in line with trend.
- Weekly/daily levels (`get_levels`: `W`, `M`, `pW`, `pM`, `Mon Open`) provide
  the structural framework and the bias filter (above/below the open).

### Step 2 — MTF confirmation (1h)
- Does the entry-timeframe structure align with HTF? (BOS in the same direction
  = aligned; a CHoCH against HTF = caution.)
- Are there **unmitigated** OBs / FVGs in the direction of the bias?
- Where is POC (`get_market_profile`) relative to current price?

### Step 3 — LTF entry trigger (5m / 15m)
- Wait for a CHoCH on the lower timeframe **at an HTF key level**.
- Enter at the OB / FVG that formed *after* the CHoCH.
- Use order flow (`get_orderflow`) to confirm the trigger — delta turning in the
  trade's direction, or absorption against the prior move.

---

## Confluence Scoring

### High confidence (3+ factors align)
- HTF bias + MTF structure + OB/FVG + correct premium/discount zone.
- POC / VAH / VAL coincides with the OB/FVG level.
- Session dynamics confirm (e.g. London swept the Asia range in the bias
  direction).
- Order-flow delta confirms (buying volume dominant for a long).

### Medium confidence (2 factors)
- HTF bias + OB/FVG at a key level.
- Structure alignment + session killzone timing.
- POC acting as support/resistance + delta confirmation.

### Low confidence (1 factor)
- A single OB or FVG with no structural confirmation.
- Trend on one timeframe contradicted by another.
- No session or order-flow confirmation.

`scan_confluence` gives a deterministic structural grade (0–N with a `min_score`
and a required aligned OB within 0.5% of price). Use it as the spine of the
score, then layer order flow and session context — which it does **not** include
— on top.

---

## Weighing Conflicting Signals

### Resolution rules (priority order)
1. **HTF > LTF.** Daily bullish but 15m bearish → bullish bias, with caution /
   wait for a pullback.
2. **Structure > indicators.** BOS/CHoCH outranks a volume or delta blip.
3. **Confluence > isolation.** Several aligned signals beat one strong one.
4. **Session context matters.** A setup inside a killzone > the same setup
   outside one.
5. **Order flow confirms or warns.** Delta/CVD diverging from price = absorption,
   potential reversal.

### Common contradictions
- **Bullish structure + bearish order flow** → absorption; smart money buying
  into selling. Often precedes a move *up*. Watch for a CHoCH up.
- **Bearish trend + price at discount** → possible counter-trend bounce; only
  trade it if a CHoCH confirms.
- **POC above price + bearish OB above** → stacked resistance; strong area to
  look for shorts.
- **EQH above + bullish trend** → expect a sweep of EQH *then* possible reversal;
  don't go long *targeting* EQH as if it's clean.

---

## Pre-Trade Checklist

```
1.  BIAS:         HTF direction? [Bullish/Bearish/Neutral]
2.  STRUCTURE:    Does MTF/LTF confirm? [Aligned/Conflicting]
3.  KEY LEVELS:   Nearest OB/FVG/level above & below? [list]
4.  ZONE:         Premium / Equilibrium / Discount? [+ implication]
5.  PROFILE:      Where is POC? Price inside/outside value area?
6.  FLOW:         Delta/CVD — buyers or sellers dominant? Divergence?
7.  SESSION:      Which session? Killzone active? Asia range swept?
8.  LIQUIDITY:    Targets — EQH/EQL, prior session/day H-L, weak levels.
9.  CONFLUENCE:   How many factors align? [High/Medium/Low] + scan score.
10. INVALIDATION: What breaks the thesis? [level + condition]
```

---

## Brief Output Format

```
BIAS: [Bullish/Bearish/Neutral] — Confidence: [High/Medium/Low]

STRUCTURE
- HTF (4h/1d): [trend, recent BOS/CHoCH]
- MTF (entry TF): [alignment, key structures]
- Current zone: [Premium/Equilibrium/Discount]

KEY LEVELS (nearest to current price)
- Above: [level — type — significance]
- Below: [level — type — significance]
- POC: [..] | VAH: [..] | VAL: [..]

ORDER FLOW
- Net delta: [buyers/sellers dominant]
- CVD trend: [rising/falling/diverging]
- Notable: [absorption/exhaustion/large trades]

SESSION CONTEXT
- Current: [session + phase]
- Asia range: [swept/intact]
- Killzone: [active/upcoming/none]

CONFLUENCES
- [aligned factors with levels] (+ scan_confluence score vs min_score)

TRADE IDEA (if High/Medium confidence)
- Direction: [Long/Short]
- Entry zone: [range — reason]
- Target: [level — reason]
- Invalidation: [level — what breaks it]

RISKS
- [what could go wrong]
- [contradicting signals]
- [news-blind: no macro feed — check the economic calendar before risking]
```
