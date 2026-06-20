# Derivatives — Reference Playbook (Crypto Only)

Futures positioning data — funding rates, open interest, long/short ratios, and
taker activity — reveals how leveraged traders are positioned and where squeezes
may fire. Source: Binance Futures public endpoints (keyless). Crypto only; forex
has no equivalent — say so if asked.

## Tool payload

`get_derivatives` returns `mark_price`, a `lookback` descriptor, and:
`funding` (`rate_pct`, `annualized_pct`, `next_funding_in_hours`), `open_interest`
(`current`, `value_usdt`, `change_pct`, `trend`), `long_short` (`global_ratio` +
`global_trend`, `top_trader_ratio` + `top_trader_trend`), `taker`
(`buy_sell_ratio`, `trend`), and compact `series` for OI / global L/S / taker.

---

## Key Metrics

### Funding Rate
The periodic payment (every 8h on Binance) between longs and shorts that keeps
the perp aligned with spot. `annualized_pct` ≈ rate × 3 × 365 — the real holding
cost.

- **Positive** (e.g. +0.01%): longs pay shorts → bullish-biased, crowded long.
  - **> +0.05%**: overcrowded longs → vulnerable to a long squeeze / correction.
- **Negative** (e.g. −0.01%): shorts pay longs → bearish-biased, crowded short.
  - **< −0.03%**: overcrowded shorts → vulnerable to a short squeeze / pump.
- **Near zero** (±0.005%): balanced, no extreme.

### Open Interest (OI)
Total open futures contracts (the plugin reports coin units + USDT value + the
trend/% change over the lookback).

- **OI rising + price rising** → new longs; trend supported (bullish).
- **OI rising + price falling** → new shorts; trend supported (bearish).
- **OI rising + price flat** → buildup without direction; fragile, expect a sharp
  move either way.
- **OI falling + price rising** → short squeeze (shorts closing); may be temporary.
- **OI falling + price falling** → long liquidation cascade; may be temporary.
- **OI change > 5% in ~1h** → significant; flag it.

### Long/Short Account Ratio
Net-long vs net-short accounts. The plugin gives **global** (the crowd) and
**top-trader** (large accounts — a smart-money proxy).

- **> 1.5**: heavily long-biased → contrarian, potential long squeeze.
- **< 0.7**: heavily short-biased → contrarian, potential short squeeze.
- **0.8–1.2**: balanced.
- **Divergence**: when `top_trader_ratio` leans opposite the `global_ratio`
  (e.g. crowd piling long while top traders cut), weight the large accounts.

### Taker Buy/Sell Ratio
Aggressive (market-order) buy vs sell volume.

- **> 1.2**: buyers aggressive → bullish pressure.
- **< 0.8**: sellers aggressive → bearish pressure.
- **Divergence from price**: ratio rising while price falls = absorption
  (bullish); ratio falling while price rises = distribution (bearish).

---

## How to Use in Analysis

1. **Directional confirmation**: SMC bullish + funding negative + taker > 1 =
   strong bullish confluence.
2. **Squeeze detection**: extreme funding + OI building = squeeze setup — cite the
   specific numbers.
3. **Risk assessment**: high OI + extreme funding = volatile; reduce size.
4. **Top vs crowd**: lean with the top-trader ratio when it diverges from global.
5. **Always cite numbers**: "Funding −0.023% with OI +4.2% — shorts crowded,
   squeeze risk elevated."

---

## Output Format

```
DERIVATIVES POSITIONING:
  Funding Rate: [rate_pct]% ([annualized_pct]% APR) — [who pays, bias]; next in [h]h
  Open Interest: [value] ([change_pct]%, [trend]) — [new positions / unwind]
  Long/Short: global [x] ([trend]) | top-trader [x] ([trend]) — [crowd vs smart money]
  Taker Buy/Sell: [ratio] ([trend]) — [buyers/sellers aggressive]

POSITIONING SIGNAL:
  [Bullish/Bearish/Neutral] — [reason + the driving metric]
  Squeeze Risk: [Low/Medium/High] — [why]
```
