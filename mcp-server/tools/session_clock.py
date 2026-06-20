"""
``get_session_clock`` — pure UTC session/killzone clock (no network, symbol-agnostic).

Maps the current UTC time onto the trading day the desk frames everything
around: which session is live (Asia/London/New York/post-NY), how far into it
we are, what comes next, and whether an ICT killzone is active or imminent.
This is the *timing* layer the brief and synthesis skills lean on — the same
setup has very different odds inside vs. outside a killzone, so the host model
needs an exact, offline clock it can trust.

No candles, no Binance, no symbol. Just ``datetime.now(timezone.utc)`` and the
session/killzone window math vendored verbatim from the backend so the plugin
reports the same windows as the hosted product.

Session windows (UTC), from the backend (Asia 00:00–08:00, London 08:00–13:00,
New York 13:00–21:00); 21:00–24:00 is the post-NY / Asia-pre-open lull.
Killzone windows are vendored from ``confluence_scanner.KILLZONES`` /
``SILVER_BULLETS``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# --- Session windows (UTC hours) — exact from the backend (CLAUDE.md rule #7) --
# (start_hour, end_hour, key, label). end is exclusive. Order = chronological.
SESSIONS = [
    (0, 8, "asia", "Asia"),
    (8, 13, "london", "London"),
    (13, 21, "new_york", "New York"),
    (21, 24, "post_ny", "Post-NY / Asia pre-open"),
]

# --- Killzone windows (UTC hours) — vendored from confluence_scanner.py ---------
# KILLZONES: the two primary ICT entry windows.
KILLZONES = [
    (7, 9, "London Open"),
    (12, 14, "NY Open"),
]
# SILVER_BULLETS: the highest-precision sub-windows (a subset/refinement).
SILVER_BULLETS = [
    (7, 8, "London Silver Bullet"),
    (14, 15, "NY AM Silver Bullet"),
    (18, 19, "NY PM Silver Bullet"),
]

# All killzone-class windows, chronological — what the clock reports as the
# "active or next" killzone. Each is (start_hour, end_hour, name).
ALL_KILLZONES = sorted(KILLZONES + SILVER_BULLETS, key=lambda w: (w[0], w[1]))

# Short, session-specific tendencies (from the backend ict_session/killzone docs).
SESSION_NOTES = {
    "asia": [
        "Asia is the lowest-volatility session — it builds the day's initial range.",
        "Mark the Asia high/low: London typically acts on this range.",
        "Range/accumulation phase (ICT Power-of-3 'A') — usually no clean trend.",
    ],
    "london": [
        "London often sweeps the Asia range before trending (the Judas Swing).",
        "Highest volatility / institutional volume — the day's directional session.",
        "London Open killzone (07:00–09:00 UTC) is the #1 ICT entry window.",
    ],
    "new_york": [
        "NY continues or reverses London — watch the London high/low for the sweep.",
        "NY Open killzone (12:00–14:00 UTC) is the second-best entry window.",
        "London/NY overlap (12:00–13:00 UTC) is the highest-volume hour of the day.",
    ],
    "post_ny": [
        "Post-NY (21:00–24:00 UTC) is a low-volume lull — let trades run, avoid new entries.",
        "Crypto still moves but with thin institutional participation.",
        "This rolls into the next Asia accumulation — start framing tomorrow's range.",
    ],
}


def _classify_session(dt: datetime) -> tuple[str, str, datetime, datetime]:
    """Return (key, label, start_dt, end_dt) for the session ``dt`` falls in.

    Window math is hour-based on the UTC clock and is closed-open on the hour
    boundaries (e.g. 08:00 is London, not Asia). ``end_dt`` may land on the next
    calendar day (post-NY ends at the following 00:00).
    """
    hour = dt.hour
    day0 = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    for start, end, key, label in SESSIONS:
        if start <= hour < end:
            start_dt = day0 + timedelta(hours=start)
            end_dt = day0 + timedelta(hours=end)  # end==24 -> next midnight, correct
            return key, label, start_dt, end_dt
    # Unreachable: SESSIONS cover 0..24 contiguously.
    raise ValueError(f"hour {hour} not covered by SESSIONS")


def _phase(minutes_into: float, total_minutes: float) -> str:
    """Early/mid/late by elapsed fraction of the session (thirds)."""
    if total_minutes <= 0:
        return "early"
    frac = minutes_into / total_minutes
    if frac < 1 / 3:
        return "early"
    if frac < 2 / 3:
        return "mid"
    return "late"


def _next_session(current_key: str) -> tuple[str, str]:
    """Return (next_key, next_label) for the session chronologically after current.

    Wraps post_ny -> asia. The next session starts exactly when the current one
    ends, so the caller derives ``minutes_until`` from the current session's end.
    """
    keys = [s[2] for s in SESSIONS]
    idx = keys.index(current_key)
    nxt = SESSIONS[(idx + 1) % len(SESSIONS)]
    return nxt[2], nxt[3]


def _killzone_status(dt: datetime) -> dict:
    """Return the active killzone, or the next upcoming one, relative to ``dt``.

    Searches today's and (for late-day) tomorrow's windows so a 22:00 UTC call
    correctly points at tomorrow's 07:00 London Open killzone rather than going
    negative.
    """
    day0 = dt.replace(hour=0, minute=0, second=0, microsecond=0)

    # 1) Active right now?
    for start, end, name in ALL_KILLZONES:
        s = day0 + timedelta(hours=start)
        e = day0 + timedelta(hours=end)
        if s <= dt < e:
            return {
                "name": name,
                "active": True,
                "minutes_until": 0,
                "minutes_remaining": int(round((e - dt).total_seconds() / 60)),
            }

    # 2) Otherwise the next one — scan today then tomorrow for the soonest start > now.
    candidates: list[tuple[datetime, str]] = []
    for offset_days in (0, 1):
        base = day0 + timedelta(days=offset_days)
        for start, _end, name in ALL_KILLZONES:
            s = base + timedelta(hours=start)
            if s > dt:
                candidates.append((s, name))
    nxt_start, nxt_name = min(candidates, key=lambda c: c[0])
    return {
        "name": nxt_name,
        "active": False,
        "minutes_until": int(round((nxt_start - dt).total_seconds() / 60)),
        "minutes_remaining": 0,
    }


def _build_clock(now: datetime) -> dict:
    """Pure classifier over a UTC datetime — the testable core of the tool."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    key, label, start_dt, end_dt = _classify_session(now)
    total_minutes = (end_dt - start_dt).total_seconds() / 60
    minutes_into = (now - start_dt).total_seconds() / 60
    minutes_until_next = int(round((end_dt - now).total_seconds() / 60))

    nxt_key, nxt_label = _next_session(key)
    kz = _killzone_status(now)

    return {
        "utc_time": now.isoformat(),
        "weekday": now.strftime("%A"),
        "session": key,
        "session_label": label,
        "phase": _phase(minutes_into, total_minutes),
        "minutes_into_session": int(round(minutes_into)),
        "session_window_utc": f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}",
        "next_session": nxt_key,
        "next_session_label": nxt_label,
        "minutes_until_next_session": minutes_until_next,
        "killzone": kz,
        "notes": SESSION_NOTES.get(key, []),
    }


