# Opening Range Breakout (ORB) — Reference Playbook

This skill analyzes the **Opening Range Breakout (ORB)** — the high/low of the
first `orb_minutes` (default 15) of the regular trading session, and what price
does with that range for the rest of the session. The `compute_orb_stats` MCP
tool fetches deep 5m history, computes per-day ORB events, and aggregates them.

## Definitions

- **Opening range (ORB):** the high and low of the first `orb_minutes` of the
  RTH session. For `synthetic_ny` / `nyse` the session opens 13:30 UTC, so a
  15-minute ORB is 13:30-13:45 UTC. Regional indices use their own opens
  (frankfurt 07:00, london 08:00, tokyo 00:00 UTC).
- **Post-ORB window:** from ORB-end through RTH-end (e.g. 13:45-20:00 UTC for
  synthetic_ny). All break/extension detection happens here.
- **First break side:** the first post-ORB candle whose high crosses the ORB
  high (`high`) or whose low crosses the ORB low (`low`). A candle that straddles
  both in the same bar defaults to `high` (deterministic, matches production —
  5m candles have no sub-candle ordering).
- **Outcome (mutually exclusive):**
  - `only_h` — only the high broke,
  - `only_l` — only the low broke,
  - `both` — both sides broke (= `two_side_broken`),
  - `neither` — price stayed inside the range all session (ORB held).
- **Breakout rate** = 1 − neither. **ORB-hold rate** = neither.
- **Extensions:** `orb_up_extension` = post-ORB high − ORB high (≥0);
  `orb_down_extension` = ORB low − post-ORB low (≥0). The **range-relative**
  variants divide by `orb_size` so they compare across price regimes.

## Synthetic open for crypto

Crypto trades 24/7, so there is no real cash open. The convention pins a
synthetic RTH to the US equities open (13:30-20:00 UTC) where crypto volume
concentrates. Treat crypto ORB rates as suggestive; the edge is cleaner on
forex/indices that have a true opening auction.

## How to read each block

- **`breakout_rate` vs `orb_hold_rate`:** a high breakout rate with large
  extension multiples is a trend-prone open — the breakout is tradeable. A high
  hold rate flags range/chop days where breakout entries get faded.
- **`first_break_side` skew:** a persistent lean (e.g. low-first) is a directional
  tell — BUT cross-check `two_side_pct`. A high two-side rate means the first
  break is often a stop-run that reverses; the *second* side is the real move.
- **`avg_first_break_time`:** early breaks (soon after the open) trend further;
  late breaks are often exhaustion.
- **Extension multiples:** `orb_*_extension_x_size` < 1 means price barely clears
  the range (chop, fade the edges); > 2 means breaks run far (momentum, trade the
  break with the opposite edge as the stop).
- **Day-of-week:** look for a standout `both_pct` (whippy days) or `neither_pct`
  (range days) by weekday.

## Sample-size discipline

- `confidence`: `high` (≥100), `normal` (≥30), `low` (≥10), `insufficient` (<10).
- These are a **recent live sample**, not the hosted dashboard's full history.
  Always cite `window.orb_days` and discount thin samples.
