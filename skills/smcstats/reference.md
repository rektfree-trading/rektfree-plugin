# SMC Hit-Rate Statistics — Reference Playbook

This skill grounds Smart Money Concepts (SMC) analysis in **what has actually
happened** for a specific crypto asset, rather than relying on generic SMC
theory. It measures how often each detected pattern — order block, fair value
gap, break of structure, change of character, equal high/low, liquidity sweep —
played out against the candles that followed.

Use these empirical rates to decide which SMC patterns to trust on this asset
right now, and to attach honest probabilities to a setup instead of asserting
"OBs always hold" or "FVGs always fill."

## How the numbers are produced

`compute_smc_stats` fetches ~2500 1H Binance candles (~3-4 months), then slides
the SMC engine across them in **200-candle windows with a step of 50**. For each
window it runs the full SMC analysis, then scores every detected structure
against the FUTURE candles using fixed look-forward windows and thresholds:

| Pattern | Look-forward | Success threshold |
|---|---|---|
| Order Block | 24 candles | retest into the zone, hold = close back on the right side |
| Fair Value Gap | 48 candles (skip first 3) | price enters the gap |
| BOS | 8 candles | price runs ≥ 0.3% in the break direction |
| CHoCH | 12 candles | price reverses ≥ 0.5% in the new direction |
| EQH/EQL | 6 candles | level swept, then reverses ≥ 0.3% |
| Liquidity Sweep | 12 candles | price moves ≥ 1% in the reversal direction |

Outcomes are de-duplicated across overlapping windows by candle index, so each
structure is counted once.

**Coverage caveat.** This is the *recent* ~3-4 months only. The hosted product
(app.rektfree.com) runs the identical evaluation over *full* candle history and
persists it, so its rates will differ. Quote the window
(`window.from` → `window.to`) and treat these as a recent-regime read.

## Tool payload

`compute_smc_stats` returns:

```
{
  "symbol", "window": { "candles", "timeframe", "from", "to" },
  "ob_test":    { "n", "retest_rate", "hold_rate", "hold_rate_when_retested",
                  "avg_retest_candles", "bullish", "bearish" },
  "fvg_test":   { "n", "fill_rate", "avg_fill_candles", "avg_fill_pct",
                  "bullish", "bearish" },
  "bos_test":   { "n", "continuation_rate", "avg_max_move_pct",
                  "bullish", "bearish" },
  "choch_test": { "n", "reversal_rate", "avg_max_move_pct",
                  "bullish", "bearish" },
  "eq_test":    { "n", "sweep_rate", "reversal_rate", "reversal_rate_when_swept",
                  "avg_reversal_pct", "eqh", "eql" },
  "sweep_test": { "n", "success_rate", "avg_max_move_pct", "wick", "retest" }
}
```

All rates are percentages (0–100). **`n` is the sample size for that block** —
the number of structures of that type detected and scored. Read every rate next
to its `n`.

## Sample size is not optional

A hit rate is only as good as the count behind it. Binomial noise on a small
sample is enormous — a 70% rate from n=4 could easily be a true 30%.

- **n ≥ 50** — solid; quote with confidence.
- **n 15–49** — directional; quote but hedge.
- **n < 15** — noise; describe the tendency, do not assert the percentage.
  `eq_test` is frequently in this range — equal highs/lows are comparatively
  rare. Expect small n there and discount accordingly.

## How to interpret each rate

### Order Blocks (`ob_test`)

- **retest_rate** — how often price returned to the OB zone at all. Low retest
  rate = price often runs away; the OB never gets a chance to act as support.
- **hold_rate** — how often the OB held (price respected it and bounced/rejected).
  This is the headline.
  - **> 65%** — OBs are reliable; use them confidently as entry zones.
  - **50–65%** — moderate; require extra confluence (FVG overlap, killzone).
  - **< 50%** — OBs get run; tighten stops or skip OB-only entries.
