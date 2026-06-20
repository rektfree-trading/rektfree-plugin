# ICT Session Concepts — Reference Playbook

This skill analyzes intraday session dynamics using interconnected ICT (Inner
Circle Trader) concepts: Draw on Liquidity (DOL), Power of 3 (AMD), the Judas
Swing, and Session Bias — plus a 10-factor trade-qualification checklist. These
explain HOW smart money operates within each trading day using session structure.

## Tool payload

`get_ict_concepts` returns per-day history lists plus latest-day summaries:

```
{
  "symbol", "timeframe", "candle_count",
  "dol":          [ {day_start, bias, dol_price, dol_label, opposite_price, reached}, ... ],
  "amd":          [ {day_start, phase, start_time, end_time, high, low, direction, range_pct, quality}, ... ],
  "judas_swings": [ {day_start, sweep_time, sweep_price, direction, asia_high, asia_low, reversal_confirmed}, ... ],
  "session_bias": [ {day_start, session, bias, reason, target_high, target_low, hit_target}, ... ],
  "current_dol":          {bias, dol_price, dol_label, opposite_price, reached} | null,
  "current_session_bias": {session, bias, reason} | null
}
```

All times are unix seconds, UTC. Session windows (UTC): **Accumulation** 00:00–
05:00, **Manipulation** (London Open) 07:00–10:00, **Distribution** (NY) 13:00–
17:00; full **London** 07:00–13:00, full **NY** 13:00–21:00.

---

## 1. Power of 3 (AMD) — Accumulation, Manipulation, Distribution

The three phases of institutional activity within each day. PO3 is **fractal** —
the same A→M→D appears on every timeframe.

**Accumulation (Asia, 00:00–05:00 UTC).** Smart money builds positions in the
lowest-volatility window. Tight range; its high/low become the day's reference.
Tighter = more compressed energy. Quality: range < 30% of ADR = `clean`, > 50% =
`messy`. Do NOT trade here — note the range.

**Manipulation / Judas Swing (London Open, 07:00–10:00 UTC).** The fake move.
Price is pushed beyond one side of the accumulation range to trip stops and
induce wrong-way breakout entries. `direction`: `up_sweep` (high taken → trapped
longs → expect down) or `down_sweep` (low taken → trapped shorts → expect up).
Quality `clean` when it covers 20–40% of day range with a clear direction. This
is where the entry signal forms.

**Distribution (NY, 13:00–17:00 UTC).** The real move — smart money offloads into
retail chasing. Up-sweep manipulation → bearish distribution; down-sweep →
bullish. Quality `clean` when it covers 50–70% of day range (it forms the body of
the daily candle). Targets: opposite side of accumulation, then the DOL (PDH/PDL).

A **clean** AMD day: narrow accumulation, decisive one-side sweep, strong
opposite-direction distribution. Both sides swept during manipulation = `messy`,
lower confidence.

---

## 2. Judas Swing

The specific manipulation-phase move against the true bias — looks bullish but is
bearish (or vice versa).

- **Up (fake bullish):** breaks above Asia high during London Open, retail buys
  the "breakout", smart money sells, price reverses below Asia high. True
  direction bearish.
- **Down (fake bearish):** breaks below Asia low, retail sells the "breakdown",
  smart money buys, price reverses above Asia low. True direction bullish.
- **`reversal_confirmed`:** London closed back on the opposite side of the sweep
  (sweep up + close below Asia high = confirmed bearish; sweep down + close above
  Asia low = confirmed bullish). Treat confirmed swings as the tradeable signal.

Trade it: wait for the sweep → CHoCH on 5m/15m → enter at first OB/FVG → stop
beyond the Judas extreme → target opposite side of Asia range, then DOL.

---

## 3. Session Bias

**London (set ~08:00 UTC)** from how London sweeps the Asia range:

| Scenario | Bias | Reason |
|---|---|---|
| Sweeps Asia high only | Bearish | Liquidity grab above — sell-side target |
| Sweeps Asia low only | Bullish | Liquidity grab below — buy-side target |
| Both, closes above Asia H | Bullish | Aggressive, closed strong |
| Both, closes below Asia L | Bearish | Aggressive, closed weak |
| Both, closes inside | Neutral | Mixed — stay flat |
| No sweep, closes above mid | Bullish | Quiet strength above equilibrium |
| No sweep, closes below mid | Bearish | Quiet weakness below equilibrium |

**New York (set ~13:00 UTC)** from London's result and NY vs London range:

