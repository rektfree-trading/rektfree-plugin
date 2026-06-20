# Volatility & Range — Reference Playbook

This skill provides context on current market volatility relative to recent
history. It is essential for setting realistic targets, appropriate stop
distances, sizing positions, and gauging whether the market is in a compressed
(pre-breakout) or expanded (trending) state. The numbers are descriptive — they
tell you *how big* a move is and *how much room is left*, not *which direction*.
Pair with the levels and SMC skills for direction.

## Tool payload

`get_volatility` returns:

```
{
  "symbol", "last_price", "timeframe",
  "atr": { "value", "pct", "period", "method" },
  "adr": { "value", "pct", "days", "today_range", "pct_of_adr_used" },
  "realized_vol": { "annualized_pct", "window", "annualization" },
  "bollinger": { "width", "squeeze", "percentile", "period" },
  "state": { "label", "reason" }
}
```

All prices are in the quote currency (e.g. USDT). `*_pct` fields are percent of
`last_price`. `state.label` is `expanding` / `contracting` / `neutral`.

---

## Metrics & how they're computed

### ATR — Average True Range
Average candle size over `period` candles of the chosen timeframe.

- **True Range** = `max(high − low, |high − prev_close|, |low − prev_close|)`.
- **ATR** = simple mean of the last `period` true ranges. The tool reports
  `method: "simple"` — a plain SMA of true ranges, not Wilder's smoothing. Over a
  short recent window the two track closely; simple is the more transparent.
- **ATR%** = ATR / last price × 100. On BTC 1H this is typically ~0.3–1%.
- **Use:** stop distance (0.5–1.5× ATR) and target distance (2–3× ATR).

### ADR — Average Daily Range
Mean daily (high − low) over `days` *completed* daily candles (the current,
partial day is treated as "today", not averaged in).

- **ADR%** = ADR / price × 100. On BTC this is typically ~2–5%.
- **today_range** = today's high − low so far.
- **pct_of_adr_used** = today_range ÷ ADR × 100 — *how much of the typical daily
  move has already happened.* The key "is there room left?" signal:
  - `< 50%` → market is compressed for the day; potential for a larger move.
  - `~100%+` → typical daily range largely spent; late entries carry exhaustion
    and mean-reversion risk.
  - `> 150%` → an outsized day; expect reversion / consolidation.

### Realized volatility
Sample standard deviation of per-period **log returns** `ln(c[i]/c[i-1])` over
the last `window` periods (default 30), **annualized** by multiplying by
`sqrt(periods_per_year)` for the timeframe (crypto trades 24/7/365, so e.g. 1H
uses `sqrt(8760)`). Reported as `annualized_pct`. A regime gauge — crypto often
sits ~40–90% annualized; compare to the asset's own norm. A 30-period window can
read low during a quiet/compressed stretch (consistent with a squeeze).

### Bollinger Band width (BBW) + squeeze
On a 20-period band (mid = SMA, bands = mid ± 2·stdev):

- **width** = (upper − lower) / mid = 4·stdev / mid. Always positive.
- **percentile** = where the current width sits within the last ~100 widths
  (0 = tightest in the window, 1 = widest).
- **squeeze** = `true` when the percentile is in the bottom ~25% — i.e. bands are
  compressed relative to their own recent range. **Squeeze → compression →
  expansion likely** (a breakout often follows), but direction is unknown.

### State — expansion vs contraction
Compares short ATR (`period`) to a longer ATR (50) average, combined with the
squeeze flag:

- **expanding** — ATR ≥ ~1.15× its longer average: ranges growing / trending.
- **contracting** — a squeeze, or ATR ≤ ~0.85× its longer average: ranges
  shrinking / coiling / compression.
- **neutral** — ATR near its longer average with no squeeze: normal volatility.

`state.reason` states the ATR ratio and the squeeze read in one line.

---

## How to interpret

### Stop placement
- Minimum stop: 0.5× current ATR (tighter = stopped out on noise).
- Standard stop: 1× ATR (room for normal fluctuation).
- Wide stop: 1.5× ATR (swing trades or volatile conditions).
- If the user's stop is < 0.5× ATR, warn that it's likely to get hit.

### Target setting
- Minimum target: 1.5× the stop distance (acceptable R:R).
- ATR-based target: 2–3× ATR from entry is a realistic intraday target.
- If a target is > 3× current ATR for the timeframe, warn it may be unrealistic.

### Entry timing & sizing
- Compressed / squeeze + a killzone = strong entry timing (breakout imminent).
- Expanded + late session / high % of ADR used = poor entry timing (move may be
  exhausted).
- Normal volatility + trend alignment = standard conditions, trade normally.
- Volatility scales **size, not direction**: wider ATR / higher realized vol →
  smaller position for the same dollar risk; compression → room to size up.

### Confidence
- Compression lowers directional confidence (breaks either way) until structure
  confirms — use it to *anticipate*, not to pick a side.
- Extreme expansion (ATR ≫ average, or a single > ~2× ATR move) often precedes
  mean reversion — don't chase the last leg.

---

## How to use in analysis

1. Always contextualize targets and stops relative to ATR.
2. Flag a squeeze / compression as a potential setup catalyst (expect a move).
3. Warn when the daily range is already exhausted (`pct_of_adr_used` ≳ 100%).
4. Use volatility to size positions and to adjust confidence.
5. Compare current volatility to the asset's own typical range, not other
   markets.

---

## Output format

```
VOLATILITY STATE
- State: [Expanding / Contracting / Neutral] — [reason]
- ATR-[period] ([timeframe]): [value] ([pct]%)
- ADR-[days]: [value] ([pct]%) — today [today_range], [pct_of_adr_used]% used
- Realized vol (annualized): [pct]%
- Bollinger width: [value] — [Squeeze / Normal] (percentile [x])

IMPLICATIONS
- Suggested stop: ~1× ATR = [value]   (min 0.5× / wide 1.5×)
- Realistic target: 2–3× ATR = [range]
- Room left today: [pct_of_adr_used]% of ADR used → [room / exhausted]
- Position sizing: [smaller in expansion / room in contraction]

READ
- [One clear, decision-oriented call: squeeze→breakout watch, expansion→pullback
   entries in trend, range exhausted→wait or fade.]
```
