---
name: derivatives
description: >-
  Crypto futures positioning analysis. Use whenever the user asks about funding
  rate, open interest (OI), long/short ratio, taker buy/sell flow, leverage,
  perps/perpetuals, crowding, or squeeze risk for a crypto symbol (BTC, ETH, SOL,
  etc.). Pairs with the `get_derivatives` MCP tool, which pulls keyless data from
  Binance Futures. Not available for forex.
---

# Derivatives / Futures Positioning

You are the analyst. The `get_derivatives` MCP tool (server `rektfree`) fetches
funding, open interest, long/short ratios, and taker flow from Binance Futures
(keyless). Your job is to read **how leveraged traders are positioned** and where
squeezes may fire — not to echo the JSON. Crypto only; forex has no futures data.

## Workflow

1. **Fetch.** Call `get_derivatives` with `symbol` (e.g. `BTCUSDT`) and optional
   `period` (default `1h`, 24-period lookback). Forex pairs (`_`) are rejected.
2. **Interpret** each metric against the thresholds in
   [reference.md](reference.md):
   - **Funding** — sign = which side pays (bias); magnitude = crowding. Use
     `annualized_pct` for the real cost of holding. Extremes → squeeze risk.
   - **Open interest** — pair the OI `trend` / `change_pct` with price: rising OI
     backs the move (new positions); falling OI = closing/unwind (squeeze or
     exhaustion). Flag OI change > 5% over ~1h as notable.
   - **Long/short ratio** — `global_ratio` is the crowd; `top_trader_ratio` is
     large accounts (smart-money proxy). Read extremes contrarian, **and** flag
     divergence: crowd long while top traders cut = caution for longs.
   - **Taker buy/sell ratio** — aggressor flow. Divergence from price = absorption
     (ratio up, price down → bullish) or distribution (ratio down, price up →
     bearish).
3. **Synthesize** a positioning signal with squeeze risk, always citing numbers.

## Output shape

```
DERIVATIVES POSITIONING
- Funding: [rate_pct]% ([annualized_pct]% APR) — [longs/shorts pay, bias], next in [h]h
- Open Interest: [value] ([change_pct]%, [trend]) — [new positions / unwind]
- Long/Short: global [x] ([trend]), top-trader [x] ([trend]) — [crowd vs smart money]
- Taker: [ratio] ([trend]) — [buyers/sellers aggressive]

POSITIONING SIGNAL
- [Bullish/Bearish/Neutral] — [the metric driving it]
- Squeeze risk: [Low/Medium/High] — [why]
```

## Guardrails

- **Funding + OI together** tell the squeeze story: extreme funding + rising OI =
  a crowded, leveraged book primed to unwind violently. Cite both.
- **Positioning is often contrarian.** Heavily-long crowds get squeezed; don't
  read a high long ratio as bullish confirmation.
- **Top-trader vs global divergence is the edge** — when large accounts lean
  opposite the crowd, weight the large accounts.
- **Confirm, don't lead.** Derivatives confirm or warn against a structural
  (SMC/levels) thesis; they're not a standalone entry trigger.

See [reference.md](reference.md) for the full thresholds and interpretation.
