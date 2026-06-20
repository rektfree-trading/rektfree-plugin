"""
Pure-Python Day-Type classifier (vendored from the backend).

DB-free port of the backend's ``app/services/day_type_stats.py``. The hosted
product reads pre-computed ``session_range`` / ``*_sweep`` / ``ny_continuation``
/ ``power_of_3`` rows out of ``session_events`` (plus D1 candles), classifies
each trading day into one of 11 archetypes (4 regimes), and PERSISTS a
``day_type`` row. The plugin has no database — so the tool layer reproduces the
per-day event ``rows`` dict in memory (via :mod:`engines.session_stats`) and
feeds it to the SAME classifier vendored here.

Only the **pure** classifier core is vendored, byte-for-byte where it matters so
the archetype assignment stays identical to production:

- ``REGIME_BY_ARCHETYPE`` / ``ALL_ARCHETYPES`` / ``WEEKDAYS`` — taxonomy
- ``_net_direction``        — bullish/bearish/neutral from a D1 candle
- ``_hod_lod_session``      — which session printed the day's high / low
- ``_classify_day``         — the deterministic priority-ordered rule engine

DROPPED (DB-coupled, replaced by the tool layer): ``_fetch_daily_candles``,
``_fetch_session_event_rows``, ``_save_day_type``, ``compute_day_types`` (the
async orchestrator), and ``compute_all_day_types``. Nothing here imports from
``app.*`` or sqlalchemy.

ROW CONTRACT (mirrors what the backend pulls from ``session_events``): the
``rows`` argument to :func:`_classify_day` is keyed ``f"{event_type}:{session}"``
where the values are the ``data`` payloads produced by the session_stats
detectors:

- ``session_range:asia`` / ``:london`` / ``:new_york`` — ``_compute_session_range`` data
- ``asia_sweep:london``  — ``_detect_sweep`` data (London swept Asia)
- ``london_sweep:new_york`` — ``_detect_sweep`` data (NY swept London)
- ``ny_continuation:new_york`` — ``_detect_ny_continuation`` data
- ``power_of_3:daily`` — ``_detect_power_of_3`` data

``d1_today`` / ``d1_prev`` are ``{high, low, open, close}`` daily candles, which
the tool layer synthesises from the 1H candles of each UTC day.
"""

from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

REGIME_BY_ARCHETYPE: dict[str, str] = {
    "asia_breakout_continuation":   "trend",
    "london_breakout_continuation": "trend",
    "ny_breakout_continuation":     "trend",
    "asia_high_london_reversal":    "london_reverse",
    "asia_low_london_reversal":     "london_reverse",
    "power_of_3_long":              "high_volatile",
    "power_of_3_short":             "high_volatile",
    "double_sweep_expansion":       "high_volatile",
    "inside_day":                   "rare",
    "outside_day":                  "rare",
    "consolidation_drift":          "rare",
}

ALL_ARCHETYPES = list(REGIME_BY_ARCHETYPE.keys())

# Regimes always reported (so a 0% regime still appears).
ALL_REGIMES = ["trend", "london_reverse", "high_volatile", "rare"]


def _net_direction(d1: dict | None) -> str:
    if not d1:
        return "neutral"
    return "bullish" if d1["close"] > d1["open"] else "bearish" if d1["close"] < d1["open"] else "neutral"


def _hod_lod_session(
    asia: dict | None,
    london: dict | None,
    ny: dict | None,
    day_high: float,
    day_low: float,
) -> tuple[str | None, str | None]:
    """Identify which session printed the day's high and low."""
    sess_map = {"asia": asia, "london": london, "new_york": ny}
    hod_session = None
    lod_session = None
    # Highest session high wins HOD; lowest session low wins LOD.
    best_high = -float("inf")
    best_low = float("inf")
    for name, s in sess_map.items():
        if not s:
            continue
        sh = float(s.get("high", 0) or 0)
        sl = float(s.get("low", 0) or 0)
        if sh > best_high:
            best_high = sh
            hod_session = name
        if sl < best_low and sl > 0:
            best_low = sl
            lod_session = name
    # Final cross-check against the day extremes (in case D1 candle differs).
    return hod_session, lod_session


