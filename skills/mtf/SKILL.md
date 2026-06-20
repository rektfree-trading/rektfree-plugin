---
name: mtf
description: >-
  Multi-timeframe (MTF) structural alignment for crypto. Use whenever the user
  asks about the higher-timeframe bias, "what's the HTF doing", aligning the
  timeframes, whether the daily/4H agrees with the entry timeframe, or whether a
  setup is with or against the higher trend (BTC, ETH, SOL, etc.). Runs the
  `analyze_smc` MCP tool on several timeframes and weighs their alignment.
---

# Multi-Timeframe (MTF) Alignment

You are the analyst. There is no dedicated MTF tool — you build the read by
calling `analyze_smc` (server `rektfree`) on **several timeframes** and comparing
their structure. The principle: **trade in the direction of the higher timeframe,
enter on the lower timeframe.**

## Workflow

1. **Fetch the stack.** Call `analyze_smc` on **Daily (`1d`)**, **4H (`4h`)**, and
   the user's **entry timeframe** (default `1h`, or `15m`/`5m` for precision).
   Run them together. If a higher timeframe returns too few candles, say so and
   weight it less.
2. **Read each level** against [reference.md](reference.md): Daily = strategic
   direction, 4H = tactical bias, 1H = execution, 15m/5m = precision entry. Note
   each timeframe's `trend_bias`, last BOS/CHoCH, and nearest unmitigated OB/FVG.
3. **Classify alignment** — Full (all agree), Partial (LTF pullback inside an HTF
   trend), or Conflict (HTF vs HTF disagree). State the HTF bias **first**, then
   how the lower timeframe sits within it.

## Output shape

```
MULTI-TIMEFRAME STRUCTURE
- Daily: [bullish/bearish] — last BOS/CHoCH @ [price]; key OB/FVG [range]
- 4H:    [bullish/bearish] — last BOS/CHoCH @ [price]; key OB/FVG [range]
- Entry TF ([1h/15m]): [aligned / pulling back / conflicting]

ALIGNMENT: [Full / Partial / Conflict]
IMPLICATION: [direction + confidence adjustment; where to enter; what invalidates]
```

## Guardrails

- **State HTF bias before any LTF read.** The higher timeframe frames everything.
- **HTF structure breaks override LTF signals.** A Daily CHoCH outweighs a 1H BOS.
- **Use HTF OBs/FVGs as LTF targets**, and as the zones where you wait for an LTF
  CHoCH+OB entry trigger.
- **Conflict = caution.** Daily-bull / 4H-bear means a 4H correction is underway —
  wait for realignment, or only take counter-trend at a major HTF level with a
  tight stop.
- **Flag divergences** (e.g. 4H makes a new high but 1H prints a CHoCH = possible
  distribution).

See [reference.md](reference.md) for the full timeframe hierarchy and alignment
rules.
