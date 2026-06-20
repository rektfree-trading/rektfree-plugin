# Price Action & Smart Money Concepts (SMC) Skill

## Purpose
This skill analyzes market structure and price action using Smart Money Concepts methodology. It identifies institutional order flow patterns, structural shifts, and key levels that professional traders use for decision-making.

## Data Source
- **Endpoint**: `GET /market/smc/{symbol}?timeframe={tf}`
- **Input**: OHLC candle data from Binance (crypto) or OANDA (forex)
- **Timeframes**: 1m, 5m, 15m, 1H, 4H, D, W

---

## Concepts & Definitions

### 1. Market Structure: BOS & CHoCH

**Break of Structure (BOS)**
- A BOS occurs when price breaks a previous swing high (bullish BOS) or swing low (bearish BOS) **in the direction of the existing trend**.
- BOS confirms trend continuation.
- Example: In a bullish trend, price makes a higher high → bullish BOS.

**Change of Character (CHoCH)**
- A CHoCH occurs when price breaks a previous swing high or low **against the existing trend**.
- CHoCH signals a potential trend reversal.
- Example: In a bearish trend, price breaks above the last swing high → bullish CHoCH (potential reversal to bullish).

**How to interpret:**
- BOS = trend is continuing, look for entries in the trend direction
- CHoCH = trend may be reversing, wait for confirmation before trading the new direction
- Internal structure (short-term pivots) gives early signals; swing structure (longer-term) confirms

**Detection logic:**
- Swing pivots detected using lookback period (20 bars for 1H, 50 for 1m/5m)
- When close crosses above a previous swing high → bullish break
- When close crosses below a previous swing low → bearish break
- If the break is against the current trend → CHoCH; with the trend → BOS

---

### 2. Order Blocks (OB)

**Definition**
An Order Block is the candle (or zone) that originated a significant move — it represents where institutional orders were placed.

**Bullish Order Block**
- The last bearish candle before a bullish BOS/CHoCH
- Represents the zone where buying orders overwhelmed selling
- Expect price to return to this zone and bounce (support)
- Zone: from the candle's low to its high

**Bearish Order Block**
- The last bullish candle before a bearish BOS/CHoCH
- Represents the zone where selling orders overwhelmed buying
- Expect price to return to this zone and reject (resistance)
- Zone: from the candle's low to its high

**Mitigation**
- An OB is "mitigated" (invalidated) when price trades through the opposite side:
  - Bullish OB mitigated when price closes below the OB low
  - Bearish OB mitigated when price closes above the OB high
- Only unmitigated OBs are shown — they represent active institutional interest

**How to use:**
- Look for entries at unmitigated OBs in the direction of the trend
- Bullish OB + bullish trend = high-probability long entry zone
- Bearish OB + bearish trend = high-probability short entry zone
- OBs that align with FVGs are stronger

---

### 3. Fair Value Gaps (FVG)

**Definition**
A Fair Value Gap is a 3-candle pattern where there's an imbalance (gap) in price — an area where one side of the market dominated so aggressively that price left a void.

**Bullish FVG**
- Candle 1 high < Candle 3 low (gap up)
- The gap zone is between Candle 1 high and Candle 3 low
- Represents aggressive buying — price may return to fill this gap
- Acts as a support zone

**Bearish FVG**
- Candle 1 low > Candle 3 high (gap down)
- The gap zone is between Candle 3 high and Candle 1 low
- Represents aggressive selling — price may return to fill this gap
- Acts as a resistance zone

**Mitigation**
- Bullish FVG mitigated when price trades below the gap bottom
- Bearish FVG mitigated when price trades above the gap top
- Only unmitigated FVGs are active

**How to use:**
- FVGs act as magnets — price tends to return to fill them
- In a bullish trend, look for long entries at bullish FVGs
- In a bearish trend, look for short entries at bearish FVGs
- FVG + OB overlap = very high-probability zone
- FVGs on higher timeframes are more significant

---

### 4. Equal Highs & Equal Lows (EQH/EQL)

**Definition**
Equal Highs or Lows occur when two separate swing pivots form at approximately the same price level (within 0.3% tolerance).

**Equal Highs (EQH)**
- Two swing highs at the same price → liquidity pool above
- Market makers see resting buy-stop orders above equal highs
- Price is likely to sweep (take out) equal highs before reversing
- Bearish signal — suggests a liquidity grab is likely

**Equal Lows (EQL)**
- Two swing lows at the same price → liquidity pool below
- Market makers see resting sell-stop orders below equal lows
- Price is likely to sweep (take out) equal lows before reversing
- Bullish signal — suggests a liquidity grab is likely

