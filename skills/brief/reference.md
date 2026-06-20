# Pre-Session Brief — Reference Playbook

Turn the gathered read into a forward-looking plan for the session **ahead**.
This is the cross-referencing-plus-forecast layer: it sits on top of the
single-factor skills (smc, levels, tpo, sessions, derivatives) and the synthesis
skill, and adds the trading-day clock so the plan is timed, not just directional.

Audience: experienced traders who know SMC, Auction Market Theory, and ICT
session structure. Be precise, use proper terminology, skip basic definitions,
and lead with actionable intelligence.

---

## The trading day (UTC) — what `get_session_clock` returns

| Session | Window (UTC) | Character |
|---|---|---|
| Asia | 00:00–08:00 | Lowest volatility. Builds the day's initial range (accumulation). |
| London | 08:00–13:00 | Highest volatility / institutional volume. Sweeps Asia, then trends. |
| New York | 13:00–21:00 | Second highest. Continues or reverses London. |
| Post-NY | 21:00–24:00 | Low-volume lull. No new entries; rolls into next Asia. |

**Killzones** (vendored from the backend scanner — the entry windows):
- **London Open KZ** 07:00–09:00 UTC — the #1 ICT entry window.
- **NY Open KZ** 12:00–14:00 UTC — the second-best; overlaps London 12:00–13:00.
- Silver-bullet sub-windows (highest precision): London 07:00–08:00,
  NY AM 14:00–15:00, NY PM 18:00–19:00.

The same setup has very different odds inside vs. outside a killzone. Tie every
if-then trigger in the plan to the active or next killzone the clock reports.

---

## Session-by-session playbook (what to plan for)

### Heading into ASIA (or post-NY)
- Note where the prior NY session closed relative to the day's range.
- Expect range formation / accumulation — do **not** plan directional entries.
- The job: **define the Asia range bounds (H/L)** that London will act on, and
  set up tomorrow. This is preparation, not execution.

### Heading into LONDON
- Note the Asia range (high, low, width vs. ADR).
- Primary question: **which side of the Asia range gets swept first?** Cite the
  actual sweep rate for this symbol ("London sweeps Asia high X% of days, n=…").
- If Asia was **tight** (<50% of ADR): expect aggressive London expansion.
- If Asia was **wide**: expect London to test one extreme, possibly range.
- The Asia sweep is the **Judas Swing** — plan to fade it on a CHoCH + OB/FVG in
  the opposite direction, targeting the other side of the range then PDH/PDL.

### Heading into NEW YORK
- Note London's direction and range.
- Primary question: **continuation or reversal of London?** Cite the NY
  continuation rate. <50% continuation = reversal-prone — watch the NY Open KZ
  (12:00–14:00) for London's move to fail.
- If London **trended** strongly: expect an NY pullback/retest then continuation.
- If London **ranged**: NY likely sets the real direction.

---

## Power of 3 (AMD) — the day's skeleton

The Accumulation → Manipulation → Distribution model maps onto the day:

- **Accumulation (Asia, ~00:00–05:00 UTC):** smart money builds positions in a
  tight range. Tighter range = more compressed energy = larger expected move.
  Quality: range <30% of ADR is clean; >50% is messy. The range H/L become the
  day's reference liquidity.
- **Manipulation / Judas Swing (London Open, ~07:00–10:00 UTC):** the fake move
  beyond one side of the Asia range to trap retail and harvest stops.
  Up-sweep → traps longs → expect bearish distribution. Down-sweep → traps
  shorts → expect bullish distribution.
- **Distribution (NY, ~13:00–17:00 UTC):** the real move, opposite the
  manipulation side, forming the body of the daily candle (50–70% of day range).
  Targets: opposite side of the accumulation range, then PDH/PDL (DOL).

Plan use: pre-session, identify the likely DOL (draw on liquidity = PDH or PDL by
daily bias), then wait for the Judas Swing in the killzone to confirm the entry.

