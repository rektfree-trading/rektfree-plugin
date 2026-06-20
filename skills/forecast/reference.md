# Session Forecast — Reference

Adapted from the backend `docs/skills/forecast.md`. The hosted product forecasts
by matching the *upcoming* session against historically **similar** sessions (a
condition vector of day-of-week, HTF bias, range state, ATR state, macro, prior
outcome) and computing conditional probabilities from the matches. The plugin's
`get_session_forecast` keeps the **pure frequency math** of that approach but
replaces the DB-coupled condition-matching with straight aggregation over a
**recent live sample**. So read it as base rates for the next session — not a
condition-matched, macro-aware prediction.

## Purpose

A forward-looking, probabilistic read of what the **upcoming** trading session
will most likely do — not "what happened" (that's the `sessions` skill) but
"what's most likely next," expressed as frequencies with sample sizes.

## Data source

- Deep 1H Binance candles (keyless), bucketed into Asia/London/New York sessions
  per UTC day, run through the same detectors the hosted product uses.
- The forecast session is chosen from the **UTC clock** (the session that is
  next). Frequencies are computed over that session's recent history only.

---

## How to interpret

### Expected range

`expected_range` is in **range%** ((high − low) / low × 100), which is
comparable across price regimes. Read it as the envelope, not a target:

- `median` — the typical session range. Lead with this.
- `low`/`high` — the 25th/75th percentile band: ~half of sessions land inside
  it. A quiet session sits near `low`, an expansion near `high`.
- `min`/`max` — the extremes seen in the sample (tail risk / blow-off context).
- `projected_levels.projected_high/low` apply the median range to the **live
  price** — "the session typically reaches about here," never "it will hit X."

### Sweep probability (the trap move)

`sweep_prob` is how often the forecast session sweeps the **prior** session's
high or low — the liquidity grab to watch for.

- `prob` — % of days it happened (denominator = days the prior session existed,
  reported as `n`).
- `likely_side` — high / low / either. This is the side that gets hunted more —
  the "trap" to anticipate.
- `reversal_rate` — how often the sweep closed back inside the prior range. **This
  is the tradeable edge**, not the sweep itself:
  - High sweep prob **+ high reversal rate** → fade the sweep at the prior
    extreme (sweep → CHoCH → entry).
  - High sweep prob **+ low reversal rate** → the sweep is a continuation
    breakout; trade with it, don't fade.
- **Asia forecast has no sweep** — there is no intraday session before Asia to
  sweep (the backend has no NY→Asia sweep detector). `sweep_prob.n == 0`.

### Continuation vs reversal (New York only)

`continuation_prob` is whether **New York** continues or reverses London's move:

- `continuation` — NY closed the same direction London did → trade pullbacks
  with the trend.
- `reversal` — NY went the other way → watch the London high/low for the
  rejection; **< 50% continuation = reversal-prone**.
- Only populated when `forecast_session == new_york`; otherwise `n == 0`.

### Direction skew

`direction` is the session's bullish/bearish **close** frequency — a mild
standing bias, weakest of the signals. Use as a tiebreaker, not a thesis.

### Projected levels

- `anchor_price` — the live close the projection is built on.
- `projected_high`/`projected_low` — `anchor_price` ± half the median range.
- `prior_session_high`/`prior_session_low` — the **actual** prior-session
  extremes — the concrete liquidity a sweep targets. Pair these with
  `sweep_prob`: "70% odds it sweeps the prior high at `prior_session_high`."

---

## Confidence (derive it from `n`, the tool doesn't label it)

There is no `confidence` field — judge it yourself from the sample size, the way
the backend does (30+ = HIGH, 15+ = MEDIUM, else LOW):

- **Strong:** `n` ≥ 30 and the rate is decisive (well above/below 50%). Lead
  with it.
- **Useful:** `n` ≥ 15. Guidance, not conviction.
- **Weak:** `n` < 15 or the rate is near 50/50. Treat as context only;
  recommend waiting for confirmation.

---

## How to use in analysis

1. **Lead with the forecast** for the upcoming session: "Over the last ~90 days,
   London sweeps the Asia range 70% of days (n=90) and fades it 57% of the time."
2. **Frame trade ideas around the scenarios + levels:** "If it sweeps the prior
   high at `prior_session_high`, the fade entry sets up on the CHoCH back inside."
3. **Set expectations with the expected range:** use `median`/`high` for
   realistic targets and stops, not the `max` tail.
4. **Warn on low `n`:** if the sample is thin, say so and downgrade conviction.
5. **Connect to other skills:** the sweep side → the `smc` liquidity level to
   watch; the killzone clock → *when* the move is timed; `volatility` → is the
   expected range realistic vs current ATR; `sessions` → the long-run stats.

## Always-state caveats

- **Frequencies, not certainties.** These are base rates over a recent sample;
  read every figure with its `n`.
- **Recent window, not full history.** `window.days` (~90) differs from the
  hosted dashboard's full-history figures.
- **No macro/news input.** A scheduled event (CPI, FOMC, etc.) can override any
  of these odds — the forecast is a base rate the trader layers events on top
  of, not a standalone plan.