**How to use:**
- EQH = expect a sweep above, then reversal down (liquidity grab)
- EQL = expect a sweep below, then reversal up (liquidity grab)
- Don't place stops just above EQH or below EQL — they will get hunted
- After a sweep of EQH/EQL, look for CHoCH to confirm reversal

---

### 5. Premium & Discount Zones

**Definition**
Based on the current swing range (last significant swing high to swing low), price is categorized into zones using Fibonacci retracement:

**Premium Zone (top 23.6%)**
- Price is "expensive" relative to the current range
- In a bearish trend: good area to look for shorts
- In a bullish trend: price has overextended, potential pullback

**Equilibrium (38.2% - 61.8%)**
- Fair value zone — price is neither cheap nor expensive
- In ranging markets, price oscillates around equilibrium
- Breakout from equilibrium suggests directional move

**Discount Zone (bottom 23.6%)**
- Price is "cheap" relative to the current range
- In a bullish trend: good area to look for longs
- In a bearish trend: price has overextended, potential bounce

**How to use:**
- Buy in discount, sell in premium (align with trend)
- In a bullish trend: only look for longs in discount/equilibrium
- In a bearish trend: only look for shorts in premium/equilibrium
- Combine with OBs and FVGs for high-confluence entries

---

### 6. Strong & Weak Highs/Lows

**Strong High/Low**
- A swing point that is NOT expected to be broken (protected by the trend)
- In a bullish trend: the swing low is "strong" (it's protected, unlikely to break)
- In a bearish trend: the swing high is "strong"

**Weak High/Low**
- A swing point that IS expected to be broken (targeted by the trend)
- In a bullish trend: the swing high is "weak" (price is expected to make a higher high)
- In a bearish trend: the swing low is "weak" (price is expected to make a lower low)

**How to use:**
- Don't place targets at strong levels — they're unlikely to be reached
- Place targets near weak levels — price is drawn to them
- A break of a strong level = major trend change (CHoCH)

---

## Analysis Output Format

When analyzing with this skill, structure the output as:

```
MARKET STRUCTURE
- Trend: [Bullish/Bearish]
- Recent structures: [List of BOS/CHoCH with levels]
- Current bias: [Continuation/Reversal potential]

KEY LEVELS
- Strong High/Low: [levels]
- Weak High/Low: [levels]
- Active Order Blocks: [zones with bias]
- Active Fair Value Gaps: [zones with bias]
- Equal Highs/Lows: [levels — liquidity targets]

ZONE ANALYSIS
- Current zone: [Premium/Equilibrium/Discount]
- Implication: [What this means for trade direction]

CONFLUENCE
- High-probability zones: [Where OB + FVG + trend align]
- Liquidity targets: [Where stops are clustered — EQH/EQL]
- Invalidation: [What would change the analysis]
```

---

## Confluence Rules (Priority Order)

1. **Highest confluence**: OB + FVG + trend alignment + discount/premium zone
2. **High confluence**: OB + trend alignment + key level
3. **Medium confluence**: FVG + trend alignment
4. **Low confluence**: Single factor (OB only, FVG only)

Always note contradictions:
- If OB is bullish but trend is bearish → lower probability
- If FVG is in premium zone during bearish trend → short setup, not long
- If EQH exists above with bearish trend → expect sweep then continuation down

---

## Timeframe Hierarchy

- **HTF (4H, D, W)**: Determines the overall bias and key levels
- **MTF (1H)**: Confirms the direction and identifies entry zones
- **LTF (5m, 15m)**: Precise entry timing and structure shifts

When analyzing:
1. Start with HTF to determine bias
2. Move to MTF to find confluent zones
3. Drop to LTF for entry triggers (CHoCH, BOS at key levels)

---

## API Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `trend_bias` | string | "bullish" or "bearish" |
| `swing_high` | float | Current range high |
| `swing_low` | float | Current range low |
| `strong_high` | float | High protected by trend |
| `strong_low` | float | Low protected by trend |
| `weak_high` | float | High targeted by trend |
| `weak_low` | float | Low targeted by trend |
| `structures[]` | array | BOS/CHoCH with type, bias, level, start/end times |
| `order_blocks[]` | array | Active OBs with high, low, bias, timestamp |
| `fair_value_gaps[]` | array | Active FVGs with top, bottom, mid, bias |
| `equal_levels[]` | array | EQH/EQL with level, type, connecting timestamps |
