"""
``discover_edges`` — mine recent history for statistical edges & anti-patterns.

Fetches deep 1H Binance history (keyless), reuses the vendored SMC + session
detectors to build a labeled event set IN MEMORY, then grid-searches single- and
pairwise-dimension filters and ranks each cell by

    edge_score = (win_rate - baseline) * sqrt(sample_count)

mirroring the hosted product's ``edge_discovery`` service — but with NO database,
NO AI narration, and NO macro dimension.

The hosted product mines its FULL persisted event history and ranks edges per
asset; this tool samples only the last ``days`` it fetches live (default ~180).
So the edges it surfaces are a **recent-sample exploration**, not a verified
strategy — and because a grid-search tests many cells, some apparent edges are
multiple-comparisons artifacts. The ``sqrt(n)`` weighting and the ``min_samples``
floor blunt that, but small-n edges are still fragile hypotheses to validate,
not guarantees.
"""

from __future__ import annotations

from datetime import datetime, timezone

from data import binance
from data import market
from engines import edge_discovery as engine
from engines import session_stats as sess_engine
from engines import smc_stats as smc_engine

# ~180 days × 24h = 4320 1H candles. The sliding-window SMC analyze is the cost,
# so we keep the default lookback modest; capped well below the smc_stats tool's
# 5000 to keep a single discover_edges call fast (<~10s).
_MAX_DAYS = 365
_MIN_CANDLES = smc_engine.MIN_CANDLES  # need a full window + look-forwards

# The dimensions we grid-search. Deliberately small: every added dimension
# multiplies the pairwise cell count and the multiple-comparisons risk. No macro
# dimension (the plugin has no macro feed).
_DIMENSIONS = ["session", "day_of_week", "direction", "side"]

# SMC event types → the outcome field that means "win" for that structure.
# (These are the natural success criteria the vendored evaluators emit.)
_SMC_WIN_FIELD = {
    "ob_test": "held",
    "fvg_test": "filled",
    "bos_test": "continuation",
    "choch_test": "reversed",
    "eq_test": "reversed",
    "sweep_test": "success",
}
# Which SMC events carry a directional bias we can label.
_SMC_BIAS_FIELD = {
    "ob_test": "ob_bias",
    "fvg_test": "fvg_bias",
    "bos_test": "bos_bias",
    "choch_test": "choch_bias",
}


def _adapt_for_sessions(raw: list[dict]) -> list[dict]:
    """Reshape Binance candles for the session detectors (need a UTC datetime)."""
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


def _build_smc_events(raw: list[dict]) -> list[dict]:
    """Run the vendored sliding-window SMC evaluation, flatten to labeled events.

    Each detected structure already carries its outcome + ``session`` (and, for
    most, ``trend_at_formation`` and a bias). We map the outcome to a boolean
    ``win`` and copy the dimensions the grid-search understands.
    """
    outcomes = smc_engine.evaluate_smc_outcomes(raw)
    events: list[dict] = []
    for etype, win_field in _SMC_WIN_FIELD.items():
        bias_field = _SMC_BIAS_FIELD.get(etype)
        for o in outcomes.get(etype, []):
            ev = {
                "event_type": etype,
                "win": bool(o.get(win_field)),
                "session": o.get("session"),
                "day_of_week": None,  # SMC outcomes are not weekday-tagged
                "direction": o.get(bias_field) if bias_field else None,
                # EQ/sweep carry a structure type instead of a bias.
                "side": o.get("eq_type") or o.get("sweep_type"),
            }
            events.append(ev)
    return events


def _build_session_events(raw: list[dict]) -> list[dict]:
    """Run the vendored session detectors, flatten to labeled events.

    Reuses ``tools/session_stats._build_events`` math via the engine detectors:
    sweep reversal (asia/london sweeps), NY continuation, and Power-of-3
    distribution success — each with its day-of-week and side.
    """
    from tools.session_stats import _adapt_candles, _build_events

    candles = _adapt_candles(raw)
    grouped = sess_engine._group_by_day_and_session(candles)
    built = _build_events(grouped)

    events: list[dict] = []

    # Sweeps — "win" = the sweep reversed (the fade played out).
    for d in built["asia_sweeps"]:
        events.append({
            "event_type": "asia_sweep",
            "win": bool(d.get("reversal")),
            "session": "london",  # London sweeps Asia
            "day_of_week": d.get("day_of_week"),
            "direction": None,
            "side": d.get("swept_side"),
        })
    for d in built["london_sweeps"]:
        events.append({
            "event_type": "london_sweep",
            "win": bool(d.get("reversal")),
            "session": "new_york",  # NY sweeps London
            "day_of_week": d.get("day_of_week"),
            "direction": None,
            "side": d.get("swept_side"),
        })

    # NY continuation — "win" = NY continued London's direction.
    for d in built["ny_conts"]:
        events.append({
            "event_type": "ny_continuation",
            "win": bool(d.get("continuation")),
            "session": "new_york",
            "day_of_week": d.get("day_of_week"),
            "direction": d.get("london_direction"),
            "side": None,
        })

    # Power-of-3 — "win" = distribution ran ≥1.5× the Asia range.
    for d in built["p3s"]:
        events.append({
            "event_type": "power_of_3",
            "win": bool(d.get("distribution_success")),
            "session": None,
            "day_of_week": d.get("day_of_week"),
            "direction": d.get("distribution_direction"),
            "side": d.get("manipulation_side"),
        })

    return events


