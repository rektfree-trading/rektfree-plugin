---
name: killzone
description: >-
  Trading session & ICT killzone timing. Use whenever the user asks what session
  it is, whether a killzone is active, how much time is left in the session/
  killzone, when the next killzone or session opens, or whether now is good timing
  for an entry. Pairs with the `get_session_clock` MCP tool (pure UTC time — no
  symbol needed).
---

# Session & Killzone Timing

You are the analyst. The `get_session_clock` MCP tool (server `rektfree`) returns
the current UTC session, phase, the active/next killzone, and minutes remaining —
all from the clock, no market data. Your job is to turn that into a **timing
assessment**: the same setup has very different odds inside vs outside a killzone.

## Workflow

1. **Fetch.** Call `get_session_clock` (no arguments). It returns the current
   session (asia/london/new_york/post_ny) + phase, `next_session` + minutes, and
   the active or next killzone with minutes until/remaining.
2. **Assess** against [reference.md](reference.md): which session, is a killzone
   live, how much time is left, and what that session typically does.
3. **Advise on timing** — Optimal (inside a killzone), Acceptable, or Suboptimal
   (off-hours / between killzones) — and tie it to session dynamics (e.g. "London
   is live; watch for a sweep of the Asia range").

## Output shape

```
CURRENT SESSION
- Session: [Asia/London/New York/post-NY] — phase [early/mid/late]
- Killzone: [London Open / NY Open / Silver Bullet / none] — [active, Xm left / next in Xm]
- Next session: [name] in [Xh Ym]

TIMING ASSESSMENT
- [Optimal / Acceptable / Suboptimal] for new entries — [why]
- Session note: [what this session tends to do; what to watch]
```

## Guardrails

- **Always state the session AND whether a killzone is live.** Lead with timing.
- **Inside a killzone = optimal entry window** (London Open and NY Open are the
  two primary ones; the Silver Bullet hours are the highest-precision sub-windows).
  Combine with an SMC trigger (CHoCH + OB) at a key level.
- **Outside a killzone**, setups are still valid but lower-probability — consider
  waiting for the next window unless the setup is exceptionally strong.
- **Factor the remaining time** — "5 min left in London KZ" is very different from
  "just entered NY KZ".
- **Crypto trades 24/7**, but these session/killzone tendencies still frame the
  day; off-hours (post-NY) is the weakest window for new entries.

See [reference.md](reference.md) for full session characteristics and killzone
rules.
