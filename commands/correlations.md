---
description: Cross-asset correlation for crypto — how symbols move with BTC and each other, with a recent-vs-older regime shift. Use for confirmation, diversification, and avoiding doubled-up risk.
argument-hint: [SYMBOLS...]
---

Read how a crypto symbol (or watchlist) moves relative to BTC and to each other,
and deliver a trader-facing read of regime, confirmation, and correlated risk.

Request: `$ARGUMENTS`

Steps:

1. Parse the request. Tokens are Binance symbols (comma/space separated). Accept
   friendly forms like "eth" → `ETHUSDT`, "sol" → `SOLUSDT`. If none given, use
   the default watchlist. The base defaults to `BTCUSDT` (BTC is the market's
   beta anchor) unless the user names another reference. Default timeframe `4h`.
2. Call the `get_correlations` MCP tool (server: `rektfree`) with `symbols`
   (and `base`/`timeframe` if the user specified them).
3. Interpret the JSON using the correlations skill. Do NOT dump the matrix —
   synthesize: each symbol's correlation to BTC (strength + direction), the
   regime shift (tightening vs decoupling), which names are effectively the same
   trade (high mutual correlation = doubled-up risk), where real diversification
   or a hedge exists (near-zero or negative r), and what the recent-vs-older
   shift implies about regime (risk-on rotation vs everything-follows-BTC).
4. If the tool returns an `error` (e.g. too few aligned bars, or a bad base),
   say so plainly and suggest a fix (wider `limit`, fewer symbols, valid base).
   Note any `skipped` symbols (forex pairs, bad symbols) explicitly.

Keep it concise and decision-oriented. Remember: correlation is not causation,
short windows are noisy, and most alts are high-beta to BTC by default.