### Session bias from the sweep (plan the branch)
- London sweeps Asia **high** only → bearish (sell-side liquidity grab).
- London sweeps Asia **low** only → bullish (buy-side liquidity grab).
- Sweeps **both**, closes above Asia H → bullish; closes below Asia L → bearish;
  closes inside → neutral, stay flat.
- No sweep, closes above Asia midpoint → bullish; below → bearish.
- NY: sweeps London high → bearish reversal; sweeps London low → bullish
  reversal; London bullish & no sweep → continuation bullish (and vice versa).

When **daily bias and session bias align**, that's the highest-probability
branch; when they conflict, reduce size or wait.

---

## Reading the session stats (`compute_session_stats`)

- **Sweep rate ≠ edge by itself.** A 70% sweep rate means *expect the sweep*; the
  tradeable edge is the **reversal_rate** after it (fade) vs. continuation.
- **High vs. low sweep skew reveals bias.** If London sweeps the Asia *high* far
  more than the low, the post-sweep bias is bearish (and vice versa).
- **NY continuation <50% = reversal-prone.** Plan for London's move to fail in
  the NY Open KZ.
- **Power of 3 needs a tight Asia.** Low occurrence_rate = the asset rarely
  accumulates tight enough — don't force the AMD framing.
- **Range% over raw range** when comparing sessions/assets (raw range scales with
  price).
- **Anchor to sample size.** The tool samples the recent window (`window.days`),
  not full history. Cite session counts; treat thin buckets (<8) as weak.

---

## Building the if-then plan

A pre-session plan is a small set of **conditional** branches, each tied to a
level, a time/killzone, and an invalidation:

```
IF  [Asia high swept in the London Open KZ (07:00–09:00)] AND CHoCH down on 15m
THEN short the first bearish OB/FVG after the CHoCH
TARGET  Asia low → PDL (the DOL)
INVALIDATION  15m close back above the swept Asia high
CONFLUENCE  HTF bearish bias + premium zone + 68% Asia-high-sweep stat
```

Rules for the plan:
- **Every branch needs an invalidation level** — no "what breaks it", no trade.
- **Lead with the highest-confluence branch**; cap at 1–2 actionable ideas.
- **Only present Medium+ confidence.** If nothing aligns, the brief states "no
  clean setup into this session — here's the watch-list and the triggers."
- **Tie triggers to the clock.** "London Open KZ in 90m" / "NY Open KZ active,
  28m left" from `get_session_clock` is the timing rail.
- **Liquidity = targets, not safe stops.** EQH/EQL and prior session/day H-L are
  where price is drawn; don't hide stops just beyond them.

---

## Pre-session checklist

```
0.  CLOCK:        Current session/phase? Next session + when? Killzone active/next?
1.  BIAS:         HTF direction? [Bullish/Bearish/Neutral] + the BOS/CHoCH reason
2.  ZONE:         Premium / Equilibrium / Discount? Does it agree with bias?
3.  LEVELS:       D/W/M near price; prior-session & prior-day H/L (the liquidity)
4.  PROFILE:      POC / VAH / VAL — do they stack with an OB/FVG?
5.  STATS:        Upcoming-session sweep/continuation rate + sample size
6.  POSITIONING:  Funding/OI/long-short — backs the thesis or warns (squeeze)?
7.  DOL:          Draw on liquidity for the day = PDH or PDL?
8.  CONFLUENCE:   How many factors align? scan_confluence score vs min_score
9.  PLAN:         If-then branches keyed to the killzone, each with invalidation
10. RISK:         Macro window (check the calendar — no feed here), vol sizing
```

---

## Guardrails

- **Never fabricate levels** — only use prices from the tool payloads.
- **If data is unavailable for a section, say so** and continue; degrade
  gracefully, never abort the brief.
- **Prioritize recency**: last 24h > last week > older.
- **Conflicting timeframes** → note the conflict, default to the higher timeframe.
- **No macro/news feed** in this plugin — high-impact events can override the
  technical plan; always tell the user to check the economic calendar for the
  session window.
