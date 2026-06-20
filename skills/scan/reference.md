# Confluence Scan — Reference Playbook

This skill grades a crypto setup with a single 0–N **confluence score**: it
stacks Smart Money Concepts (SMC) signals across the 1H entry timeframe and the
4H bias timeframe, awards points per aligned factor, and reports whether the
setup clears the hosted operating threshold. It is the plugin re-implementation
of the RektFree confluence scanner's *pure scoring math* — the same point
weights, the same required gates, the same recalibrated discipline — run on
freshly fetched Binance candles, with no AI and no database.

## Tool payload

`scan_confluence` returns:

```
{
  "symbol", "last_price", "scored_at",
  "score", "min_score", "meets_threshold",
  "direction",            # "long" | "short"
  "is_counter_trend",     # bool
  "factors": [ ... ],     # labels that fired
  "target", "invalidation"
}
```

All prices are in the symbol's quote currency. `scored_at` is UTC ISO.

---

## Scoring philosophy

The scanner is an **ICT checklist**, not a momentum oscillator. It asks: *is
price sitting in an institutional entry zone, in the direction the higher
timeframe wants, with liquidity engineered to fuel the move?* Points accrue when
the answer is yes for a given factor. The threshold is deliberately high — most
scans return **no setup**, and that is the correct, honest output. The hosted
scanner emits roughly half a signal per day per symbol; expect the same
sparsity here.

The weights are not hand-waved — they were re-calibrated against a production
backtest (n=65 settled signals, 2026-03/05). Factors that looked intuitive but
proved **anti-predictive** were dropped to zero rather than deleted, so the
discipline stays auditable. See "Recalibration" below.

---

## The required gate

**A bias-aligned order block must sit within 0.5% of the current price.** If no
such OB exists, the scan returns `score 0` with an empty `factors` list and
stops. This is by design: the scanner refuses FVG-only or trend-only signals.

When you see score 0:
- It is **not** a short (or a long). The `direction` field is just the scorer's
  default lean; ignore it.
- The honest read is **"no setup — price isn't in an order block."** Tell the
  user to wait for price to return to a zone, or point them at the SMC/levels
  tools to see where the nearest zones are.

---

## Factors and weights

Once the required OB is present, points stack as follows. Factors marked
NEUTRALIZED never fire in the plugin (their input is DB-backed and unavailable);
factors marked weight 0 are appended for narrative context but do not move the
score.

### Directional bias (the HTF filter)

- **Daily bias (+1)** — NEUTRALIZED. The plugin scans 1H + 4H only; there is no
  daily SMC pass, so this never fires.
- **4H confirms (+1)** — the 4H trend agrees with (or, absent a daily, sets) the
  higher-timeframe bias. This is the plugin's primary HTF anchor.

Direction is decided by the HTF signals; if they're silent, by the 1H trend.

### Entry zone (the core)

- **OB at price (+2, required)** — covered above.
- **FVG overlap (+1)** — an aligned fair value gap also within 0.5% of price.
  Stacks an imbalance on top of the order block — a stronger entry.
- **OB in OTE zone (+1)** — the order block sits in the 0.618–0.786 fib
  retracement of the current swing. The "optimal trade entry" pocket.

### Liquidity engineering

- **Sweep of liquidity (+2)** — a recent same-direction liquidity grab (price
  took out a level then reversed). The single strongest positive factor in the
  backtest (with-sweep WR 39.4% vs no-sweep 22%).
- **MSS / CHoCH after sweep (weight 0)** — a structure shift *after* the sweep.
  Intuitive, but the backtest showed it anti-predictive (n=12, WR 16.7% — by the
  time CHoCH prints, the entry chase is late). Listed for context only.
- **Draw on liquidity (+1)** — there is a clear unswept target (equal high/low or
  swing) within 5% in the trade direction, giving the move somewhere to go.

### Session timing (recalibrated to zero)

