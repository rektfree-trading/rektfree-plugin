"""
Pure-Python Peak Points detectors (vendored from the backend).

DB-free port of the backend's ``app/services/peak_points_stats.py`` +
``app/routers/peak_points_stats.py``. The hosted product reads the per-day
``session_range`` rows out of ``session_events``, classifies which session
printed the day's HIGH (HOD) and which printed the day's LOW (LOD), PERSISTS one
``peak_points`` row per day, then builds the HOD×LOD joint matrix + marginals in
the ``/stats/peak-points`` router. The plugin has no database — so the tool layer
feeds in-memory ``session_range`` dicts (built by :mod:`engines.session_stats`)
to these same detectors and builds the matrix in Python.

Only the **pure** parts are vendored, matching production math:

- ``_time_key`` / ``_pick_extreme`` — pick the session owning the day's extreme,
  ties broken by earliest ``high_time`` / ``low_time`` (byte-for-byte port).
- ``_net_direction`` — bullish if max up-leg >= max down-leg across the day's
  sessions (the backend's day-direction convention for the peak-points view).
- ``classify_day`` — the body of ``compute_peak_points``'s per-day loop, minus
  the DB save: returns the ``peak_points`` data dict for one day, or ``None``.
- ``build_matrix`` — the body of the router's ``_build_matrix``: HOD×LOD joint
  counts/percentages + HOD/LOD marginals + valid sample size.
- ``confidence`` — the n→HIGH/MEDIUM/LOW/INSUFFICIENT bucketing other plugin
  stats tools use (``>=50 / >=20 / >=5 / else``).

DROPPED (DB-coupled, replaced by the tool layer): ``_fetch_session_ranges``,
``_save_peak_points``, ``compute_peak_points`` (the async orchestrator), and
``compute_all_peak_points``. Nothing here imports from ``app.*`` or sqlalchemy.

SESSION-RANGE SHAPE: each detector expects a list of session dicts with keys
``session`` (name), ``high``, ``low``, ``open``, ``close``, ``high_time``,
``low_time`` — exactly the ``data`` block that
``engines.session_stats._compute_session_range`` produces.
"""

from __future__ import annotations

SESSION_ORDER = ["asia", "london", "new_york"]

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# Confidence bucketing (same buckets as the other plugin stats tools)
# ---------------------------------------------------------------------------

def confidence(n: int) -> str:
    """n → HIGH / MEDIUM / LOW / INSUFFICIENT (``>=50 / >=20 / >=5 / else``)."""
    if n >= 50:
        return "HIGH"
    if n >= 20:
        return "MEDIUM"
    if n >= 5:
        return "LOW"
    return "INSUFFICIENT"


# ---------------------------------------------------------------------------
# Extreme picking (vendored from peak_points_stats._pick_extreme)
# ---------------------------------------------------------------------------

def _time_key(t: str | None) -> str:
    """Sort key for HH:MM strings; missing values sort last."""
    if not t:
        return "99:99"
    return t


def _pick_extreme(
    sessions: list[dict],
    *,
    field: str,
    time_field: str,
    pick_max: bool,
) -> tuple[str, float, str] | None:
    """Pick the session that owns the day's extreme.

    Ties are broken by earliest time-of-occurrence. Returns
    (session_name, value, time) or None if input is empty.
    """
    if not sessions:
        return None

    best: tuple[str, float, str] | None = None
    for s in sessions:
        try:
            val = float(s[field])
        except (TypeError, ValueError, KeyError):
            continue
        t = s.get(time_field) or ""
        if best is None:
            best = (s["session"], val, t)
            continue

        cur_sess, cur_val, cur_t = best
        if pick_max:
            if val > cur_val or (val == cur_val and _time_key(t) < _time_key(cur_t)):
                best = (s["session"], val, t)
        else:
            if val < cur_val or (val == cur_val and _time_key(t) < _time_key(cur_t)):
                best = (s["session"], val, t)
    return best


