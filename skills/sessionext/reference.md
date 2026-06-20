# Session-Extension — Reference Playbook

This skill measures **range expansion across sessions**: how often and how far
each trading session (London, NY) pushes BEYOND the prior intraday session's
range, plus each session's own range distribution, the long/short day split, and
HOD/LOD potential. It grounds "how far does it run?" in what has actually
happened for a crypto asset over the sampled window rather than generic theory.

## Tool payload

`compute_session_extension_stats` returns:

```
{
  "symbol": "BTCUSDT",
  "window": { "candles", "from", "to", "days", "usable_days", "note" },
  "extensions": {
    "london":   { "n", "vs_prior_session": "asia",   "extension_rate",
                  "only_h_pct", "only_l_pct", "both_pct", "neither_pct",
                  "h_then_l_pct", "l_then_h_pct",
                  "avg_overshoot", "avg_overshoot_multiple", "overshoot_sample" },
    "new_york": { "n", "vs_prior_session": "london",  ... }
  },
  "session_range": { "asia": { "n", "range": {...}, "range_pct": {...} }, ... },
  "daily_direction": { "n", "long_day_pct", "short_day_pct",
                       "avg_up_leg", "avg_down_leg" },
  "hod_lod": { "n", "sessions": { "asia": { "n", "hod_pct", "lod_pct" }, ... } }
}
```

All session times are UTC: **Asia 00:00–08:00**, **London 08:00–13:00**,
**New York 13:00–21:00**. Asia has no intraday predecessor, so it has no
extension block (it's the day's opening range).

### Sample window — read this first

`window.days` is the **live sample length** (default ~90 days) and each block's
`n` is its own denominator. The hosted product aggregates over FULL history, so
its dashboard rates will differ from this snapshot. Always cite `n` and treat
thin samples (e.g. fewer than ~30 days) with caution.

---

## Concepts & Definitions

### 1. Session extension (the core metric)

A session **extends** when its 1H candles trade beyond the PRIOR intraday
session's high or low:
- **London** is measured vs **Asia** (Asia is the opening range).
- **New York** is measured vs **London**.

For each day we walk the session's candles and record the FIRST break of the
prior high and the FIRST break of the prior low, giving a grid cell:
- `only_h` — broke the prior high only.
- `only_l` — broke the prior low only.
- `both` — broke both (with ordering `h_then_l` or `l_then_h`).
- `neither` — stayed inside the prior session's range.

`extension_rate` = `(only_h + only_l + both) / n` — how often the session broke
the prior range at all.

### 2. Overshoot

How FAR the session pushed beyond the prior extreme:
- `avg_overshoot` — average overshoot distance in quote units (USDT), over the
  days an extension occurred (`overshoot_sample`).
- `avg_overshoot_multiple` — that overshoot as a multiple of the PRIOR session's
  range. A 1.0× means the session ran an extra full prior-range beyond the
  break; 0.2× means a shallow probe.

### 3. Session range distribution

Each session's own H−L, distributed (median / mean / min / max / p25 / p75) in
both raw quote units (`range`) and percent (`range_pct`). Use `range_pct` to
compare across assets/price regimes; the p25–p75 spread shows typical vs outlier
expansion.

### 4. Daily direction

For each day: `day_open` = Asia open (fallback earliest session), `day_high` =
max session high, `day_low` = min session low. `up_leg = day_high − day_open`,
`down_leg = day_open − day_low`. **long** if `up_leg ≥ down_leg`, else **short**.
This is the canonical definition used across the views.

### 5. HOD / LOD potential

Per session, the probability it prints the day's high (`hod_pct`) or low
(`lod_pct`), over the days that session was present. Tells you which session
tends to set the day's extremes.

---

## How to Interpret the Rates

### Extension edge
- **High NY extension of London** = London's range rarely caps the day → plan
  for NY expansion, don't anchor targets to London's range.
- **Side skew** (`only_h` vs `only_l`) reveals directional bias: more high-side
  extensions → bullish expansion lean; more low-side → bearish.
- **`both` with an ordering skew** (e.g. `l_then_h`) often signals a sweep-then-
  reverse sequence (low taken first, then expansion up).
- **High `neither_pct`** = the session respects the prior range → trade the prior
  session's H/L as support/resistance rather than expecting a break.

### Overshoot
- Read `extension_rate` and `avg_overshoot_multiple` TOGETHER. High rate + small
  multiple = frequent shallow probes (the break often fails to run). Low rate +
  large multiple = rare but violent expansion. The tradeable size is the
  multiple.

### Range distribution
- Lead with median `range_pct` per session (typical day) and the p25–p75 spread
  (how often it runs wide). NY is usually the widest in crypto; Asia the
  tightest.

### Day direction & HOD/LOD
- The long/short split is the net directional lean over the sample.
- HOD/LOD potential tells you which session to watch for the day's extreme — if
  NY prints the LOD most often, the day's low is frequently a late-session event.

---

## How to Use in Analysis

1. **When the user asks "how far does it run?"** lead with the extension rate AND
   overshoot multiple for the relevant session, not just one.
2. **When planning targets**, use the prior session's range × the overshoot
   multiple as a realistic expansion estimate, and the session `range_pct`
   distribution for a typical-day envelope.
3. **When calling S/R**, cite `neither_pct` — a high value means the prior
   session's H/L holds and is tradeable as a level.
4. **Always state the sample window** and remind the user this is a recent live
   snapshot, not the full-history dashboard figure.

Cite specific numbers. "NY extends London 97% of days and overshoots ~1.2×
London's range on BTCUSDT over the last 60 days" is far more useful than "NY
usually expands."
