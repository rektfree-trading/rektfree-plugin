# Order Flow — Reference Playbook

This skill analyzes the buying and selling pressure within each candle and
across time. Price charts show *where* price went; order flow reveals *how* it
got there — whether a move is driven by genuine demand or is likely to fail. By
examining delta, cumulative delta (CVD), absorption, exhaustion, footprint
imbalances, and large trades, this skill exposes the real-time intentions of
market participants and gives early warning of reversals or continuations.

## Tool payload

`get_orderflow` returns
`{ "symbol", "timeframe", "candles": [...], "cvd": [...] }`. Footprints are
reconstructed on the fly from Binance's keyless aggregated-trades endpoint, so
this is crypto-only (OANDA has no tick data). Timeframes: **5m, 15m, 1h**.

Each `candles[]` entry:

| Field | Type | Description |
|---|---|---|
| `timestamp` | float | Bucket start, unix seconds |
| `tick_size` | float | Price-bucket size for the levels (auto from price) |
| `buy_volume` | float | Aggressive buy volume (market buys hitting the ask) |
| `sell_volume` | float | Aggressive sell volume (market sells hitting the bid) |
| `delta` | float | `buy_volume − sell_volume` for the candle |
| `buy_count` | int | Number of aggressive buy executions |
| `sell_count` | int | Number of aggressive sell executions |
| `price_levels` | dict | Per-price-level breakdown (see below) |
| `large_trades` | list | Large individual trades in this candle (see below) |

`price_levels` is a **dict keyed by stringified price** → `{bv, sv, bc, sc}`:
- `bv` = buy volume at that price level
- `sv` = sell volume at that price level
- `bc` = buy execution count
- `sc` = sell execution count

`large_trades[]` entries are compact: `{t, p, v, q, s}`:
- `t` = timestamp (unix seconds), `p` = price, `v` = volume (base currency),
  `q` = quote value (USD), `s` = side (`"buy"` / `"sell"`).

Top-level `cvd[]` is the running cumulative delta: `{timestamp, cvd}` per
candle. A `truncated: true` flag means the trade window hit the request budget,
so the earliest candle(s) may be partial.

> Buy vs sell uses Binance's maker flag: a trade where the buyer was the maker
> means an aggressive market **sell** hit the bid (`is_buy = not isBuyerMaker`).

---

## Concepts & Definitions

### 1. Volume Delta
The difference between aggressive buying and aggressive selling within one
candle. `delta = buy_volume − sell_volume`.
- Positive = more aggressive buying; negative = more aggressive selling. Magnitude
  matters (a +500 BTC delta dwarfs +5 BTC).
- **Positive delta + green candle** / **negative delta + red candle** =
  confirming, trend healthy.
- **Positive delta + red candle** = buyers absorbing supply → potential reversal
  up. **Negative delta + green candle** = sellers absorbing demand → reversal down.
- Diverging delta at a key level (OB, FVG, POC, session H/L) = high-probability
  reversal. Near-zero delta on a large candle = balanced aggression; breakout may
  fail.

### 2. CVD (Cumulative Volume Delta)
Running total of delta over the returned candles (`cvd[]`). `CVD(n) = CVD(n-1) +
delta(n)`.
- Rising CVD = accumulation; falling = distribution; flat = balanced.
- **Confirmation:** price up + CVD up (or both down) = genuine, flow-supported
  trend.
- **Divergence (the most powerful signal):** price higher highs + CVD lower highs
  = bearish divergence (rally on fumes); price lower lows + CVD higher lows =
  bullish divergence (decline losing momentum).
- CVD divergence at an HTF key level = the highest-probability reversal signal in
  order flow. The reconstructed window is short — treat `cvd` as an intraday /
  session view, not a multi-day trend.

### 3. Absorption
Aggressive orders on one side are matched by large passive orders on the other,
so delta diverges from price.
- Price flat/down while delta strongly positive = **buy-side absorption** (large
  buyer soaking up selling). Price flat/up while delta strongly negative =
  **sell-side absorption**.
