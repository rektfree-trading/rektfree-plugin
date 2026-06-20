# ETH Profile / Previous-Day Value-Area — Reference Playbook

This skill analyzes how reliably yesterday's **market-profile value area**
(POC / VAH / VAL) is revisited the next day — a mean-reversion / magnet edge. The
`compute_eth_profile_stats` MCP tool builds a daily RTH-bounded TPO profile,
captures each day's POC/VAH/VAL, then walks the next day to detect touches.

## Definitions

- **TPO profile:** a Time-Price-Opportunity profile of the RTH session. The price
  range is split into auto-sized buckets; each candle adds a TPO to every bucket
  it spans. This reuses the same Market Profile engine as `get_market_profile`.
- **POC (Point of Control):** the price bucket with the most TPOs — the session's
  fairest / most-accepted price.
- **Value Area (VAH/VAL):** the contiguous band around POC holding ~68.26% of
  TPOs. VAH = value-area high, VAL = value-area low.
- **RTH window:** the regular-trading-hours window per the symbol's convention
  (synthetic_ny / nyse = 13:30-20:00 UTC; frankfurt/london/tokyo differ). For
  24/7 crypto this is a **synthetic** window pinned to the US equities session.
- **Prior-day touch:** the next day's intraday 1H candles are walked in order; a
  level is "touched" the first time a candle's `[low, high]` contains the prior
  day's POC / VAH / VAL. The touch time is that candle's HH:MM UTC.
- **Chronological chaining:** days are processed oldest→newest. Each day's profile
  becomes the *next* day's `prev_*` levels. The first day has `prev_*=null` and no
  touches (it still counts toward the denominator, matching the backend).

## Why this is an edge

Yesterday's value area marks where the market last agreed on price. Markets
routinely return to retest accepted value — a high prior-POC touch rate means the
POC acts as a magnet, so a level not yet revisited intraday (a *naked* POC) is a
high-probability draw. VAH/VAL touch rates show whether the prior value area's
edges still act as support/resistance.

## How to read each block

- **`prev_poc_pct` / `prev_vah_pct` / `prev_val_pct`:** the magnet strength of each
  prior level. Rank them; the highest is the primary target. POC usually leads.
- **`avg_prev_*_touch_time`:** when the revisit typically lands. Early touches suit
  a morning fade; late touches suit holding for an end-of-day return.
- **`tpo_quality_normal_pct`:** the share of days whose profile had enough TPOs to
  be reliable (`tpo_sample_label` ≠ `insufficient`). Low here = noisier levels.
- **`rth_extension`:** the daily RTH-range distribution — use the median and p25–p75
  to size stops and targets relative to a normal day.
- **`day_of_week`:** look for weekdays with standout touch rates.

## This is the heaviest stats tool

A TPO profile is computed for **every day** in a chronological walk over 15m + 1H
history. Paging is bounded and `days` is capped at 150. As with all plugin stats
tools, accuracy scales with history depth.

## Sample-size discipline

- `confidence`: `high` (≥100), `normal` (≥30), `low` (≥10), `insufficient` (<10).
- These are a **recent live sample**, not the hosted dashboard's full history.
  Always cite `window.profile_days` / `touch.n` and discount thin samples.
