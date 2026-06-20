# Initial Balance (Opening-Range) Statistics — Reference Playbook

This skill analyzes the **Initial Balance (IB)** — the first hour of the regular
trading session — and the empirical rates that govern how it behaves: IB size,
breakout rate (above / below / both / neither), which side breaks first, how far
price extends beyond the IB, and how often the IB holds. These statistics ground
analysis in what has actually happened for a specific crypto asset over the
sampled window, rather than generic theory.

## Concept

The **Initial Balance** is a Market-Profile idea: the price range established in
the first hour of the trading session sets the "balance" that the rest of the day
either breaks out of or rotates within. Traders watch it because:

- The IB high and IB low are natural breakout triggers and stop locations.
- Days that break the IB early and extend tend to **trend**; days that stay
  inside the IB tend to **rotate / mean-revert**.
- The **opening-range breakout (ORB)** strategy enters on a break of the IB edge
  in the break direction, using the opposite edge as the stop.

**RTH convention.** Crypto trades 24/7, so the platform uses a *synthetic NY*
session (volume concentrates around the US equities open). The IB window is
**13:30-14:30 UTC**, and post-IB runs to the RTH close at **20:00 UTC**. The
engine measures the IB-window high/low, then walks the post-IB candles to record
the first break, the breakout outcome, and the up/down extensions.

**Data source.** The IB window starts at 13:30 — a 5-minute candle boundary that
1H candles cannot resolve — so the tool fetches **5m candles** for IB precision,
falling back to 1H only when 5m is unavailable for a day. 5m history is heavy, so
the live sample is capped at ~60 days. Days resolved on the 1H fallback are
flagged via `window.candle_source_5m_days` and are lower-resolution.

## Tool payload

`compute_ib_stats` returns:

```
{
  "symbol": "BTCUSDT",
  "window": { "candles_5m", "candles_1h", "from", "to", "days", "ib_days",
              "ib_window_utc", "rth_convention", "candle_source_5m_days", "note" },
  "breakouts": { "n", "only_h_pct", "only_l_pct", "both_pct", "neither_pct",
                 "breakout_rate", "ib_hold_rate",
                 "first_break_high_pct", "first_break_low_pct",
                 "first_break_none_pct", "avg_first_break_time" },
  "extension": { "n", "ib_size", "ib_size_pct", "ib_up_extension",
                 "ib_down_extension", "max_extension", "size_to_extension_ratio" },
  "day_of_week": { "Monday": {...}, ... }
}
```

Each `extension.*` value is a distribution block:
`{ n, median, mean, min, max, p25, p75 }`.

### Sample window — read this first

`window.ib_days` is the **live sample length**, and `window.note` restates it.
The hosted product computes these same stats over its FULL candle history, so its
dashboard rates will differ from this tool's snapshot. **Always cite the sample
size** and treat thin buckets (a weekday with only a handful of days) with
caution. Discount days where the 1H fallback was used
(`candle_source_5m_days` << `ib_days`).

### Field reference

| Field | Meaning |
|---|---|
| `breakouts.only_h_pct` | % of days that broke **only** the IB high |
| `breakouts.only_l_pct` | % that broke **only** the IB low |
| `breakouts.both_pct` | % that broke both IB edges (two-sided / trend-then-reverse) |
| `breakouts.neither_pct` | % that stayed inside the IB all session (= `ib_hold_rate`) |
| `breakouts.breakout_rate` | % of days that broke at least one IB edge |
| `breakouts.ib_hold_rate` | % of days the IB held (no breakout) — rotation days |
| `breakouts.first_break_high_pct` / `_low_pct` | Which edge broke **first** |
| `breakouts.avg_first_break_time` | Average UTC time of the first IB break |
| `extension.ib_size` | IB range (high − low), quote units (USDT) |
| `extension.ib_size_pct` | IB range as **% of price** — comparable across regimes |
| `extension.ib_up_extension` | How far price ran **above** the IB high, post-IB |
| `extension.ib_down_extension` | How far price ran **below** the IB low, post-IB |
| `extension.max_extension` | The larger of up/down extension |
| `extension.size_to_extension_ratio` | IB size ÷ max extension; small = price runs far past the IB |
| `day_of_week.{d}` | Per-weekday `avg_ib_size_pct`, `neither_pct`, `both_pct`, `count` |

## How to interpret

**IB size** (`ib_size_pct`)
- A wide IB (high median %) implies a volatile open → wider stops/targets, and
  the IB edges are further apart so breakouts need a bigger move.
- A tight IB → coiled open; breakouts can be explosive but also more prone to
  fakeouts.

**Breakout rate vs IB-hold rate**
- High `breakout_rate` (> 75%) = the IB almost always breaks → ORB is viable;
  trade the break, stop at the opposite IB edge.
- High `ib_hold_rate` (> 30%) = frequent rotation/range days → ORB gets chopped;
  fade the IB extremes or require confluence.

**First-break side**
- A skew (e.g. `first_break_low_pct` ≫ high) shows where price tends to probe
  first. Combine with `both_pct`: a first low-break that frequently reverses into
  a both-day is a classic **bear trap → upside** pattern (and vice versa).

**Extensions**
- Compare `ib_up_extension` vs `ib_down_extension` medians for a directional
  lean (which way price runs further once the IB breaks).
- `size_to_extension_ratio`: **small (< 1)** = price runs well past the IB
  (trend days, ORB pays); **large (> 2)** = price barely clears the IB (chop,
  ORB unreliable).

**Day-of-week** — opening-range behavior often differs by weekday (e.g. a Monday
range-build vs a mid-week expansion). Use `count` to weight confidence.

## Analysis output format

```
INITIAL BALANCE EDGE

IB PROFILE:
- Median IB size: X% (p25–p75: Y%–Z%), window 13:30-14:30 UTC
- Breakout rate X% vs IB-hold rate Y% (n=N)

BREAKOUT DIRECTION:
- First break high X% / low Y%, avg break HH:MM UTC
- Outcome mix: only_h X% / only_l Y% / both Z% / neither W%

EXTENSION:
- Up median X / down median Y / max median Z
- size_to_extension_ratio median R → [runs / stalls past IB]

DAY-OF-WEEK EDGE:
- [Standout weekdays]

IMPLICATION FOR CURRENT SETUP:
- [ORB-trade the break vs fade IB extremes, given hold rate + extensions]

SAMPLE: window.ib_days days, n=N (5m-resolved D of them) — recent snapshot
```

Always cite the specific numbers. "BTCUSDT breaks its IB 82% of days and the low
breaks first 56% of the time (n=58)" is far more valuable than "the opening range
usually breaks."
