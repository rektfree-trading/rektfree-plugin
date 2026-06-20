# Multi-Timeframe Analysis — Reference Playbook

Provides higher-timeframe structural context so you can align lower-timeframe
entries with the dominant trend. Built by running `analyze_smc` on 4H + Daily (in
addition to the entry timeframe) and comparing trend bias, key structures, and
active zones.

---

## Timeframe Hierarchy

### Daily (D1) — Strategic Direction
- Sets the weekly/monthly directional bias.
- BOS on Daily = strong trend confirmation.
- CHoCH on Daily = potential major reversal — high significance.
- OBs on Daily = institutional entry zones, very high hold rate.
- Use for: overall bias, no-trade zones, major targets.

### 4-Hour (4H) — Tactical Bias
- Confirms or conflicts with Daily direction.
- 4H BOS in the same direction as Daily = strong alignment, trade aggressively.
- 4H CHoCH against Daily = possible pullback or reversal starting.
- OBs on 4H = key entry zones for swing trades.
- Use for: directional bias, entry-zone identification, target setting.

### 1-Hour (1H) — Execution Timeframe
- Standard execution timeframe for most setups.
- Structures here should align with 4H for high-confidence entries.
- Use for: precise entry timing, stop placement, intraday targets.

### 15m / 5m — Precision Entry
- Used only after HTF bias is established.
- Look for CHoCH + OB entry on the LTF at an HTF key level.
- Use for: sniper entries, tight stops, scalp targets.

---

## Alignment Rules

### Full Alignment (highest confidence)
- Daily bullish + 4H bullish + 1H bullish = strong long bias.
- All timeframes agree → trade with trend, enter on pullbacks.

### Partial Alignment (moderate confidence)
- Daily bullish + 4H bullish + 1H bearish = a 1H pullback in an uptrend.
- Wait for 1H to realign (CHoCH back to bullish) before entering.

### Conflict (low confidence / counter-trend)
- Daily bullish + 4H bearish = a 4H correction underway.
- Trade cautiously or wait for 4H to realign.
- Only take counter-trend trades at major HTF levels with tight stops.

### Divergence Signals
- 4H makes a new high but 1H prints a CHoCH = potential distribution.
- Daily trend strong but 4H shows exhaustion (small-body candles at an extreme) =
  possible reversal.

---

## How to Use

1. Always state the HTF bias first, before any LTF analysis.
2. If HTF and LTF conflict, explain the conflict and its implications.
3. Use HTF OBs/FVGs as target zones for LTF entries.
4. HTF structure breaks override LTF signals.
5. Note when HTF data is unavailable or has too few candles for a reliable read.

---

## Output Format

```
MULTI-TIMEFRAME STRUCTURE:
  Daily: [Bullish/Bearish] — last BOS/CHoCH at [price]
    Key OB: [range] | Key FVG: [range]
  4H: [Bullish/Bearish] — last BOS/CHoCH at [price]
    Key OB: [range] | Key FVG: [range]
  Current TF: [alignment status with HTF]

ALIGNMENT: [Full/Partial/Conflict]
IMPLICATION: [trade direction + confidence adjustment]
```
