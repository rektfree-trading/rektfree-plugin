---
name: ethprofile
description: >-
  ETH Profile / previous-day value-area statistics. Use whenever the user asks
  how often price revisits or touches yesterday's POC / VAH / VAL, prior-day
  value area, previous value-area high/low, naked POC, profile-level magnets, or
  the next-day touch rate of the prior session's market profile, for any symbol
  (crypto BTC/ETH/SOL, or forex/indices like EUR_USD, NAS100_USD, XAU_USD).
  Pairs with the `compute_eth_profile_stats` MCP tool, which builds a daily
  RTH-bounded TPO profile and measures prior-day-level touch frequencies.
---

# ETH Profile / Previous-Day Value-Area Statistics

You are the analyst. The `compute_eth_profile_stats` MCP tool (server `rektfree`)
does the computation — it fetches deep 15m + 1H history, builds an RTH-bounded
**TPO profile** per day (POC / VAH / VAL), then walks the NEXT day to measure how
often price **touches the prior day's** POC / VAH / VAL and when. Your job is to
**interpret** these into a clear, decision-oriented read. Never just echo numbers.

## Workflow

1. **Fetch.** Call `compute_eth_profile_stats` with the `symbol`, and `days` if
   named. Crypto needs no key; forex/indices (underscore symbols) need
   `RF_OANDA_TOKEN`. This is the heaviest stats tool (a profile per day), so
   `days` defaults to 90 and is capped at 150.
2. **Interpret.** Read the payload against the rules in
   [reference.md](reference.md) — what high prior-level touch rates imply, how to
   read touch times, and how the RTH-range distribution frames stops/targets.
3. **Synthesize.** Produce the structured output below. Lead with the strongest
   magnet (the highest prior-level touch rate).

## Synthetic-window caveat (state this for crypto)

For 24/7 crypto the RTH window is a **synthetic** convention (13:30-20:00 UTC,
US equities session). The edge is most meaningful on **forex/indices** with a
real cash session. Compute it for crypto, but flag the caveat.

## Sample-window caveat (state this every time)

The tool samples only the **last ~N days** it fetches live
(`window.profile_days`, `touch.n`), NOT the full history the hosted dashboard
aggregates. Cite the sample size and treat it as a recent snapshot. Note
`touch.tpo_quality_normal_pct`: low-TPO days produce coarser profiles.

## Payload key

- `window.rth_window_utc` — the RTH window (e.g. `13:30-20:00`);
  `window.profile_days` — days with a valid profile; `window.rth_convention`.
- `touch` — `prev_poc_pct` / `prev_vah_pct` / `prev_val_pct` (how often the next
  day touched each prior-day level), `avg_prev_poc_touch_time` /
  `avg_prev_vah_touch_time` / `avg_prev_val_touch_time` (UTC HH:MM),
  `tpo_quality_normal_pct`, `n`, `confidence`.
- `extension` — `rth_extension` distribution (`median`/`mean`/`min`/`max`/`p25`/
  `p75` + `sample_size`/`confidence`) of the daily RTH range.
- `day_of_week.{Mon..Sun}` — per-weekday prior-level touch rates + `count`.

## Output shape

```
PRIOR-DAY VALUE-AREA MAGNETS
- Prev POC touched X% / VAH Y% / VAL Z% — strongest magnet first
- Avg touch times (early vs late in the RTH session)

RTH RANGE
- Typical daily RTH range (median, p25–p75) → stop/target framing

DAY-OF-WEEK EDGE
- Standout high/low touch-rate days

IMPLICATION
- Lean toward fading to the strongest prior level, with timing + range context

SAMPLE: window.profile_days days, n=N — recent snapshot, not full history
```

## Interpretation guardrails

- **High prior-POC touch rate = strong magnet.** If price tags yesterday's POC on
  most days, lean toward mean-reversion targets there; a *naked* prior POC (one
  not yet touched intraday) is the highest-probability draw.
- **VAH/VAL touch rates frame the edges.** High VAH/VAL touch rates mean the prior
  value area still governs — fade toward it from outside, expect rejection at it
  from inside.
- **Touch time matters.** Early-session touches (soon after the open) suit a
  morning fade; late touches suit holding for an end-of-session revisit.
- **`rth_extension` sizes the trade.** A wide median RTH range implies wider stops
  and further targets; a tight range warns of chop.
- **Discount low-TPO days.** A low `tpo_quality_normal_pct` means many days had
  thin profiles — the POC/VAH/VAL are noisier, so weight confidence down.
- **Crypto = synthetic window.** The edge is cleaner on a real-cash forex/index
  session.
- **Anchor to sample size.** An 85% touch rate off 6 days is noise.

See [reference.md](reference.md) for the complete definitions and rules.
