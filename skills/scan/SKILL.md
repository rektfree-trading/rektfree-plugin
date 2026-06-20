---
name: scan
description: >-
  Confluence setup scoring for crypto. Use whenever the user asks to "scan" a
  market, for a "confluence" read, a "setup score", "is there a setup", "grade
  this trade", "go/no-go", whether a setup qualifies, or how strong a setup is
  for a crypto symbol (BTC, ETH, SOL, etc.). Pairs with the `scan_confluence`
  MCP tool, which fetches Binance 1H+4H candles, runs SMC, and returns the
  numeric confluence score, factor breakdown, and structural target/invalidation.
---

# Confluence Setup Scan

You are the analyst. The `scan_confluence` MCP tool (server `rektfree`) does the
computation — it fetches Binance 1H + 4H candles, runs the SMC engine on each,
and stacks the signals into a single 0–N confluence score with the same point
weights as the hosted RektFree scanner. Your job is to **interpret** the score
into a clear go/no-go read. Never just echo the JSON.

## What this is (and is not)

This is a **deterministic structural confluence grade** — NOT the hosted
scanner's full signal. There is **NO AI** in the tool, and several DB-backed
inputs the hosted scanner uses are **neutralized** here:

- **Macro calendar** → no macro DB; treated as "no event" (the "No macro events"
  +1 always fires). Always remind the user the scan is blind to news risk —
  *they* must check the calendar before acting.
- **Avoid-signatures** → no `discovered_edges` DB; the hosted scanner's
  subtractive blocklist is skipped (it could only ever *remove* a signal).
- **Historical sweep-rate** → no session-events DB; that +1 never fires.
- **Order-flow delta / derivatives** → no footprint/derivatives DB; those
  factors never fire.
- **Daily SMC** → the plugin scans 1H + 4H only, so the "Daily bias" +1 and the
  daily leg of "Full MTF alignment" never fire.

So the score is a clean **structural ceiling** built from 1H + 4H SMC. Read the
factors as a checklist; you supply the narrative, the macro caveat, and the risk
read.

## Workflow

1. **Fetch.** Call `scan_confluence` with the `symbol` (e.g. `BTCUSDT`). Crypto
   only — forex pairs (containing `_`) return an error. No timeframe argument:
   the scan always pairs 1H entry structure with the 4H bias.
2. **Interpret.** Read the payload against the rules in
   [reference.md](reference.md) — the full confluence playbook (every factor,
   its weight, the threshold, counter-trend gating, target/invalidation).
3. **Synthesize.** Lead with the go/no-go verdict. A trader should be able to
   act on it, with risk clearly framed.

## Payload key

`scan_confluence` returns:

| Field | Meaning |
|---|---|
| `score` | The 0–N confluence score (structural only). |
| `min_score` | Hosted operating threshold (currently **6**). |
| `meets_threshold` | `true` only if `score ≥ min_score` **and** (if counter-trend) `score ≥ 8`. |
| `direction` | `long` or `short` — the scored trade direction. |
| `is_counter_trend` | `true` if the 1H trend disagrees with the HTF bias. Needs a higher bar. |
| `factors` | The labels that fired (same vocabulary as the hosted scanner). |
| `target` | Nearest structural level in the trade direction, capped to 2% (crypto). |
| `invalidation` | 1.5× ATR stop (fallback 1% if ATR unavailable). |
| `last_price`, `scored_at` | Entry reference + UTC timestamp. |

## The score, factor by factor (weights)

A setup only scores if a **bias-aligned order block sits within 0.5% of price**
— this is REQUIRED. No such OB ⇒ `score 0` and an empty `factors` list (the most
common outcome; price simply isn't in a setup right now). When the OB is present:

| Factor | Weight | Notes |
|---|---|---|
| Daily bias | +1 | NEUTRALIZED in plugin (no daily fetch) — never fires. |
| 4H confirms | +1 | 4H trend agrees with / sets the HTF bias. |
| **OB at price (required)** | **+2** | Bias-aligned order block within 0.5% of price. |
| FVG overlap | +1 | Aligned fair value gap within 0.5% of price. |
| OB in OTE zone | +1 | OB sits in the 0.618–0.786 retracement. |
| Sweep of liquidity | +2 | Recent same-direction liquidity grab. |
| MSS/CHoCH after sweep | **0** | Listed for context; anti-predictive (recalibrated to 0). |
| Draw on liquidity | +1 | Nearest unswept target within 5%. |
| Killzone | **0** | Listed for context; recalibrated to 0. |
| Silver Bullet | **0** | Listed for context; recalibrated to 0. |
| High sweep rate | +1 | NEUTRALIZED (no session DB) — never fires. |
| Deep premium/discount | +1 | >80% premium for shorts, <20% discount for longs. |
| No macro events | +1 | NEUTRALIZED to always-on (no macro DB). |
| Order flow confirms / diverges | +1 / −1 | NEUTRALIZED (no footprint) — never fires. |
| Derivatives confirm / oppose | +1 / −1 | NEUTRALIZED (no derivatives) — never fires. |
| Full MTF alignment (1H+4H+D) | +1 | Daily leg neutralized; rarely fires without it. |
| OB aligns with POC/VAH/VAL | +2 | TPO confluence — PURE, computed from candles. Active. |

## Interpretation guardrails

- **`min_score` is the line.** `score ≥ min_score` (6) = a qualifying structural
  setup. Below it = no setup; name what's missing.
- **Counter-trend needs more.** If `is_counter_trend` is `true`, the setup must
  reach **8** to qualify (the tool reflects this in `meets_threshold`). Flag the
  HTF disagreement explicitly.
- **Score 0 / empty factors is information.** It almost always means no order
  block is sitting at price. That's a "wait" — not a short or a failure.
- **Killzone / silver-bullet carry zero weight.** If you see them in `factors`,
  mention them as context only; they do NOT push the score.
- **Always state the macro caveat.** The scan can't see news. A high score into a
  red-folder event is still a high-risk trade.
- **Target & invalidation are structural, not gospel.** `target` is the nearest
  level within the 2% cap; `invalidation` is 1.5× ATR. Compute and report the
  implied R:R (the hosted scanner rejects < 1.5) so the user can judge it.

See [reference.md](reference.md) for the complete playbook and the philosophy
behind each weight.