def register(mcp) -> None:
    @mcp.tool()
    async def get_session_clock() -> dict:
        """Where are we in the trading day? Pure UTC session + killzone clock.

        Takes no arguments and touches no network. Reads ``datetime.now(utc)``
        and maps it onto the desk's trading-day structure so the host model can
        time entries and frame a pre-session brief without guessing the clock.

        Sessions (UTC): Asia 00:00–08:00, London 08:00–13:00, New York
        13:00–21:00, post-NY 21:00–24:00 (the low-volume Asia-pre-open lull).
        Killzones are vendored from the backend scanner: London Open
        (07:00–09:00) and NY Open (12:00–14:00), plus the silver-bullet
        sub-windows (London 07:00–08:00, NY AM 14:00–15:00, NY PM 18:00–19:00).

        Returns:
            A dict with the current ``utc_time`` (ISO) and ``weekday``; the live
            ``session`` (``asia``/``london``/``new_york``/``post_ny``) with its
            ``phase`` (``early``/``mid``/``late`` by elapsed fraction),
            ``minutes_into_session`` and ``session_window_utc``; the
            ``next_session`` and ``minutes_until_next_session``; a ``killzone``
            object (the active one, or the next upcoming, with ``name``,
            ``active`` bool, ``minutes_until``, ``minutes_remaining``); and a
            short ``notes`` list of this session's tendencies for the model to
            weave into the read.
        """
        return _build_clock(datetime.now(timezone.utc))


