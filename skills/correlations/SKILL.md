---
name: correlations
description: >-
  Cross-asset correlation for crypto. Use whenever the user asks how a symbol
  moves with BTC or with another coin, about correlation / decoupling / coupling
  / tightening, risk-on rotation, whether two markets are "the same trade",
  diversification, hedging, or doubled-up / correlated risk across positions
  (BTC, ETH, SOL, alts). Pairs with the `get_correlations` MCP tool, which
  fetches aligned Binance candles and returns a Pearson correlation matrix, each
  symbol vs the base, and a recent-vs-older regime shift.
---

# Cross-Asset Correlation Analysis

You are the analyst. The `get_correlations` MCP tool (server `rektfree`) does the
computation — it fetches aligned Binance candles, computes log-return Pearson
correlations (full matrix + each symbol vs the base), and a recent-vs-older
regime shift. Your job is to **interpret** it into a clear read of regime,
confirmation, diversification, and correlated risk. Never just echo the matrix.

## Workflow

1. **Fetch.** Call `get_correlations` with `symbols` (comma/space separated;
   empty → default watchlist), `base` (default `BTCUSDT`), `timeframe` (default
   `4h`), and `limit` (default 180 bars). Crypto only — forex pairs (`_`) are
   skipped and reported in `skipped`.
2. **Interpret.** Read `vs_base`, `matrix`, and `window` against the rules in
   [reference.md](reference.md) — the full correlation playbook (Pearson
   interpretation, crypto regime reading, confirmation vs correlated risk).
3. **Synthesize.** Produce the structured output below. Lead with the regime
   read (is everything following BTC, or is something decoupling) and the most
   actionable relationship.

## Payload key

`get_correlations` returns:
- `base`, `timeframe`, `window` ({bars, from, to}) — the aligned sample.
- `vs_base` — list of `{symbol, r, strength, direction, recent_r, older_r,
  shift}`, sorted by |r| descending. `r` is Pearson on log returns vs the base.
  `strength`: |r|>0.7 strong / 0.4–0.7 moderate / <0.4 weak. `direction`:
  same / opposite / none. `shift`: tightening (recent r rose) / decoupling
  (recent r fell) / stable, comparing the recent half of the window to the older.
- `matrix` — symmetric `{symbol: {symbol: r}}`, 1.0 on the diagonal.
- `skipped` — symbols dropped (forex, bad symbol, fetch error) with reasons.

## Output shape

```
REGIME READ
- Are alts tightening to BTC (risk-on / everything-follows-BTC) or decoupling?
- Overall: high mutual correlation = one-trade market; spread-out = rotation.

VS BASE (correlation to {base})
- Per symbol: r, strength + direction, and the recent-vs-older shift
- Call out the strongest follower and anything decoupling

SAME-TRADE / CORRELATED RISK
- Pairs with high mutual r in the matrix = effectively one position
- Warn if the user is (or would be) doubled-up on correlated names

DIVERSIFICATION / HEDGE
- Near-zero r = genuine diversification; negative r = a hedge
- Confirmation: aligned moves across correlated names strengthen a directional read

CAVEATS
- Window length, noise, correlation ≠ causation where relevant
```

## Interpretation guardrails

- **BTC is the anchor.** Most alts are high-beta to BTC by default — a strong
  positive r is the baseline, not a signal. The *interesting* readings are
  decoupling, unusually low r, or a sign flip.
- **Tightening vs decoupling is the regime tell.** Rising correlation to BTC
  across the board = risk-off / everything-follows-BTC (alts are just leverage on
  BTC). Falling correlation = rotation / alt-season behavior / idiosyncratic
  drivers. Read `shift` alongside `recent_r`.
- **Correlated names are one trade.** If two symbols correlate strongly, a
  position in both is doubled-up risk, not diversification. Flag it.
- **Use correlation for confirmation, not as an entry.** A move confirmed across
  correlated names is higher-conviction; a lone move in a normally-correlated
  name is suspect (divergence — fade or wait).
- **Short windows are noisy.** Few aligned bars or a short timeframe → treat
  borderline r values as soft. Prefer the `recent_r`/`older_r` agreement over a
  single point estimate.
- **Correlation ≠ causation.** Two assets moving together may share a driver
  (macro, USD, risk sentiment), not cause each other.

See [reference.md](reference.md) for the complete definitions and rules.
