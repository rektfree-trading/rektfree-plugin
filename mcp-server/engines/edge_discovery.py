"""
Edge-discovery grid-search engine — PURE / keyless / DB-free.

A vendored, database-free distillation of the backend's
``app/services/edge_discovery.py``. The backend grid-searches combinations of
trading-pattern conditions over a persisted ``session_events`` store and ranks
each cell by how far its win rate beats (or trails) the pattern's baseline,
weighted by sample size. This module keeps that *ranking math* identical —

    edge_score = (win_rate - baseline) * sqrt(sample_count)

— but operates on an in-memory list of already-labeled events instead of SQL.

What's DIFFERENT from the backend:
- **No DB / no AI / no macro.** The backend reads ``session_events`` rows, calls
  an LLM to narrate each edge, and includes a macro-proximity dimension. None of
  that is here. The tool layer (``tools/edge_discovery.py``) builds the labeled
  event list in memory by reusing the vendored SMC + session detectors, then
  hands it to :func:`discover_edges`.
- **Bounded grid.** The backend tests 1–3 filters at a time across many
  dimensions. This module tests only **single and pairwise** filters over a
  small, fixed dimension set (see the tool) to keep a live in-memory analyze
  fast and to limit the multiple-comparisons blow-up.

EVENT SHAPE — every event handed to :func:`discover_edges` is a flat dict:

    {
        "event_type": "ob_test",   # baseline is computed per event_type
        "win": True | False,       # the event's natural success criterion
        # ...any number of dimension fields, e.g.:
        "session": "london",
        "day_of_week": "Tuesday",
        "direction": "bullish",
        "zone": "premium",
        ...
    }

Dimension values may be ``None`` (unknown) — those events are simply excluded
from any cell that filters on that dimension, never counted as a category.

Nothing here imports from ``app.*``.
"""

from __future__ import annotations

import math
from itertools import combinations


def _win_rate(events: list[dict]) -> float:
    """Percentage of winning events (0–100, one decimal). 0.0 when empty."""
    n = len(events)
    if not n:
        return 0.0
    wins = sum(1 for e in events if e.get("win"))
    return round(wins / n * 100, 1)


def compute_baselines(events: list[dict]) -> dict[str, float]:
    """Per-``event_type`` baseline win rate over *all* its instances.

    The baseline is the no-filter reference each filtered cell is measured
    against — exactly the backend's ``_compute_baseline`` (a COUNT/SUM over the
    whole pattern), just in memory.
    """
    by_type: dict[str, list[dict]] = {}
    for e in events:
        by_type.setdefault(e["event_type"], []).append(e)
    return {etype: _win_rate(evs) for etype, evs in by_type.items()}


def _cell_filters(
    events: list[dict],
    dimensions: list[str],
) -> "dict[tuple, dict]":
    """Enumerate single- and pairwise-dimension filter cells for one event type.

    Returns a mapping ``filter_dict_items -> {"filters", "events"}`` where each
    cell holds the events matching that exact combination of (dimension=value)
    constraints. Events whose value for a filtered dimension is ``None`` are
    excluded from that cell (unknown ≠ a category). Dimensions absent from every
    event are skipped automatically.
    """
    # Which dimensions actually carry at least one non-None value here.
    live_dims = [
        d for d in dimensions
        if any(e.get(d) is not None for e in events)
    ]

    cells: dict[tuple, dict] = {}

    def _add(combo: tuple[str, ...]) -> None:
        # Group events by their value-tuple across the chosen dimensions,
        # dropping events that are None on any of them.
        buckets: dict[tuple, list[dict]] = {}
        for e in events:
            vals = tuple(e.get(d) for d in combo)
            if any(v is None for v in vals):
                continue
            buckets.setdefault(vals, []).append(e)
        for vals, evs in buckets.items():
            filters = {d: v for d, v in zip(combo, vals)}
            key = tuple(sorted(filters.items()))
            cells[key] = {"filters": filters, "events": evs}

    # Single-dimension cells, then pairwise. No deeper combos — bounded search.
    for d in live_dims:
        _add((d,))
    for combo in combinations(live_dims, 2):
        _add(combo)

    return cells


def discover_edges(
    events: list[dict],
    dimensions: list[str],
    *,
    min_samples: int = 10,
    top: int = 15,
    min_edge_pct: float = 0.0,
) -> dict:
    """Grid-search labeled events for the strongest positive and negative edges.

    For each ``event_type`` present:

    1. Compute the baseline win rate over all its events.
    2. Enumerate single- and pairwise-dimension filter cells (see
       :func:`_cell_filters`).
    3. For every cell with ``n >= min_samples`` compute the cell win rate and

           edge_score = (win_rate - baseline) * sqrt(n)

       Positive edge_score = the condition wins MORE than baseline; negative =
       an anti-pattern (wins less). The ``sqrt(n)`` factor down-weights
       small-sample cells so a flukey 100%-of-5 doesn't outrank a durable
       60%-of-120.

    Cells whose absolute deviation from baseline is below ``min_edge_pct`` are
    dropped (noise filter; default 0 keeps everything ≥ min_samples).

    Args:
        events: flat labeled event dicts (see module docstring).
        dimensions: the ordered dimension field names to grid-search over.
        min_samples: minimum cell size to be eligible (default 10).
        top: cap on how many edges and how many anti-patterns to return.
        min_edge_pct: minimum |win_rate - baseline| to keep a cell.

    Returns:
        ``{"baselines": {event_type: rate}, "edges": [...], "anti_patterns":
        [...]}`` where each entry is
        ``{event_type, filters, n, win_rate, baseline, edge_score}``. ``edges``
        are sorted strongest-positive first; ``anti_patterns`` most-negative
        first.
    """
    baselines = compute_baselines(events)

    by_type: dict[str, list[dict]] = {}
    for e in events:
        by_type.setdefault(e["event_type"], []).append(e)

    scored: list[dict] = []
    for etype, evs in by_type.items():
        baseline = baselines[etype]
        cells = _cell_filters(evs, dimensions)
        for cell in cells.values():
            cell_evs = cell["events"]
            n = len(cell_evs)
            if n < min_samples:
                continue
            win_rate = _win_rate(cell_evs)
            delta = win_rate - baseline
            if abs(delta) < min_edge_pct:
                continue
            edge_score = round(delta * math.sqrt(n), 2)
            scored.append({
                "event_type": etype,
                "filters": cell["filters"],
                "n": n,
                "win_rate": win_rate,
                "baseline": round(baseline, 1),
                "edge_score": edge_score,
            })

    positives = sorted(
        (s for s in scored if s["edge_score"] > 0),
        key=lambda s: -s["edge_score"],
    )[:top]
    negatives = sorted(
        (s for s in scored if s["edge_score"] < 0),
        key=lambda s: s["edge_score"],
    )[:top]

    return {
        "baselines": {k: round(v, 1) for k, v in baselines.items()},
        "edges": positives,
        "anti_patterns": negatives,
    }