# --- Offline self-test: boundary correctness across midnight/day rollover ------
def _self_test() -> None:
    """Feed fixed UTC datetimes through the classifier to prove boundaries."""
    base = datetime(2026, 6, 20, tzinfo=timezone.utc)  # a Saturday

    def at(h: int, m: int = 0) -> dict:
        return _build_clock(base.replace(hour=h, minute=m))

    # Session classification at representative times.
    assert at(2)["session"] == "asia", at(2)["session"]
    assert at(9, 30)["session"] == "london", at(9, 30)["session"]
    assert at(13, 30)["session"] == "new_york", at(13, 30)["session"]
    assert at(22)["session"] == "post_ny", at(22)["session"]

    # Boundary edges are closed-open on the hour.
    assert at(8, 0)["session"] == "london"
    assert at(13, 0)["session"] == "new_york"
    assert at(21, 0)["session"] == "post_ny"
    assert at(0, 0)["session"] == "asia"

    # Phase: 09:30 is 90 min into a 300-min London (early, <1/3=100min).
    assert at(9, 30)["phase"] == "early", at(9, 30)["phase"]
    # 11:00 is 180/300 = late (>=2/3=200? no -> mid). Check mid.
    assert at(11, 0)["phase"] == "mid", at(11, 0)["phase"]
    assert at(12, 30)["phase"] == "late", at(12, 30)["phase"]

    # Killzone: 07:30 is inside London Open AND London Silver Bullet (07-08).
    # Earliest-by-start tie-break — both start at 07, SB ends 08, KZ ends 09.
    kz0730 = at(7, 30)["killzone"]
    assert kz0730["active"] is True, kz0730
    # 13:30 NY sits *inside* the NY Open killzone (12:00–14:00) -> active.
    kz1330 = at(13, 30)["killzone"]
    assert kz1330["active"] is True and kz1330["name"] == "NY Open", kz1330
    assert kz1330["minutes_remaining"] == 30, kz1330
    # 15:30 NY is *between* killzones: next is NY PM SB at 18:00 (150 min away).
    kz1530 = at(15, 30)["killzone"]
    assert kz1530["active"] is False and kz1530["minutes_until"] == 150, kz1530
    assert kz1530["name"] == "NY PM Silver Bullet", kz1530

    # Day-rollover: at 22:00 the next killzone is tomorrow's first (07:00).
    kz22 = at(22)["killzone"]
    assert kz22["active"] is False, kz22
    # 22:00 -> next 07:00 London SB (07-08) tomorrow = 9h = 540 min.
    assert kz22["minutes_until"] == 540, kz22["minutes_until"]
    assert "London" in kz22["name"], kz22

    # Next-session + minutes never negative.
    for h in range(0, 24):
        c = at(h)
        assert c["minutes_into_session"] >= 0, (h, c)
        assert c["minutes_until_next_session"] >= 0, (h, c)
        assert c["killzone"]["minutes_until"] >= 0, (h, c)
    # post_ny -> asia wraps correctly.
    assert at(22)["next_session"] == "asia", at(22)
    assert at(2)["next_session"] == "london"


if __name__ == "__main__":
    _self_test()
    import json

    print("self-test OK")
    print(json.dumps(_build_clock(datetime.now(timezone.utc)), indent=2))