| Scenario | Bias | Reason |
|---|---|---|
| NY sweeps London high only | Bearish | Reversal expected after high sweep |
| NY sweeps London low only | Bullish | Reversal expected after low sweep |
| London bullish, no sweep | Bullish | Continuation expected |
| London bearish, no sweep | Bearish | Continuation expected |

Session bias is **micro** (per session); daily bias is **macro** (once per day).
Aligned = highest probability; conflicting = wait or reduce size.

---

## 4. Draw on Liquidity (DOL)

The target the daily bias points to: bullish → PDH (`dol_label` "PDH"), bearish →
PDL ("PDL"). `opposite_price` is the invalidation side; `reached` = price hit the
DOL during the day. The DOL framework: identify it → wait for manipulation away
from it → enter at OB/FVG after CHoCH → target the DOL → invalidate on a close
beyond the opposite level.

**DOL + session confluence:** DOL = PDH and London sweeps Asia low (Judas down)
→ high-probability long targeting PDH. DOL = PDL and London sweeps Asia high
(Judas up) → high-probability short targeting PDL.

---

## How the four concepts work together

```
1. PRE-SESSION: Daily bias → know the DOL (PDH or PDL)
2. ASIA (00:00–08:00): note the accumulation range
3. LONDON OPEN (07:00–10:00): watch for the Judas Swing
   - Sweep against bias (e.g. Judas down + bullish daily bias) = HIGH CONFIDENCE
4. POST-MANIPULATION: enter on CHoCH + OB/FVG in the bias direction
5. DISTRIBUTION (NY): hold for the DOL target
6. NY SESSION: check session bias for continuation or take profit
```

Confluence scoring: daily + session bias aligned +2, clean Judas +2, manipulation
direction matches bias +2, SMC BOS/CHoCH confirms +1, OB/FVG entry available +1.
Score ≥ 6 = high-confidence setup.

---

## The 10-Factor ICT Trade Checklist

Each factor is a yes/no check; 5+ of 10 = high-probability. Use it to evaluate a
setup the user asks about.

1. **HTF Directional Bias** — clear bullish/bearish on Daily and/or 4H. Never
   trade against it. Foundation.
2. **Draw on Liquidity** — a clear, *unswept* liquidity target in the trade
   direction (EQH/EQL, PDH/PDL, session H/L, weekly/monthly). No draw = no target.
3. **Liquidity Sweep Occurred** — price just swept the OPPOSITE side (longs:
   swept sell-side lows; shorts: swept buy-side highs), recent. The trap.
4. **Market Structure Shift (MSS / CHoCH)** — after the sweep, a body-close break
   of structure confirms the reversal. Sweep + CHoCH = strongest signal.
5. **Entry Zone (OB / FVG / Breaker)** — valid OB or FVG in the retracement;
   bonus if at the 0.618–0.786 OTE zone. The precision entry.
6. **Killzone / Session Timing** — forming in an institutional session. London
   Open 07:00–09:00 UTC, NY Open 12:00–14:00; Silver Bullet 07–08/14–15/18–19.
7. **Premium/Discount Zone** — longs in discount (< 50% of range), shorts in
   premium; best at 0.618–0.786.
8. **Macro Event Risk** — no high-impact event within 30–60 min. Wait 5–15 min
   after a release.
9. **Order Flow Confirmation (crypto)** — delta/volume supports the direction;
   divergence warns of reversal.
10. **Multi-Timeframe Alignment** — D1/4H/1H agree (3/3 strong, 2/3 moderate,
    1/3 skip).

| Score | Confidence | Action |
|---|---|---|
| 8–10 | Very High | Full size, tight stop |
| 6–7 | High | Standard size |
| 5 | Medium | Reduced size, wider stop |
| < 5 | Low | Do not trade |

**Ideal sequence:** HTF bias → unswept draw → sweep opposite-side liquidity →
CHoCH/MSS → retrace to OB in OTE zone → enter in killzone → target the draw →
stop beyond the OB. Sweep → CHoCH → OB entry → target liquidity is the highest-
probability ICT model.

---

## Output Format

```
SESSION SETUP (latest day)
- Draw on liquidity: [dol_label] @ [dol_price] — reached? [reached]; invalidation [opposite_price]
- Power of 3: Accumulation [quality], Manipulation [direction, quality], Distribution [direction, quality]
- Judas swing: [up/down] sweep @ [price], reversal_confirmed [yes/no]  (or "none")
- Session bias: London [bias] ([reason]); NY [bias] ([reason])

THE READ
- True direction (opposite of the Judas sweep / the distribution direction)
- Plan: sweep → CHoCH/MSS → OB/FVG entry → DOL target
- Confluence with daily bias and the checklist score
- Invalidation: [close beyond opposite level / Judas extreme]
```
