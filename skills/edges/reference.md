# Edge Discovery — Reference Playbook

This skill mines a crypto symbol's recent history for **statistically
significant edges and anti-patterns**: combinations of conditions under which a
trading pattern wins meaningfully more (or less) than its own baseline. It
grounds "what actually works" in the sampled data for a specific asset, rather
than generic theory — but because it grid-searches many combinations, its output
is a set of **hypotheses to validate**, not laws.

## Tool payload

`discover_edges` returns:

```
{
  "symbol": "BTCUSDT",
  "window": { "candles", "from", "to", "days" },
  "baselines": { "ob_test": 33.3, "fvg_test": 56.7, ... },
  "edges": [ {event_type, filters, n, win_rate, baseline, edge_score}, ... ],
  "anti_patterns": [ ... same shape, most-negative first ... ],
  "notes": [ caveats ]
}
```

### Sample window — read this first

`window.days` is the **live sample length** (default ~180 days). The hosted
product mines its FULL persisted event history; this tool only mines what it
just fetched. So:
- Cite the sample size and treat the edges as a **recent snapshot**.
- The dashboard's edges will differ.

## The event set being mined

The tool labels every detected structure/event with a boolean **win** and a set
of **dimensions**, then mines them. The win criterion per event type:

| event_type        | "win" means…                                         |
|-------------------|------------------------------------------------------|
| `ob_test`         | the order block **held** on retest                   |
| `fvg_test`        | the fair-value gap got **filled**                    |
| `bos_test`        | the break-of-structure **continued** (≥0.3%)         |
| `choch_test`      | the change-of-character **reversed** (≥0.5%)         |
| `eq_test`         | the equal high/low swept then **reversed** (≥0.3%)   |
| `sweep_test`      | the liquidity sweep **succeeded** (≥1% move)         |
| `asia_sweep`      | London's sweep of Asia **reversed** (the fade hit)   |
| `london_sweep`    | NY's sweep of London **reversed** (the fade hit)     |
| `ny_continuation` | NY **continued** London's direction                  |
| `power_of_3`      | the AMD **distribution** ran ≥1.5× the Asia range    |

Dimensions the grid searches over:
- **session** — asia / london / new_york (where the event formed/fired).
- **day_of_week** — Monday…Sunday (session events only; SMC outcomes are not
  weekday-tagged, so they appear only under session/direction/side cells).
- **direction** — the event's bias (bullish/bearish) where it has one.
- **side** — the swept side (high/low/both) or structure type (EQH/EQL,
  WICK/RETEST) where applicable.

There is **no macro dimension** in this slice (the plugin has no macro feed).

## The ranking math

For each event type:

1. **baseline** = win rate over *all* its instances.
2. For each filter **cell** (a single dimension=value, or a pair of them) with
   `n ≥ min_samples`:
   - `win_rate` = cell win rate.
   - `edge_score = (win_rate − baseline) × sqrt(n)`.

Only **single** and **pairwise** filters are tested (no deeper combos) — this
bounds both runtime and the multiple-comparisons explosion.

`edges` = positive edge_score, strongest first. `anti_patterns` = negative,
most-negative first. Each list is capped at `top` (default 15).

### Why sqrt(n) and not raw lift

The lift `(win_rate − baseline)` alone over-rewards tiny samples: a single lucky
streak gives a huge lift on `n=4`. Weighting by `sqrt(n)` is a sample-size
confidence proxy (it grows like the inverse of the standard error of a
proportion), so a modest, durable lift over a large sample can outrank a wild
lift over a handful of events. This is the same formula the hosted
`edge_discovery` service ranks by.

## How to read an edge

- **Quote win_rate vs baseline**, always. `76% vs 49% baseline (n=46)` is the
  unit of a claim — the bare 76% is meaningless without the baseline.
- **Higher edge_score = stronger**, because it already blends lift and sample.
  Don't manually re-rank by win_rate.
- **A pairwise cell** is more specific (and more overfit-prone) than a single
  filter. Prefer the single-filter version when scores are close.
- **Anti-patterns are edges too** — knowing a setup degrades under a condition is
  as tradeable as a positive edge ("skip FVG longs in NY when bearish").

## Overfitting / multiple-comparisons caveat

A grid-search over many cells will, by chance, surface some cells that look like
edges but aren't. `min_samples` (default 10) and the sqrt(n) weighting reduce —
but do not eliminate — this. Treat every mined edge as a **forward hypothesis**:
worth a watchlist and a paper-trade, not a position sizing rule on day one. The
smaller the `n`, the more skeptical you should be, even when the edge_score is
large.

## Interpretation guardrails

- **Never present a mined edge as a guarantee or a "rule".** Say "worth testing".
- **Always cite `n`** next to every edge you surface.
- **State the sample window** every time (`window.days`).
- **Lead with the highest edge_score**, but sanity-check its `n` before you make
  it your headline.
- **Cross-reference** with the `sessions` and `smcstats` skills when a user wants
  the underlying base rates behind an edge.
