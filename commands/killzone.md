---
description: Current trading session & ICT killzone timing — which session is live, whether a killzone is active, and how long is left. Use to judge whether now is good timing for an entry.
argument-hint: (no arguments)
---

Report the current session and killzone status and turn it into an entry-timing
assessment.

Request: `$ARGUMENTS`

Steps:

1. Call the `get_session_clock` MCP tool (server: `rektfree`) — it needs no
   arguments and returns the current UTC session, phase, next session, and the
   active/next killzone with minutes remaining.
2. Interpret with the `killzone` skill: state the session and whether a killzone
   is live, how much time is left, and what this session typically does.
3. Give a timing verdict — Optimal / Acceptable / Suboptimal for new entries —
   with the reason (inside killzone, session overlap, off-hours, etc.).

If the user named a symbol, you may also note the relevant session level to watch
(e.g. the Asia high/low during London) — but the clock itself is symbol-agnostic.