def register(mcp) -> None:
    @mcp.tool()
    async def discover_edges(
        symbol: str = "BTCUSDT",
        days: int = 180,
        min_samples: int = 10,
        top: int = 15,
    ) -> dict:
        """Mine a crypto symbol's recent history for statistical edges.

        Fetches deep 1H history from Binance (public, no API key), reuses the
        same SMC and session detectors the hosted product runs to build a
        labeled event set in memory — every order-block / FVG / BOS / CHoCH /
        equal-level / liquidity-sweep outcome, plus session sweeps, NY
        continuation, and Power-of-3 — each tagged with its win/loss and its
        context dimensions (session, day-of-week, direction/bias, swept side).

        It then grid-searches single- and pairwise-dimension filters and ranks
        each cell exactly the way the hosted ``edge_discovery`` service does:

            edge_score = (win_rate - baseline) * sqrt(sample_count)

        where ``baseline`` is the event type's overall win rate. A positive
        score means the condition wins MORE than baseline (an edge); a negative
        score means it wins LESS (an anti-pattern to avoid). The ``sqrt(n)``
        factor is the whole point — it down-weights small samples so a flukey
        "100% of 5" doesn't outrank a durable "62% of 130".

        IMPORTANT — this is recent-sample EXPLORATION, not gospel:
        - The hosted product mines its FULL persisted history; this tool samples
          only the last ``days`` it fetches live (default ~180). Numbers will
          differ from app.rektfree.com.
        - There is **no macro dimension** here (the plugin has no macro feed).
        - A grid-search tests many cells, so some apparent edges are
          multiple-comparisons artifacts. ``min_samples`` and the ``sqrt(n)``
          weighting blunt this, but any low-``n`` edge is a fragile hypothesis
          to validate forward, not a guarantee. Cite ``n`` when you act on one.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex/metals (e.g. ``EUR_USD``,
                ``XAU_USD``) ARE supported when ``RF_OANDA_TOKEN`` is set;
                crypto needs no key.
            days: Lookback window in days of 1H candles (capped at 365, default
                ~180). Deeper = more samples per cell but a slower analyze.
            min_samples: Minimum events in a cell for it to qualify as an edge
                (default 10). Lower it to surface more (noisier) cells.
            top: Max number of edges and max number of anti-patterns to return
                (default 15 each).

        Returns:
            A dict with ``symbol``; ``window`` (``candles``, ``from``, ``to``
            ISO-UTC, ``days`` of coverage); ``baselines`` (per-event-type win
            rate, 0–100); ``edges`` (top positive, strongest first); and
            ``anti_patterns`` (top negative, most-negative first). Each edge is
            ``{event_type, filters, n, win_rate, baseline, edge_score}``. Plus
            ``notes`` restating the recent-sample / overfitting caveats. On
            failure, a dict with an ``error`` key.
        """
        days = max(1, min(int(days), _MAX_DAYS))
        min_samples = max(2, int(min_samples))
        top = max(1, int(top))

        total = days * 24
        max_pages = max(2, (total // 1000) + 2)

        try:
            raw = await market.fetch_candles_paged(
                symbol, "1h", total=total, max_pages=max_pages
            )
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if len(raw) < _MIN_CANDLES:
            return {
                "error": (
                    f"Only {len(raw)} 1H candles available for {symbol.upper()} "
                    f"— need at least {_MIN_CANDLES} to slide the SMC window and "
                    "label enough events to mine edges. Try a deeper window or a "
                    "more liquid symbol."
                )
            }

        events = _build_smc_events(raw) + _build_session_events(raw)
        if not events:
            return {
                "error": (
                    f"No labeled events could be built for {symbol.upper()} over "
                    f"{days} days. Try a deeper window."
                )
            }

        result = engine.discover_edges(
            events, _DIMENSIONS, min_samples=min_samples, top=top
        )

        from_iso = datetime.fromtimestamp(raw[0]["time"], tz=timezone.utc).isoformat()
        to_iso = datetime.fromtimestamp(raw[-1]["time"], tz=timezone.utc).isoformat()
        span_days = max(1, round((raw[-1]["time"] - raw[0]["time"]) / 86400))

        return {
            "symbol": symbol.upper(),
            "window": {
                "candles": len(raw),
                "from": from_iso,
                "to": to_iso,
                "days": span_days,
            },
            "baselines": result["baselines"],
            "edges": result["edges"],
            "anti_patterns": result["anti_patterns"],
            "notes": [
                "Recent live sample only (last ~{} days), NOT full history — "
                "rates differ from app.rektfree.com.".format(span_days),
                "No macro dimension in this slice.",
                "Grid-search tests many cells: low-n edges are fragile "
                "hypotheses (multiple-comparisons / overfitting risk), not "
                "guarantees. edge_score weights by sqrt(n) to discount thin "
                "samples — always cite n before acting.",
            ],
        }
