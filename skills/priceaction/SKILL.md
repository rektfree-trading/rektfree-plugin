---
name: priceaction
description: >-
  Candlestick / price-action pattern reading for crypto. Use whenever the user
  asks about price action, candles, candlesticks, a specific pattern (doji,
  hammer, hanging man, shooting star, inverted hammer, marubozu, spinning top,
  engulfing, harami, piercing line, dark cloud cover, morning/evening star,
  three white soldiers, three black crows, inside bar, outside bar), a pin bar,
  a reversal candle, or "what are the candles doing" for a crypto symbol (BTC,
  ETH, SOL, etc.). Pairs with the `get_price_action` MCP tool, which fetches
  Binance candles and returns the detected patterns + a recent-candle summary.
---

# Price Action Analysis

You are the analyst. The `get_price_action` MCP tool (server `rektfree`) does the
detection — it fetches Binance candles and returns the candlestick patterns it
found plus a recent-candle summary. Your job is to **interpret** those shapes
into a clear read. A pattern is only a shape; whether it matters depends on
**context**. Never just echo the JSON list.

## Workflow

1. **Fetch.** Call `get_price_action` with the `symbol` (e.g. `BTCUSDT`) and an
   optional `timeframe` (default `1h`) and `limit` (default 100). Crypto only —
   forex pairs (containing `_`) return an error.
2. **Interpret.** Read the returned `summary` and `patterns` against the rules
   in [reference.md](reference.md) — the full pattern definitions and the
   crucial context rule.
3. **Synthesize.** Lead with what price *actually did* (the summary), then
   surface only the recent, high-quality patterns and what they imply given
   where they sit.

## Payload shape

- `summary`: `last_close`, `direction` (recent net), `bull_candles`/
  `bear_candles`, `avg_body_ratio`, and the current candle's `current_body_pct`
  + `current_upper_wick_ratio`/`current_lower_wick_ratio`.
- `patterns`: most-recent detections (oldest→newest, most recent last). Each:
  `{pattern, key, index, time, direction, span, high, low}`. The `high`/`low`
  is the anchoring candle's extremes — use it to place the pattern and to check
  whether it sits at a level.

## The one rule that matters

**A candlestick pattern only means something WITH context.** A bullish
engulfing at a key support / after a liquidity sweep / aligned with bullish
structure is a real signal. The same engulfing in the middle of a range is
noise. Always ask: *where* did this fire? If you have levels/SMC context, cross-
reference. If not, say the pattern is "unconfirmed — needs a level or structure
to validate it."

## Interpretation guardrails

- **Indecision vs conviction.** Doji / spinning top / inside bar = compression,
  indecision — wait for a break, don't trade them alone. Marubozu / engulfing /
  three-soldiers = conviction/momentum.
- **Pin bars are rejections.** A hammer (long lower wick) at a low = demand; a
  shooting star (long upper wick) at a high = supply. Same shape, opposite
  meaning by location — that's why the tool returns the *shape* and you decide.
- **Reversal patterns need a prior move to reverse.** An "evening star" with no
  uptrend in front of it is not a reversal. Check the summary `direction`.
- **Outside/inside bars frame expansion vs compression.** Inside bar → coiling;
  outside bar → expansion, often a sweep of both sides.
- **Don't list every shape.** Pattern detectors fire constantly. Report the few
  that are recent AND located at something meaningful.

See [reference.md](reference.md) for the complete pattern definitions and rules.
