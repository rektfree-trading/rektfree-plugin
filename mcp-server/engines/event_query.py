"""
Unified in-memory event set for the backtester (vendored, DB-free).

The hosted backtester (`app/services/backtester.py`) queries a `session_events`
table that the product's ETL fills with detected events + their outcomes, then
filters those rows by structured conditions and aggregates the relevant outcome
rate. This module assembles that **same** event set IN MEMORY, with NO database:
it runs the already-vendored session detectors and SMC evaluators over a deep 1H
candle history and normalises every detected structure into a flat event record
the backtester can filter and aggregate.

What it REUSES (does not re-implement):
- ``engines.session_stats`` detectors — ``_group_by_day_and_session``,
  ``_compute_session_range``, ``_detect_sweep``, ``_detect_ny_continuation``,
  ``_detect_power_of_3`` (the same per-day loop ``tools/session_stats._build_events``
  runs), to produce the session-family events
  (``session_range``/``asia_sweep``/``london_sweep``/``ny_continuation``/``power_of_3``).
- ``engines.smc_stats.evaluate_smc_outcomes`` — the 200/50 sliding-window
  evaluation (same call ``tools/smc_stats`` makes) for the SMC-family events
  (``smc_ob_test``/``smc_fvg_test``/``smc_bos_test``/``smc_choch_test``/
  ``smc_eq_test``/``smc_sweep_test``).

Each event is a flat dict carrying the filterable keys the backtester's
``find_matching_events`` matches on — ``event_type``, ``day_of_week`` (session
family only; see note), ``session``, ``direction``, ``sweep_side``, ``htf_bias``,
``range_state`` — plus the per-event OUTCOME fields used by ``compute_outcomes``
(``reversal``/``continuation``/``held``/``filled``/... and any ``*_pct`` moves).

DAY-OF-WEEK NOTE: the vendored session detectors stamp ``day_of_week`` on every
event, so DOW filtering is exact for the session family. The vendored SMC
evaluator (``evaluate_smc_outcomes``) returns per-structure outcomes WITHOUT the
formation date, so SMC events have no ``day_of_week`` and a DOW filter cannot be
applied to them — the tool layer surfaces that as a note rather than silently
dropping all rows.

Nothing here imports from ``app.*`` or touches a database.
"""

from __future__ import annotations

from datetime import datetime, timezone

from engines import session_stats as session_engine
from engines import smc_stats as smc_engine

# event_type → which engine family produces it.
SESSION_EVENT_TYPES = (
    "session_range",
    "asia_sweep",
    "london_sweep",
    "ny_continuation",
    "power_of_3",
)
SMC_EVENT_TYPES = (
    "smc_ob_test",
    "smc_fvg_test",
    "smc_bos_test",
    "smc_choch_test",
    "smc_eq_test",
    "smc_sweep_test",
)
ALL_EVENT_TYPES = SESSION_EVENT_TYPES + SMC_EVENT_TYPES

# Map an SMC ``event_type`` to the key ``evaluate_smc_outcomes`` returns.
_SMC_OUTCOME_KEY = {
    "smc_ob_test": "ob_test",
    "smc_fvg_test": "fvg_test",
    "smc_bos_test": "bos_test",
    "smc_choch_test": "choch_test",
    "smc_eq_test": "eq_test",
    "smc_sweep_test": "sweep_test",
}


def _adapt_candles(raw: list[dict]) -> list[dict]:
    """Reshape Binance candles for the session detectors.

    The session detectors read ``c["timestamp"]`` as a timezone-aware UTC
    ``datetime`` (``.strftime``/``.hour``/``.weekday()``); the fetcher returns a
    float unix-second ``time``. Same adaptation ``tools/session_stats`` does.
    """
    return [
        {
            "timestamp": datetime.fromtimestamp(c["time"], tz=timezone.utc),
            "high": c["high"],
            "low": c["low"],
            "open": c["open"],
            "close": c["close"],
        }
        for c in raw
    ]


