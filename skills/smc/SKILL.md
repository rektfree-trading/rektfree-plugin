---
name: smc
description: >-
  Smart Money Concepts (SMC) market analysis for crypto. Use whenever the user
  asks about market structure, trend bias, order blocks, fair value gaps (FVG),
  liquidity, BOS/CHoCH, equal highs/lows, premium/discount, or where to enter or
  invalidate a crypto trade (BTC, ETH, SOL, etc.). Pairs with the `analyze_smc`
  MCP tool, which fetches Binance candles and returns the raw structure.
---

# Smart Money Concepts (SMC) Analysis

You are the analyst. The `analyze_smc` MCP tool (server `rektfree`) does the
detection — it fetches Binance OHLCV and returns structured SMC data. Your job is
to **interpret** it into a clear, decision-oriented read. Never just echo the
JSON.

## Workflow

1. **Fetch.** Call `analyze_smc` with the `symbol` (e.g. `BTCUSDT`), `timeframe`
   (default `1h`), and optionally `limit` (50–1000, default 500). Crypto only —
   forex pairs (containing `_`) are not supported and the tool will return an
   error.
2. **Interpret.** Read the returned fields against the rules in
   [reference.md](reference.md) — the full SMC playbook (BOS/CHoCH, order blocks,
   FVGs, EQH/EQL, premium/discount, strong/weak levels, confluence priority).
3. **Synthesize.** Produce the structured output below. Lead with the bias and
   the highest-confluence zone; a trader should be able to act on it.

## Output shape

```
STRUCTURE
- Trend: <bullish/bearish/neutral> (from trend_bias + recent BOS/CHoCH)
- Recent shifts: <BOS/CHoCH with levels>

KEY ZONES
- Order blocks: <unmitigated OBs, bias, price range>
- Fair value gaps: <unmitigated FVGs, bias, range>
- Strong/weak levels: <protected vs targeted swing points>

LIQUIDITY
- Equal highs/lows: <EQH/EQL levels — resting liquidity>
- Recent sweeps: <liquidity grabs and what they imply>

POSITIONING
- Premium/discount: <where last_price sits in the swing_high→swing_low range>

THE READ
- Bias + highest-confluence zone (OB + FVG + trend + discount/premium align)
- Liquidity target(s)
- Invalidation: <what would flip the read>
```

## Interpretation guardrails

- **Confluence beats single signals.** OB + FVG + trend alignment + correct
  premium/discount zone is the highest-probability read. A lone OB is weak.
- **Always flag contradictions.** Bullish OB in a bearish trend, or an FVG in
  premium during a downtrend, lowers probability — say so.
- **Premium/discount:** compute where `last_price` falls between `swing_low`
  (0% / discount) and `swing_high` (100% / premium). Buy discount, sell premium,
  aligned with trend.
- **Liquidity is a magnet.** EQH/EQL and unmitigated FVGs tend to get taken;
  treat them as targets, not safe stop locations.
- **Higher timeframe sets bias, lower timeframe times entries.** If the user
  wants precision, suggest checking a higher TF (4h/1d) for bias.

See [reference.md](reference.md) for the complete definitions and rules.
