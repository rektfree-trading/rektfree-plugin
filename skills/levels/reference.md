# Key Levels — Reference Playbook

This skill identifies and analyzes significant price levels derived from
time-based market structure: daily, weekly, and monthly highs/lows, session
highs/lows, and period opens. These levels act as support, resistance, and
liquidity targets because institutional algorithms and large players anchor
orders around them. Knowing which levels matter most and how they interact is
essential for entries, stops, and targets.

## Tool payload

`get_levels` returns `{ "symbol", "last_price", "levels": [...] }`. Each entry in
`levels` is `{ "label", "price", "time" }` where `time` is a unix-second
timestamp (0 for opens).

Label convention:

| Label | Meaning |
|---|---|
| `D High` / `D Low` | Current day high / low |
| `W High` / `W Low` | Current week high / low |
| `M High` / `M Low` | Current month high / low |
| `pD High` / `pD Low` | Previous day high / low (PDH / PDL) |
| `pW High` / `pW Low` | Previous week high / low (PWH / PWL) |
| `pM High` / `pM Low` | Previous month high / low (PMH / PML) |
| `D Open` | Today's open |
| `Mon Open` | This week's open (Monday 00:00 UTC) |
| `Asia/London/New York High/Low` | Today's session extremes |
| `pAsia/pLondon/pNew York High/Low` | Prior day's session extremes |

All times are UTC. Sessions: **Asia 00:00–08:00**, **London 08:00–13:00**,
**New York 13:00–21:00**. The tool fetches ~10 days of 15m candles, so monthly
levels reflect the month so far (and `pM` the full prior month only if it falls
within the window — for early-month queries the prior month may be partial).

---

## Concepts & Definitions

### 1. Monthly Highs and Lows (PMH / PML)
The extremes of an entire month of price discovery — the most significant
time-based levels.
- Major liquidity pools; stop-loss and breakout orders cluster here.
- A sweep of PMH then rejection = strong bearish signal; sweep of PML then
  rejection = strong bullish signal.
- A clean break-and-hold above PMH = bullish continuation; below PML = bearish.
- Use as primary targets for swing trades. Never hide stops just beyond monthly
  levels — they get hunted. Monthly levels override all lower periods.

### 2. Weekly Highs and Lows (PWH / PWL)
Second most significant; primary swing-trade references.
- Early week (Mon–Tue), price often sweeps PWH or PWL before setting direction.
- A midweek sweep of PWH/PWL often leads to a reversal for the rest of the week.
- If both are untouched by Wednesday, the first one swept usually defines bias.
- Enter after a PWH/PWL sweep + lower-timeframe CHoCH.

### 3. Daily Highs and Lows (PDH / PDL)
The most commonly targeted intraday liquidity.
- Sweep PDH then reverse = short setup; sweep PDL then reverse = long setup.
- Open between PDH/PDL → expect one swept before direction sets. Open above PDH
  = bullish bias; below PDL = bearish.
- A day that breaks neither = inside/consolidation day → expect expansion next.

### 4. Session Highs and Lows
- **Asia (00:00–08:00):** lowest volatility; sets the initial daily range.
  London almost always sweeps Asia high or low. The Asia-sweep direction often
  signals London's intent (sweep Asia high → London goes short).
- **London (08:00–13:00):** highest volatility; often sets the day's direction.
  Sweep Asia high + reverse → bearish day; sweep Asia low + reverse → bullish.
- **New York (13:00–21:00):** continues or reverses London; targets London H/L.
  Reversals often hit at the NY open killzone (13:00–14:00 UTC).
- Prior-session H/L are immediate S/R. Place stops beyond the opposite session
  extreme (long after Asia-low sweep → stop below Asia low).

### 5. Opens (Daily / Weekly / Monthly)
Equilibrium/pivot levels — above the open is bullish for that period, below is
bearish.
- Weekly open (`Mon Open`) is the key swing bias level: price above → weekly
  candle green; below → red. Monthly open works the same for monthly bias.
- Use opens as **bias filters** (longs only above the relevant open, shorts
  below), not as standalone entries. Daily-open retest during London is a common
  entry.

---

## Significance Hierarchy

1. **Monthly H/L** — strongest, most liquidity.
2. **Weekly H/L** — primary swing references.
3. **Daily H/L** — key intraday, most traded.
4. **Session H/L** — scalp/day-trade references.
5. **Opens (M > W > D)** — bias filters only.

When levels cluster in a tight band (confluence), the zone is much stronger —
e.g. PDH aligning with Asia High and a weekly level = very high-probability
reaction zone.

---

## Practical Rules

1. **Levels are zones, not ticks** — expect reactions within ~0.1–0.3%.
2. **First touch is strongest** — untested levels react hardest; later touches weaken.
3. **Sweeps are signals** — wick beyond + close back inside = liquidity sweep = reversal.
4. **Breaks need follow-through** — a close beyond with rising momentum = real breakout.
5. **Stacked levels amplify** — session H/L aligning with daily/weekly H/L is far more significant.
6. **Reclaimed levels flip** — broken resistance becomes support and vice versa.

### Interaction patterns
- **Magnet effect:** price is drawn to nearby unswept levels (esp. PDH/PDL, session H/L).
- **Rejection:** touch → wick through → close back inside = level held.
- **Breakout:** close beyond with momentum = level broken.
- **Sweep and reverse:** wick through to grab liquidity, then aggressively reverse — the most tradeable pattern.

---

## Output Format

```
KEY LEVELS MAP
- Monthly: PMH [price], PML [price]
- Weekly: PWH [price], PWL [price], Mon Open [price]
- Daily: PDH [price], PDL [price], D Open [price]
- Sessions:
  - Asia: High [price], Low [price]
  - London: High [price], Low [price]
  - NY: High [price], Low [price]

BIAS FROM LEVELS
- Weekly bias: [Above/Below Mon Open] → [Bullish/Bearish]
- Daily bias: [Above/Below D Open] → [Bullish/Bearish]

LEVEL INTERACTIONS
- Nearest resistance: [levels above last_price, by proximity]
- Nearest support: [levels below last_price, by proximity]
- Confluence zones: [where multiple levels stack]
- Untested levels: [levels price hasn't reached — potential targets]

LIQUIDITY TARGETS
- Above price: [resting buy stops]
- Below price: [resting sell stops]
- Most likely next target: [level] because [reasoning]

SESSION CONTEXT
- Current session: [Asia/London/NY based on last candle time]
- Prior session H/L and whether they've been swept
- Expected session behavior
```