def _classify_day(
    day_key: str,
    d1_today: dict | None,
    d1_prev: dict | None,
    rows: dict[str, dict[str, Any]],
    daily_range_history: list[float],
) -> dict | None:
    """Classify a single day. Returns the data payload (or None if there is not
    enough information for any meaningful classification).

    Vendored verbatim from the backend so the rule engine — priority order,
    thresholds, and ``rules_matched`` strings — stays identical to production.
    """
    asia = rows.get("session_range:asia")
    london = rows.get("session_range:london")
    ny = rows.get("session_range:new_york")
    asia_sweep = rows.get("asia_sweep:london")  # London swept Asia
    london_sweep = rows.get("london_sweep:new_york")  # NY swept London
    ny_cont = rows.get("ny_continuation:new_york")
    p3 = rows.get("power_of_3:daily")

    # Determine day H/L/range. Prefer D1 candle, fall back to MAX/MIN of
    # session_range rows.
    if d1_today:
        day_high = float(d1_today["high"])
        day_low = float(d1_today["low"])
        day_open = float(d1_today["open"])
        day_close = float(d1_today["close"])
    else:
        sess_highs = [float(s["high"]) for s in (asia, london, ny) if s and s.get("high") is not None]
        sess_lows = [float(s["low"]) for s in (asia, london, ny) if s and s.get("low") is not None]
        if not sess_highs or not sess_lows:
            return None
        day_high = max(sess_highs)
        day_low = min(sess_lows)
        # First/last session by chronological order
        first = asia or london or ny
        last = ny or london or asia
        day_open = float(first["open"]) if first and first.get("open") is not None else day_low
        day_close = float(last["close"]) if last and last.get("close") is not None else day_high

    day_range = day_high - day_low
    day_range_pct = (day_range / day_low * 100) if day_low > 0 else 0.0

    net_dir = "bullish" if day_close > day_open else "bearish" if day_close < day_open else "neutral"

    swept_asia_high = bool(asia_sweep and asia_sweep.get("swept_side") in ("high", "both"))
    swept_asia_low = bool(asia_sweep and asia_sweep.get("swept_side") in ("low", "both"))
    swept_london_high = bool(london_sweep and london_sweep.get("swept_side") in ("high", "both"))
    swept_london_low = bool(london_sweep and london_sweep.get("swept_side") in ("low", "both"))
    ny_continuation_flag = bool(ny_cont and ny_cont.get("continuation"))

    hod_session, lod_session = _hod_lod_session(asia, london, ny, day_high, day_low)

    # Expansion factor: day_range / median(prior 30 days' day_ranges)
    prior_30 = daily_range_history[-30:]
    median_prior = median(prior_30) if len(prior_30) >= 5 else 0.0
    expansion_factor = (day_range / median_prior) if median_prior > 0 else 1.0

    # Direction helpers
    asia_dir = (asia or {}).get("direction") if asia else None
    london_dir = (london or {}).get("direction") if london else None
    ny_dir = (ny or {}).get("direction") if ny else None
    london_range_pct = float((london or {}).get("range_pct") or 0)
    ny_range_pct = float((ny or {}).get("range_pct") or 0)

    rules_matched: list[str] = []
    archetype: str | None = None

    # ---------- Priority 1: inside_day / outside_day (need yesterday's D1) ----------
    if d1_prev:
        prev_high = float(d1_prev["high"])
        prev_low = float(d1_prev["low"])
        if day_high < prev_high and day_low > prev_low:
            archetype = "inside_day"
            rules_matched.append("today_inside_yesterdays_range")
        elif day_high > prev_high and day_low < prev_low:
            archetype = "outside_day"
            rules_matched.append("today_engulfs_yesterdays_range")

    # ---------- Priority 2: Power of 3 ----------
    if archetype is None and p3:
        if p3.get("distribution_direction") == "bullish" and p3.get("manipulation_side") in ("low", "both"):
            archetype = "power_of_3_long"
            rules_matched.append("power_of_3_event_bullish_distribution")
        elif p3.get("distribution_direction") == "bearish" and p3.get("manipulation_side") in ("high", "both"):
            archetype = "power_of_3_short"
            rules_matched.append("power_of_3_event_bearish_distribution")

    # Derived Power of 3 fallback — when the explicit event isn't present
    # (small Asia range + sweep + strong daily expansion).
    if archetype is None and asia and london and net_dir != "neutral":
        asia_range = float(asia.get("range") or 0)
        if (
            expansion_factor >= 1.3
            and asia_range > 0
            and (day_range / max(asia_range, 0.000001)) >= 2.0
        ):
            if swept_asia_low and net_dir == "bullish":
                archetype = "power_of_3_long"
                rules_matched.append("derived_amd_long")
            elif swept_asia_high and net_dir == "bearish":
                archetype = "power_of_3_short"
                rules_matched.append("derived_amd_short")

    # ---------- Priority 3: double_sweep_expansion ----------
    if archetype is None and (
        (swept_asia_high or swept_asia_low) and (swept_london_high or swept_london_low)
    ):
        archetype = "double_sweep_expansion"
        rules_matched.append("asia_and_london_both_swept")

    # ---------- Priority 4: London reversal of Asia extremes ----------
    if archetype is None and asia_sweep:
        reversed_after = bool(asia_sweep.get("reversal"))
        if swept_asia_high and reversed_after and net_dir == "bearish":
            archetype = "asia_high_london_reversal"
            rules_matched.append("asia_high_swept_then_close_bearish")
        elif swept_asia_low and reversed_after and net_dir == "bullish":
            archetype = "asia_low_london_reversal"
            rules_matched.append("asia_low_then_london_reverses_up")

    # ---------- Priority 5: Trend continuations ----------
    if archetype is None:
        # Asia breakout continuation: asia_dir == net_dir, no London reversal,
        # NY continuation flag set.
        if (
            asia_dir is not None
            and asia_dir == net_dir
            and ny_continuation_flag
            and not (swept_asia_high and net_dir == "bearish")
            and not (swept_asia_low and net_dir == "bullish")
        ):
            archetype = "asia_breakout_continuation"
            rules_matched.append("asia_dir_matches_day_dir_and_ny_continuation")

    if archetype is None:
        # London breakout continuation: london expansion in net direction,
        # NY continues.
        if (
            london_dir is not None
            and london_dir == net_dir
            and ny_continuation_flag
            and london_range_pct > 0
        ):
            archetype = "london_breakout_continuation"
            rules_matched.append("london_expansion_matches_day_dir_and_ny_continuation")

    if archetype is None:
        # NY breakout continuation: NY prints HOD or LOD with continuation
        # from London.
        if (
            ny_dir is not None
            and london_dir is not None
            and ny_dir == london_dir
            and ny_range_pct >= london_range_pct
            and (hod_session == "new_york" or lod_session == "new_york")
        ):
            archetype = "ny_breakout_continuation"
            rules_matched.append("ny_prints_extreme_with_london_continuation")

    # ---------- Priority 6: Consolidation drift (low-vol catch-all) ----------
    if archetype is None:
        prior_pcts = []
        for r in daily_range_history[-30:]:
            # daily_range_history holds RAW range; compute approx pct via day_low
            if day_low > 0:
                prior_pcts.append(r / day_low * 100)
        median_pct = median(prior_pcts) if prior_pcts else 0.0
        if median_pct > 0 and day_range_pct < median_pct * 0.5:
            archetype = "consolidation_drift"
            rules_matched.append("range_pct_below_half_30d_median")

    # Final catch-all.
    if archetype is None:
        archetype = "consolidation_drift"
        rules_matched.append("default_low_signal_day")

    regime = REGIME_BY_ARCHETYPE[archetype]
    dt = datetime.strptime(day_key, "%Y-%m-%d")
    dow = WEEKDAYS[dt.weekday()]

    return {
        "archetype": archetype,
        "regime": regime,
        "day_of_week": dow,
        "day_high": round(day_high, 6),
        "day_low": round(day_low, 6),
        "day_range": round(day_range, 6),
        "day_range_pct": round(day_range_pct, 3),
        "hod_session": hod_session,
        "lod_session": lod_session,
        "swept_asia_high": swept_asia_high,
        "swept_asia_low": swept_asia_low,
        "swept_london_high": swept_london_high,
        "swept_london_low": swept_london_low,
        "ny_continuation": ny_continuation_flag,
        "net_direction": net_dir,
        "expansion_factor": round(expansion_factor, 3),
        "rules_matched": rules_matched,
    }
