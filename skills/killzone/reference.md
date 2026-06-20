# Session & Killzone — Reference Playbook

Real-time awareness of which trading session is active, whether a killzone is in
play, and how much time remains — critical for entry timing. Sourced from the
`get_session_clock` tool (current UTC time mapped to session/killzone windows).

- **Sessions (UTC):** Asia 00:00–08:00, London 08:00–13:00, New York 13:00–21:00,
  post-NY 21:00–24:00.
- **Killzones (UTC):** London Open 07:00–09:00, NY Open 12:00–14:00.
- **Silver Bullet windows (UTC):** London 07:00–08:00, NY AM 14:00–15:00, NY PM
  18:00–19:00 — the highest-precision sub-windows.

---

## Session Characteristics

### Asia (00:00–08:00 UTC)
- Lowest volatility. Establishes the day's initial range.
- Best for: marking Asia H/L for later reference; spotting accumulation.
- Avoid: directional trades expecting large moves (absent a crypto catalyst).
- Typical behavior: range-bound, tight consolidation.

### London (08:00–13:00 UTC)
- Highest volatility and institutional volume.
- Best for: directional entries, especially after an Asia sweep.
- London Open KZ (07:00–09:00) is the #1 entry window for ICT/SMC traders.
- Typical behavior: sweep Asia H or L, then trend.

### New York (13:00–21:00 UTC)
- Second-highest volatility. Continues or reverses London.
- Best for: continuation trades, or reversals at London extremes.
- NY Open KZ (12:00–14:00) is the second-best entry window.
- Typical behavior: test London H/L, then decide direction.

### Off-Hours / post-NY (21:00–00:00 UTC)
- Very low volume. Crypto still moves but with less institutional participation.
- Best for: no new entries — let existing trades run.

---

## Killzone Rules

### Inside a killzone
- The optimal entry window; setups here have higher success rates.
- Combine with SMC structure (CHoCH + OB) at a key level.
- Confidence boost: roughly +1 tier when inside a killzone.

### Outside a killzone
- Setups still valid but lower-probability, potentially wider stops.
- Consider waiting for the next killzone unless the setup is exceptionally strong.
- Late London (10:00–13:00) is still tradeable but less ideal than the open.

### Session overlap (12:00–13:00 UTC)
- London and NY overlap — the highest-volume hour of the day.
- Can produce sharp moves and reversals; often the continuation/reversal
  confirmation of London's move.

---

## How to Use

1. Always state the current session and whether a killzone is active.
2. Inside a killzone: flag it as optimal timing for entries.
3. Between sessions: suggest waiting or note the reduced edge.
4. Factor remaining time — "5 min left in London KZ" vs "just entered NY KZ".
5. Relate to session dynamics — "We're in London, Asia high is at X — watch for a
   sweep."

---

## Output Format

```
CURRENT SESSION:
  Session: [Asia/London/New York/post-NY]
  Time: [HH:MM UTC] — [X hours Y min into session]
  Killzone: [London Open KZ / NY Open KZ / Silver Bullet / None]
  Remaining: [Xh Ym until session/killzone ends or next opens]

TIMING ASSESSMENT:
  [Optimal / Acceptable / Suboptimal] for new entries
  Reason: [inside killzone / session overlap / low-volume period / etc.]
```
