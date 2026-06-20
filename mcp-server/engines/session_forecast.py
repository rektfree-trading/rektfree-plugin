"""
Pure session-forecast helpers (crypto, keyless — no ``app.*``, no DB).

The hosted ``app/services/session_forecast.py`` builds a forecast by querying
persisted ``session_events`` for historically *similar* sessions (a condition
vector of DOW / HTF-bias / range-state / ATR / macro / prior-outcome) and
computing conditional probabilities from the matches. That matching layer is
the DB-coupled part and depends on precomputed event rows we don't have here.

This module replicates the *pure* core of that approach: given the recent
history of one session (its per-day range events, the sweep events where that
session was the sweeper, and — for New York — the continuation events), it
computes the empirical frequency distributions the backend's ``_compute_scenarios``
leans on:

  - expected range  (median + a low/high percentile band, from ``range_pct``)
  - sweep probability of the prior session's high/low + the side skew + the
    reversal-after-sweep rate  (faithful to ``_agg_sweeps`` / ``key_levels``)
  - continuation-vs-reversal odds  (New York only, from ny_continuation events)

Every figure carries the sample size ``n`` it was computed from. These are
*frequencies over a recent live sample* — a statistical forecast, not a
prediction, and with no macro/news input. Nothing here imports ``app.*`` or
SQLAlchemy; it operates purely on the in-memory event dicts produced by the
vendored ``engines.session_stats`` detectors.
"""

from __future__ import annotations

from collections import Counter


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolated percentile over an already-sorted list.

    ``pct`` is a fraction in [0, 1]. Returns 0.0 for an empty list.
    """
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    rank = pct * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def expected_range(range_rows: list[dict]) -> dict:
    """Empirical range distribution for a session, in ``range_pct`` units.

    ``range_rows`` are the ``data`` dicts from ``_compute_session_range`` (each
    has ``range_pct`` = (high-low)/low*100). Returns median plus a 25th/75th
    percentile band (the "typical" envelope) and the min/max seen, all with
    ``n``. Percent units are price-regime-agnostic so they project cleanly onto
    the live price.
    """
    pcts = sorted(r["range_pct"] for r in range_rows if r.get("range_pct", 0) > 0)
    n = len(pcts)
    if n == 0:
        return {"median": 0.0, "low": 0.0, "high": 0.0, "min": 0.0, "max": 0.0, "n": 0}
    return {
        "median": round(_percentile(pcts, 0.50), 3),
        "low": round(_percentile(pcts, 0.25), 3),
        "high": round(_percentile(pcts, 0.75), 3),
        "min": round(pcts[0], 3),
        "max": round(pcts[-1], 3),
        "n": n,
    }


def sweep_probability(sweep_rows: list[dict], prior_session_days: int) -> dict:
    """Frequency the forecast session sweeps the prior session's H/L.

    Mirrors the backend's ``_agg_sweeps`` denominator: the rate is over the
    number of days the *prior* session existed (``prior_session_days``), since a
    sweep can only happen on a day that had a prior session to sweep. ``side``
    reports the high/low skew (which liquidity gets hunted more), and
    ``reversal_rate`` is how often the sweep closed back inside — the fade edge
    the backend's ``_compute_scenarios`` keys its primary scenario on.
    """
    if prior_session_days <= 0:
        return {"prob": 0.0, "n": 0}
    sweep_count = len(sweep_rows)
    swept_high = sum(1 for s in sweep_rows if s.get("swept_side") == "high")
    swept_low = sum(1 for s in sweep_rows if s.get("swept_side") == "low")
    swept_both = sum(1 for s in sweep_rows if s.get("swept_side") == "both")
    reversals = sum(1 for s in sweep_rows if s.get("reversal"))

    # Side skew including the "both" days on each side it touched.
    high_hits = swept_high + swept_both
    low_hits = swept_low + swept_both
    if high_hits > low_hits:
        likely_side = "high"
    elif low_hits > high_hits:
        likely_side = "low"
    else:
        likely_side = "either"

    return {
        "prob": round(sweep_count / prior_session_days * 100, 1),
        "swept_high": swept_high,
        "swept_low": swept_low,
        "swept_both": swept_both,
        "likely_side": likely_side,
        "reversal_rate": round(reversals / max(sweep_count, 1) * 100, 1),
        "sweep_count": sweep_count,
        "n": prior_session_days,
    }


def continuation_probability(ny_cont_rows: list[dict]) -> dict:
    """Continuation-vs-reversal odds for New York vs London.

    New York only — the backend computes this from ``ny_continuation`` events
    (NY's close direction vs London's). ``continuation`` = NY extended London's
    move; ``reversal`` = NY went the other way. Empty/non-NY → ``n == 0``.
    """
    n = len(ny_cont_rows)
    if n == 0:
        return {"continuation": 0.0, "reversal": 0.0, "n": 0}
    cont = sum(1 for r in ny_cont_rows if r.get("continuation"))
    return {
        "continuation": round(cont / n * 100, 1),
        "reversal": round((n - cont) / n * 100, 1),
        "n": n,
    }


def direction_skew(range_rows: list[dict]) -> dict:
    """Bullish/bearish close-direction frequency for the session, with ``n``."""
    n = len(range_rows)
    if n == 0:
        return {"bullish": 0.0, "bearish": 0.0, "n": 0}
    counts = Counter(r.get("direction") for r in range_rows)
    bull = counts.get("bullish", 0)
    return {
        "bullish": round(bull / n * 100, 1),
        "bearish": round((n - bull) / n * 100, 1),
        "n": n,
    }


def project_levels(
    last_price: float,
    median_range_pct: float,
    prior_high: float | None,
    prior_low: float | None,
) -> dict:
    """Concrete price projections off the live price + prior-session extremes.

    The expected range is a *percent* of price; we center the projected band on
    the live price (``last_price``) so the high/low are the levels the session
    would reach at its median historical range. Prior-session high/low are the
    liquidity pools a sweep would target — passed through verbatim when known so
    the model can pair "sweep prob X%" with the actual price to watch.
    """
    half = last_price * (median_range_pct / 100.0) / 2.0
    out: dict = {
        "anchor_price": round(last_price, 6),
        "projected_high": round(last_price + half, 6),
        "projected_low": round(last_price - half, 6),
        "median_range_abs": round(2 * half, 6),
    }
    if prior_high is not None:
        out["prior_session_high"] = round(prior_high, 6)
    if prior_low is not None:
        out["prior_session_low"] = round(prior_low, 6)
    return out