- **hold_rate_when_retested** — of the OBs that were retested, how many held.
  (By construction "hold" is only evaluated at the retest moment, so this is the
  cleaner reliability read once price actually comes back.)
- **avg_retest_candles** — typical hours until the retest; useful for patience /
  expiry on a limit order.
- **bullish / bearish** — the directional split of detected OBs.

### Fair Value Gaps (`fvg_test`)

- **fill_rate** — how often the gap got filled (price returned into it).
  - **> 70%** — FVGs act as magnets; good for limit entries on the return.
  - **< 50%** — gaps often stay open; don't wait for a fill that may not come.
- **avg_fill_pct** — average depth of penetration into the gap. High = full
  mitigation; low = price only nicks the edge.
- **avg_fill_candles** — typical hours to fill.

### Break of Structure (`bos_test`)

- **continuation_rate** — how often a BOS ran ≥ 0.3% in the break direction.
  The 0.3% bar over 8 candles is deliberately low, so this rate is typically
  **high** — read it as "did the break have *any* follow-through," not a profit
  target.
- **avg_max_move_pct** — the meatier number for sizing; the average best-case
  move after a break. High continuation + high avg move = trend-following works.

### Change of Character (`choch_test`)

- **reversal_rate** — how often a CHoCH produced a ≥ 0.5% reversal in the new
  direction. This is the reversal-edge gauge.
  - **High** — CHoCH is a reliable reversal signal; act on it.
  - **Low** — many CHoCH are fakeouts; require confirmation (OB hold, sweep).
- **avg_max_move_pct** — average reversal extent.

### Equal Highs / Lows (`eq_test`)

- **sweep_rate** — how often the equal level got swept (taken out).
- **reversal_rate** — how often it swept AND then reversed ≥ 0.3% — the classic
  liquidity-grab pattern.
- **reversal_rate_when_swept** — of swept EQ levels, how many reversed; the
  cleaner read once the sweep happens.
  - **High** — fade the sweep; look for entries after the grab.
  - **Low** — sweeps often lead to continuation, not reversal; don't fade blindly.
- Usually **small n** — present as a tendency.

### Liquidity Sweeps (`sweep_test`)

- **success_rate** — how often a detected sweep produced a ≥ 1% move in the
  reversal direction.
- **avg_max_move_pct** — average extent of the post-sweep move.
- **wick / retest** — split of sweep types detected.

## How to use in analysis

1. **Before recommending an OB entry** — check `hold_rate`. If low, add caveats
   or require confluence.
2. **When discussing FVG fills** — cite the actual `fill_rate`; don't claim
   "FVGs always fill."
3. **When calling trend direction** — cite `bos_test.continuation_rate` (and its
   avg move) to support a continuation bias.
4. **When weighing a reversal** — cite `choch_test.reversal_rate`; low rate means
   wait for confirmation.
5. **When giving confidence levels** — ground them in the specific number and
   its `n`. "OBs hold 73% of the time (n=88) on BTCUSDT over the last 3 months"
   beats "OBs are generally reliable."

Always cite the specific number, its sample size, and the coverage window.

## Analysis output format

```
SMC HIT RATES — <SYMBOL> (1H, <from> → <to>)

RELIABLE PATTERNS (high rate, healthy n):
- OB hold: X% (n=Y) — [reliable/moderate/weak]
- FVG fill: X% (n=Y), avg fill X% — [magnet / often stays open]
- BOS continuation: X% (n=Y), avg move X% — [trend-following works / choppy]
- CHoCH reversal: X% (n=Y) — [reliable signal / needs confirmation]

WEAK / NOISY PATTERNS:
- <pattern>: X% (n=Y) — [discount, or sample too thin]

BIAS SPLIT:
- bullish vs bearish counts where they skew

IMPLICATION FOR CURRENT SETUP:
- which SMC patterns to trust on this asset now, and which to discount
```