def _net_direction(sessions: list[dict]) -> str:
    """Bullish if max up-leg >= max down-leg across the day's sessions.

    Mirrors the backend convention: compare the largest bullish session move
    vs the largest bearish session move across the day's sessions.
    """
    max_up = 0.0
    max_down = 0.0
    for s in sessions:
        try:
            o = float(s["open"])
            c = float(s["close"])
        except (TypeError, ValueError, KeyError):
            continue
        delta = c - o
        if delta >= 0 and delta > max_up:
            max_up = delta
        elif delta < 0 and -delta > max_down:
            max_down = -delta
    return "bullish" if max_up >= max_down else "bearish"


# ---------------------------------------------------------------------------
# Per-day classification (body of compute_peak_points's loop, no DB save)
# ---------------------------------------------------------------------------

def classify_day(sessions: list[dict], weekday_index: int) -> dict | None:
    """Classify HOD-session and LOD-session for a single trading day.

    ``sessions`` is the list of per-session range dicts for the day (each with
    ``session``/``high``/``low``/``open``/``close``/``high_time``/``low_time``).
    ``weekday_index`` is ``date.weekday()`` (Mon=0). Returns the ``peak_points``
    data dict the backend would persist, or ``None`` if either extreme is
    unresolvable.
    """
    if not sessions:
        return None

    hod = _pick_extreme(sessions, field="high", time_field="high_time", pick_max=True)
    lod = _pick_extreme(sessions, field="low", time_field="low_time", pick_max=False)
    if hod is None or lod is None:
        return None

    hod_session, day_high, hod_time = hod
    lod_session, day_low, lod_time = lod

    return {
        "hod_session": hod_session,
        "lod_session": lod_session,
        "hod_time": hod_time or "",
        "lod_time": lod_time or "",
        "day_high": round(float(day_high), 6),
        "day_low": round(float(day_low), 6),
        "day_of_week": WEEKDAYS[weekday_index],
        "net_direction": _net_direction(sessions),
    }


# ---------------------------------------------------------------------------
# Matrix build (body of the router's _build_matrix)
# ---------------------------------------------------------------------------

def build_matrix(rows: list[dict]) -> dict:
    """Build the HOD×LOD joint distribution from classified ``peak_points`` rows.

    Returns a dict with:
      ``matrix[hod][lod]``  — joint counts
      ``matrix_pct[hod][lod]`` — joint probabilities (0-100, 1 decimal)
      ``hod_marginals``     — counts per HOD session
      ``hod_marginals_pct`` — P(HOD in session)
      ``lod_marginals``     — counts per LOD session
      ``lod_marginals_pct`` — P(LOD in session)
      ``sample_size``       — rows where both sessions are valid known names

    Convention: outer key is the session that printed the day's HIGH; inner key
    is the session that printed the day's LOW (``matrix[HOD][LOD]``).
    """
    counts = {s: {t: 0 for t in SESSION_ORDER} for s in SESSION_ORDER}
    hod_counts = {s: 0 for s in SESSION_ORDER}
    lod_counts = {s: 0 for s in SESSION_ORDER}
    total = 0

    for r in rows:
        hod = r.get("hod_session")
        lod = r.get("lod_session")
        if hod not in SESSION_ORDER or lod not in SESSION_ORDER:
            continue
        counts[hod][lod] += 1
        hod_counts[hod] += 1
        lod_counts[lod] += 1
        total += 1

    matrix_pct = {s: {t: 0.0 for t in SESSION_ORDER} for s in SESSION_ORDER}
    hod_marg_pct = {s: 0.0 for s in SESSION_ORDER}
    lod_marg_pct = {s: 0.0 for s in SESSION_ORDER}
    if total > 0:
        for h in SESSION_ORDER:
            for l in SESSION_ORDER:
                matrix_pct[h][l] = round(counts[h][l] / total * 100, 1)
            hod_marg_pct[h] = round(hod_counts[h] / total * 100, 1)
            lod_marg_pct[h] = round(lod_counts[h] / total * 100, 1)

    return {
        "matrix": counts,
        "matrix_pct": matrix_pct,
        "hod_marginals": hod_counts,
        "hod_marginals_pct": hod_marg_pct,
        "lod_marginals": lod_counts,
        "lod_marginals_pct": lod_marg_pct,
        "sample_size": total,
    }