- **Killzone (weight 0)** — London Open (07–09 UTC) or NY Open (12–14 UTC).
- **Silver Bullet (weight 0)** — 07–08, 14–15, 18–19 UTC.
- **High sweep rate (+1)** — NEUTRALIZED (no session-events DB).

Both killzone and silver-bullet windows were *negative* in the backtest
(silver-bullet WR 16.7%, killzone 23.1%, vs 37.5% outside) — the bonuses had been
pulling the scanner into the noisy first minutes of session liquidity grabs. They
are surfaced as factors so you can mention the timing, but they carry **no
weight**. Do not treat their presence as a plus.

### Positioning, macro, flow

- **Deep premium/discount (+1)** — >80% premium for shorts, <20% discount for
  longs. Buying low / selling high within the dealing range.
- **No macro events (+1)** — NEUTRALIZED to always-on. The plugin has no macro
  calendar, so this point always lands. **This is the biggest caveat:** the scan
  is blind to news. A qualifying score into a high-impact release is still a
  high-risk trade. Always tell the user to check the calendar themselves.
- **Order flow confirms / diverges (+1 / −1)** — NEUTRALIZED (no footprint DB).
- **Derivatives confirm / oppose (+1 / −1)** — NEUTRALIZED (no derivatives DB).

### Multi-timeframe + market profile

- **Full MTF alignment 1H+4H+D (+1)** — requires all three to agree. With the
  daily leg neutralized this rarely fires.
- **OB aligns with POC/VAH/VAL (+2)** — the order block coincides with a Market
  Profile level (Point of Control / Value Area High / Low). This is **pure**
  (computed straight from the candles) and stays active. One of the two
  consistently positive factors in the backtest (the other being the sweep).

---

## The threshold and counter-trend gating

- **`min_score` = 6.** A setup qualifies when `score ≥ 6`. The threshold was
  raised 5 → 6 after the recalibration: at score ≥ 5 the score was essentially
  uncorrelated with outcome; 6 is the operating point that gives ~0.5 signals/day
  at ~48% win rate — the best honest tradeoff in the data.
- **Counter-trend setups need ≥ 8.** When `is_counter_trend` is `true` (the 1H
  trend disagrees with the HTF bias), the bar rises to 8. The tool already folds
  this into `meets_threshold`, but call out the disagreement explicitly — a
  counter-trend trade is fading the higher timeframe and deserves a louder
  caveat.

Trust `meets_threshold` for the go/no-go, but always *explain* it: which factors
got it over the line, and which high-value factors (sweep, TPO confluence) were
or weren't present.

---

## Target and invalidation

- **`target`** — the nearest structural level in the trade direction (opposite-
  side OB, FVG, swing, or equal level), capped to **2%** from entry (crypto cap).
  If no structure sits within the cap, the cap itself is used.
- **`invalidation`** — a dynamic **1.5× ATR** stop (14-period ATR on 1H), or a
  1% fallback when ATR can't be computed.
- **Compute the R:R.** reward = |target − entry|, risk = |entry − invalidation|.
  The hosted scanner rejects setups with R:R < 1.5; report the number so the user
  can apply the same discipline even though the plugin doesn't gate on it.

---

## Output format

Lead with the verdict, then the evidence:

```
VERDICT: [GO / NO-GO] — [long/short] [SYMBOL], score X/min_score
  (counter-trend: yes/no)

WHY
- Factors that fired: [list, with the weight of each high-value one]
- Missing high-value factors: [e.g. no sweep, no TPO confluence]

THE TRADE (if GO)
- Entry zone: around last_price (price is in a [bias] order block)
- Target: [price]  (~X% away)
- Invalidation: [price]  (1.5× ATR)
- Implied R:R: [reward/risk]

CAVEATS
- Structural grade only — no macro/news check (do this yourself), no
  order-flow, no avoid-signatures. Killzone/silver-bullet (if shown) = 0 weight.
```

If score is 0: say plainly there is **no setup** (no order block at price) and
suggest waiting or checking SMC/levels for where the nearest zones are.
