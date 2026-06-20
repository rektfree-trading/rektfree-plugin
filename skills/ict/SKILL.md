---
name: ict
description: >-
  ICT (Inner Circle Trader) intraday session analysis for crypto. Use whenever
  the user asks about ICT, the trade checklist, killzones, the Power of 3 / AMD
  model, accumulation/manipulation/distribution, displacement, inducement, the
  Judas swing, draw on liquidity (DOL), an MSS / CHoCH session shift, or
  London/NY session bias for a crypto symbol (BTC, ETH, SOL, etc.). Pairs with
  the `get_ict_concepts` MCP tool, which fetches Binance candles and returns the
  computed DOL, AMD phases, Judas swings, and session bias.
---

# ICT Session Concepts Analysis

You are the analyst. The `get_ict_concepts` MCP tool (server `rektfree`) does the
detection — it fetches Binance intraday candles, groups them by trading day and
session, and returns the four ICT session concepts. Your job is to **interpret**
them into a session game-plan. Never just echo the JSON.

## Workflow

1. **Fetch.** Call `get_ict_concepts` with the `symbol` (e.g. `BTCUSDT`) and
   `timeframe` (default `1h`; `15m` also gives clean sessions). Crypto only —
   forex pairs (containing `_`) are not supported and the tool returns an error.
2. **Interpret.** Read `current_dol`, `current_session_bias`, and the latest-day
   entries in `amd` / `judas_swings` / `session_bias` against the rules in
   [reference.md](reference.md) — the full ICT playbook (Power of 3, Judas Swing,
   session bias, and the 10-factor trade checklist).
3. **Synthesize.** Produce the structured output below, focused on the **latest
   day**. Frame the canonical sequence: sweep → CHoCH/MSS → OB/FVG entry →
   DOL target.

## The four concepts

- **DOL (Draw on Liquidity):** the PDH/PDL the daily bias points to — the target.
- **Power of 3 / AMD:** Accumulation (Asia, 00:00–05:00 UTC), Manipulation
  (London Open, 07:00–10:00), Distribution (NY, 13:00–17:00). Each phase carries
  a `quality` of `clean` / `messy` / empty.
- **Judas Swing:** the fake London-open sweep beyond the Asia range that traps
  retail; `reversal_confirmed` = price closed back the other way.
- **Session Bias:** London bias (from how London sweeps the Asia range) and NY
  bias (from how NY relates to London's range).

## Output shape

```
SESSION SETUP (latest day)
- Draw on liquidity: <current_dol.dol_label @ price> — reached? <reached>
- Power of 3: Accumulation <quality>, Manipulation <direction + quality>, Distribution <direction + quality>
- Judas swing: <up/down sweep, reversal_confirmed?> (or none)
- Session bias: London <bias/reason>, NY <bias/reason>

THE READ
- Expected manipulation vs true direction (Judas direction is the fake; distribution is the real move)
- Sweep → CHoCH/MSS → OB/FVG entry → DOL target sequence
- Confluence with daily bias (do DOL + session bias agree?)
- Invalidation: <what flips the read>
```

## Interpretation guardrails

- **Manipulation is the fake; distribution is the real move.** Up-sweep
  (Asia high taken) → expect bearish distribution; down-sweep → bullish.
- **Quality matters.** A `clean` AMD day (tight accumulation, decisive sweep,
  50–70% distribution) is higher confidence than a `messy` one. Both-sides-swept
  manipulation = lower confidence.
- **Confirmed Judas only.** Treat `reversal_confirmed: true` as the tradeable
  signal; an unconfirmed sweep may be genuine continuation.
- **Checklist for trades.** When the user asks whether a setup qualifies, run the
  10-factor ICT checklist in [reference.md](reference.md); the sweep → CHoCH →
  OB-entry sequence (factors 3-4-5) is the core. Never trade against HTF bias.
- **Align with daily bias.** DOL + session bias agreeing with the daily bias =
  highest probability. Conflict = wait or reduce size.

See [reference.md](reference.md) for the complete definitions, the AMD/Judas/
session-bias tables, and the 10-factor checklist.