- Absorption at support (OB, VAL, session low) = institutional buyer defending →
  bullish. At resistance (OB, VAH, session high) → bearish.
- Enter in the direction of the absorber. If absorption eventually fails (price
  breaks through), expect a sharp move in the breakout direction.

### 4. Exhaustion
A volume/delta spike at a price extreme followed by a stall or reversal.
- Volume spike (2x+ average) at a swing high/low, delta spike in the trend
  direction, then a doji or opposite-colored candle (often a long wick).
- Exhaustion at a high = last buyers in → bearish reversal; at a low =
  capitulation → bullish reversal. Most powerful at a key level. Wait for the
  next candle to confirm.

### 5. Footprint Imbalances (price-level detail)
Use `price_levels` to see where volume concentrated inside the candle.
- At a level: `bv / sv >= 3.0` = **buying imbalance**; `sv / bv >= 3.0` =
  **selling imbalance**.
- Buying imbalance at the bottom of a candle = strong support; selling imbalance
  at the top = strong resistance.
- **Stacked imbalances** (3+ consecutive price levels, same side) = institutional
  campaign — the clearest sign of committed flow.
- The price level with the most total volume is the intra-candle **point of
  control** — micro support/resistance.

### 6. Large Trades (volume bubbles)
`large_trades[]` flags individual fills above a quote-value threshold
(~$50k BTC, $25k ETH, $10k SOL / default).
- Large buy at support / large sell at resistance = institutional entry.
- A cluster at one price level = strong institutional interest → S/R zone.
- A large trade against the current candle = potential reversal trigger. Large
  trades during low-volume periods are more significant.

### 7. Trade Counts (`buy_count` / `sell_count`)
Counts of executions vs volume (size).
- High count + low volume = many small (retail) orders. Low count + high volume =
  few large (institutional) orders.
- High count + small delta = two-way indecision. Follow the institutional profile
  (few trades, large volume) over the retail one.

---

## Practical Rules

1. **Delta confirms or denies price** — always check flow supports direction.
2. **Divergences are the most powerful signals** — when price and CVD/delta
   disagree, trust the flow.
3. **Absorption at key levels is institutional** — it shows where big players sit.
4. **Exhaustion marks turning points** — volume spikes at extremes then reversal.
5. **Stacked imbalances are committed flow** — the clearest institutional footprint.
6. **Large trades validate levels** — a whale trading at a key level confirms it.
7. **Context matters** — signals at key levels (OB, FVG, POC, session H/L) are
   3–5x more reliable than in open space.
8. **Volume precedes price** — flow shifts often appear 1–3 candles before the
   reversal shows on price.

### Combining with other skills
- Delta/CVD divergence at a key level (PDH/PDL, POC) = highest-probability reversal.
- Absorption at an Order Block = institutional confirmation of the OB.
- Exhaustion at a session high/low = session reversal signal.
- Stacked imbalances at VAH/VAL = strong value-area defense.
- Large trades at an FVG = confirms the gap is institutional.
- CVD trend agreeing with SMC bias = high-conviction directional trade.

---

## Output Format

```
ORDER FLOW SUMMARY
- Current candle delta: [positive/negative, magnitude]
- CVD trend: [Rising / Falling / Flat]
- CVD vs price: [Confirming / Diverging]

DELTA ANALYSIS
- Recent delta pattern (last 5–10 candles)
- Notable delta spikes and any delta-vs-direction divergences

FOOTPRINT DETAIL
- Significant imbalances (price levels with 3:1+ bv/sv or sv/bv)
- Stacked imbalances (consecutive same-side levels)
- High-volume price levels (intra-candle point of control)

ABSORPTION / EXHAUSTION
- Active absorption zones and side (buy/sell)
- Recent exhaustion signals

LARGE TRADES
- Recent large trades (price, side, quote value)
- Clustering at price levels; institutional bias

ORDER FLOW BIAS
- Overall bias: [Bullish / Bearish / Neutral]
- Confidence: [High / Medium / Low]
- Key signal: [single most important observation]
- Invalidation: [what would change this assessment]
```