def _build_session_events(adapted: list[dict]) -> list[dict]:
    """Run the session detectors over every day/session → flat event records.

    Mirrors ``tools/session_stats._build_events`` (the same per-day loop the
    backend orchestrator runs, minus DB writes), then flattens each detector's
    ``{"data": {...}}`` into a single event dict tagged with ``event_type`` and
    the filterable fields the backtester matches on.
    """
    grouped = session_engine._group_by_day_and_session(adapted)

    # Power-of-3 needs an ADR baseline (avg full-day range across all sessions).
    daily_ranges: list[float] = []
    for sessions in grouped.values():
        all_day = [c for sc in sessions.values() for c in sc]
        if all_day:
            dh = max(float(c["high"]) for c in all_day)
            dl = min(float(c["low"]) for c in all_day)
            daily_ranges.append(dh - dl)
    avg_daily_range = (sum(daily_ranges) / len(daily_ranges)) if daily_ranges else 0.0

    events: list[dict] = []
    for day_key in sorted(grouped.keys()):
        sessions = grouped[day_key]
        asia_c = sessions.get("asia", [])
        london_c = sessions.get("london", [])
        ny_c = sessions.get("new_york", [])

        # session_range — one per session that had candles.
        for sess_name in ("asia", "london", "new_york"):
            ev = session_engine._compute_session_range(
                sessions.get(sess_name, []), sess_name, day_key, ""
            )
            if ev:
                d = ev["data"]
                events.append({
                    "event_type": "session_range",
                    "date": day_key,
                    "day_of_week": d["day_of_week"],
                    "session": sess_name,
                    "direction": d["direction"],
                    "range_pct": d.get("range_pct"),
                    "range": d.get("range"),
                    "_data": d,
                })

        # asia_sweep — did London sweep Asia's H/L?
        sweep = session_engine._detect_sweep(asia_c, london_c, "asia", "london", day_key)
        if sweep:
            d = sweep["data"]
            events.append({
                "event_type": "asia_sweep",
                "date": day_key,
                "day_of_week": d["day_of_week"],
                "session": sweep.get("session"),
                "sweep_side": d["swept_side"],
                "reversal": bool(d["reversal"]),
                "reversal_distance": d.get("reversal_distance"),
                "_data": d,
            })

        # london_sweep — did NY sweep London's H/L?
        sweep = session_engine._detect_sweep(london_c, ny_c, "london", "new_york", day_key)
        if sweep:
            d = sweep["data"]
            events.append({
                "event_type": "london_sweep",
                "date": day_key,
                "day_of_week": d["day_of_week"],
                "session": sweep.get("session"),
                "sweep_side": d["swept_side"],
                "reversal": bool(d["reversal"]),
                "reversal_distance": d.get("reversal_distance"),
                "_data": d,
            })

        # ny_continuation — did NY continue or reverse London?
        cont = session_engine._detect_ny_continuation(london_c, ny_c, day_key)
        if cont:
            d = cont["data"]
            events.append({
                "event_type": "ny_continuation",
                "date": day_key,
                "day_of_week": d["day_of_week"],
                "direction": d["ny_direction"],
                "continuation": bool(d["continuation"]),
                "_data": d,
            })

        # power_of_3 — AMD pattern completion.
        p3 = session_engine._detect_power_of_3(asia_c, london_c, ny_c, avg_daily_range, day_key)
        if p3:
            d = p3["data"]
            events.append({
                "event_type": "power_of_3",
                "date": day_key,
                "day_of_week": d["day_of_week"],
                "direction": d["distribution_direction"],
                "sweep_side": d["manipulation_side"],
                "distribution_success": bool(d["distribution_success"]),
                "_data": d,
            })

    return events


def _build_smc_events(raw: list[dict]) -> list[dict]:
    """Run the sliding-window SMC evaluation → flat event records.

    Reuses ``smc_stats.evaluate_smc_outcomes`` verbatim (the same call
    ``tools/smc_stats`` makes) and flattens each per-structure outcome into a
    backtester event. The evaluator returns ``session`` and a per-family bias
    (``ob_bias``/``fvg_bias``/...); we normalise the bias into both ``direction``
    and ``htf_bias`` so either condition key can filter it. No ``day_of_week``
    is available (the evaluator drops the formation date).
    """
    if len(raw) < smc_engine.MIN_CANDLES:
        return []

    outcomes = smc_engine.evaluate_smc_outcomes(raw)
    events: list[dict] = []

    for event_type, key in _SMC_OUTCOME_KEY.items():
        for o in outcomes.get(key, []):
            # The per-family bias field, normalised to direction/htf_bias.
            bias = (
                o.get("ob_bias")
                or o.get("fvg_bias")
                or o.get("bos_bias")
                or o.get("choch_bias")
            )
            # eq_test/sweep_test carry no bias; leave direction unset for them.
            ev = {
                "event_type": event_type,
                "session": o.get("session"),
                "_data": o,
            }
            if bias:
                ev["direction"] = bias
                ev["htf_bias"] = bias
            events.append(ev)

    return events


def build_event_set(raw_candles: list[dict]) -> list[dict]:
    """Assemble the full unified event set from one deep 1H candle history.

    ``raw_candles`` is the oldest→newest list from
    ``data.binance.fetch_candles_paged(symbol, "1h", ...)``. Returns a flat list
    of event dicts spanning both families — ready for the tool layer to filter by
    the backtester's structured conditions and aggregate the relevant outcome.
    """
    adapted = _adapt_candles(raw_candles)
    return _build_session_events(adapted) + _build_smc_events(raw_candles)
