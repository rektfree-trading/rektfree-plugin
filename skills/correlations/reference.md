# Cross-Asset Correlation — Reference Playbook

This skill measures how crypto assets move *together*. It computes the Pearson
correlation of log returns between symbols over an aligned window, reports each
symbol's correlation to a base (default BTC), and flags how that correlation is
shifting recent-vs-older. Correlation tells you whether two markets are the same
trade, whether a move is confirmed across names, and where real diversification
or a hedge actually exists — the inputs to sizing and risk, not entries.

## Tool payload

`get_correlations` returns:

```
{
  "base": "BTCUSDT",
  "timeframe": "4h",
  "window": { "bars": 179, "from": "...", "to": "..." },
  "vs_base": [
    { "symbol", "r", "strength", "direction", "recent_r", "older_r", "shift" }
  ],
  "matrix": { "BTCUSDT": { "BTCUSDT": 1.0, "ETHUSDT": 0.86, ... }, ... },
  "skipped": [ { "symbol", "reason" } ]
}
```

- `r` — Pearson correlation of log returns over the aligned window.
- `strength` — |r| > 0.7 strong, 0.4–0.7 moderate, < 0.4 weak.
- `direction` — same (r ≥ 0.1), opposite (r ≤ −0.1), none (near zero).
- `recent_r` / `older_r` — `r` over the recent half / older half of the window.
- `shift` — tightening (recent r rose meaningfully), decoupling (recent r fell),
  or stable.
- `matrix` — symmetric, 1.0 on the diagonal. `vs_base` is sorted by |r| desc.

All series are timestamp-aligned: only bars present for *every* symbol are used,
so the correlations compare matching candles.

---

## Concepts & Definitions

### 1. Pearson correlation (r)
A number in **[−1, +1]** measuring the *linear* co-movement of two return series.

- **+1** — perfectly in lockstep: when one rises x%, the other rises proportionally.
- **0** — no linear relationship: one tells you nothing about the other.
- **−1** — perfectly opposed: one up means the other down, proportionally.

It is computed on **log returns**, not prices. Two assets can both trend up yet
have low return correlation if their *day-to-day moves* aren't synchronized — and
correlation of prices is misleading (two unrelated uptrends look "correlated").
Returns are the honest input.

### 2. Strength and direction
- **Strong (|r| > 0.7):** the two effectively move as one. Treat as the same risk.
- **Moderate (0.4–0.7):** related but with meaningful independent movement.
- **Weak (< 0.4):** largely independent over this window.
- **Direction:** the sign. Positive = same direction; negative = opposite (a
  potential hedge); near-zero = unrelated (diversification).

### 3. Regime shift (recent vs older)
The same correlation computed over the recent half of the window vs the older
half. The *change* is often more informative than the level:

- **Tightening** (correlation to BTC rising) — the market is consolidating into
  one trade. Risk-off, fear, or strong BTC-led trends pull everything together;
  alts behave like leverage on BTC. Diversification across alts evaporates.
- **Decoupling** (correlation to BTC falling) — idiosyncratic drivers, rotation,
  or alt-season behavior. A name is trading on its own catalysts. This is where
  relative-strength and pair trades come alive.
- **Stable** — relationship is holding; the existing read carries.

---

## Crypto Regime Reading

- **BTC is the beta anchor.** In crypto, BTC leads. Most alts are *high-beta to
  BTC by default* — a strong positive r to BTC is the baseline, not news. The
  signal is in the exceptions: a low or falling r, or a sign flip.
- **"Everything follows BTC" regimes** show up as a matrix where nearly every
  off-diagonal cell is > 0.7 and `shift` is broadly tightening. In these regimes,
  picking alts adds risk, not edge — you're just levering a BTC view. Express the
  view in BTC (or size down) rather than spreading across correlated alts.
- **Rotation / risk-on regimes** show falling BTC correlations and dispersion in
  the matrix. Capital is moving between sectors; relative strength matters; an alt
  outperforming a flat BTC (decoupling, up) is a genuine standalone signal.
- **ETH and SOL** typically run 0.6–0.95 vs BTC. Large-cap majors cluster tightly;
  smaller/narrative coins decouple more often. A major (ETH/SOL) showing
  unusually *low* correlation is a notable regime tell.

---

## Using Correlation in Practice

### Confirmation (use correlated names to validate a move)
When normally-correlated assets all move the same way, a directional read is
**higher-conviction** — the move is market-wide, not a single-name fakeout.
Conversely, a move in one name that its correlated peers *don't* confirm
(divergence) is suspect: either an early signal or a trap. Wait for confirmation
or fade the outlier.

### Avoiding correlated double-risk (the main risk use)
Two strongly correlated positions are **one trade with double the size**. Long
ETH + long SOL in a tightening regime is not diversification — it's a leveraged
BTC long wearing two tickers. Before adding a position, check its correlation to
what you already hold; if it's high, you're concentrating, not spreading risk.
Size the *combined* exposure, not each leg independently.

### Diversification and hedging
- **Near-zero r** = genuine diversification — the assets respond to different
  drivers, so combined risk is lower than the sum.
- **Negative r** = a hedge — one offsets the other. Rare and usually unstable in
  crypto (most things are positively correlated, especially when it matters), so
  verify with the `shift` before relying on it.

### Pair / relative-strength reads
Decoupling (one alt strengthening vs a flat or weak BTC) is the setup for
relative-strength longs and pair trades. The matrix surfaces which names are
breaking from the pack.

---

## Practical Rules

1. **Returns, not prices.** Correlation is on log returns; ignore "they both went
   up" intuition.
2. **The change beats the level.** `shift` (tightening/decoupling) is often more
   actionable than a single r.
3. **High mutual r = one position.** Collapse correlated names into a single risk
   bucket when sizing.
4. **Confirm, don't enter.** Use correlation to validate or question a move, not
   as a standalone trigger.
5. **Borderline r near 0.4 is soft** — especially on short windows; don't
   over-read a single point estimate.

## Caveats

- **Correlation ≠ causation.** Co-movement usually means a *shared driver*
  (USD, macro, risk sentiment), not that one asset moves the other.
- **Short windows are noisy.** Few aligned bars or a short timeframe gives
  unstable r. Prefer more bars (wider `limit`) or a higher timeframe for a
  structural read; use short windows only for "what's happening right now".
- **Correlation is not constant.** It spikes toward 1.0 in crashes/risk-off
  (everything sells together) exactly when diversification is needed most — the
  `shift` field exists to catch this.
- **Linear only.** Pearson misses non-linear and lagged relationships; two assets
  can be related in ways r near 0 won't show.
- **Alts are high-beta to BTC.** A strong positive number is the default, not an
  insight. Read against that baseline.
