"""
``compute_day_type_stats`` — on-the-fly day-type classification (crypto, keyless).

Fetches deep 1H Binance history, rebuilds the per-day session events the hosted
product would have persisted (via the vendored session_stats detectors),
classifies every UTC day into one of 11 archetypes / 4 regimes with the SAME
deterministic rule engine, then aggregates the classifications the way the
hosted ``/stats/day-type/frequency`` router does — archetype + regime
distribution %, per-archetype average daily range, day-of-week tendencies, and
the most recent day's label.

The hosted product classifies over its FULL candle history; this tool samples
only the last ~N days fetched live, so the distribution is a recent snapshot
and will differ from the dashboard's long-run figures.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from data import binance
from data import market
from engines import day_type_stats as dt_engine
from engines import session_stats as sess_engine

# Cap the lookback so a single call stays polite to Binance's rate limits.
_MAX_DAYS = 180
_MIN_DAYS = 5  # below this no day-type distribution is meaningful


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _adapt_candles(raw: list[dict]) -> list[dict]:
    """Reshape Binance candles for the session detectors.

    The session_stats detectors read ``c["timestamp"]`` as a tz-aware UTC
    ``datetime``; the fetcher returns a float unix-second ``time``.
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


def _synth_d1(day_candles: list[dict]) -> dict | None:
    """Synthesise a D1 candle from a UTC day's 1H candles (oldest→newest).

    The backend reads true D1 candles; here we derive open=first.open,
    close=last.close, high=max, low=min over the day's 1H bars. Good enough for
    the inside/outside-day and net-direction checks the classifier makes.
    """
    if not day_candles:
        return None
    return {
        "open": float(day_candles[0]["open"]),
        "close": float(day_candles[-1]["close"]),
        "high": max(float(c["high"]) for c in day_candles),
        "low": min(float(c["low"]) for c in day_candles),
    }


def _build_event_rows(day_key: str, sessions: dict[str, list[dict]], avg_daily_range: float) -> dict:
    """Build the ``rows`` dict the classifier expects for one day.

    Reproduces the ``session_events`` payloads the backend would have persisted,
    keyed ``f"{event_type}:{session}"``, by running the vendored session_stats
    detectors over the day's session candles in memory.
    """
    asia_c = sessions.get("asia", [])
    london_c = sessions.get("london", [])
    ny_c = sessions.get("new_york", [])

    rows: dict[str, dict] = {}

    for sess_name in ("asia", "london", "new_york"):
        ev = sess_engine._compute_session_range(sessions.get(sess_name, []), sess_name, day_key, "")
        if ev:
            rows[f"session_range:{sess_name}"] = ev["data"]

    sweep = sess_engine._detect_sweep(asia_c, london_c, "asia", "london", day_key)
    if sweep:
        rows["asia_sweep:london"] = sweep["data"]

    sweep = sess_engine._detect_sweep(london_c, ny_c, "london", "new_york", day_key)
    if sweep:
        rows["london_sweep:new_york"] = sweep["data"]

    cont = sess_engine._detect_ny_continuation(london_c, ny_c, day_key)
    if cont:
        rows["ny_continuation:new_york"] = cont["data"]

    p3 = sess_engine._detect_power_of_3(asia_c, london_c, ny_c, avg_daily_range, day_key)
    if p3:
        rows["power_of_3:daily"] = p3["data"]

    return rows


def _classify_history(grouped: dict[str, dict[str, list[dict]]], d1_by_day: dict[str, dict]) -> list[dict]:
    """Classify every day in chronological order, returning the payloads.

    Mirrors the backend orchestrator's per-day loop (minus the DB writes): it
    threads ``daily_range_history`` and yesterday's D1 forward so the
    expansion-factor and inside/outside-day rules see the same context.
    """
    # ADR baseline for Power-of-3 (avg full-day range across the window).
    daily_ranges: list[float] = []
    for sessions in grouped.values():
        all_day = [c for sc in sessions.values() for c in sc]
        if all_day:
            dh = max(float(c["high"]) for c in all_day)
            dl = min(float(c["low"]) for c in all_day)
            daily_ranges.append(dh - dl)
    avg_daily_range = _avg(daily_ranges)

    payloads: list[dict] = []
    daily_range_history: list[float] = []
    prev_day_key: str | None = None

    for day_key in sorted(grouped.keys()):
        sessions = grouped[day_key]
        # Need at least one session_range to classify.
        if not any(sessions.get(s) for s in ("asia", "london", "new_york")):
            prev_day_key = day_key
            continue

        rows = _build_event_rows(day_key, sessions, avg_daily_range)
        d1_today = d1_by_day.get(day_key)
        d1_prev = d1_by_day.get(prev_day_key) if prev_day_key else None

        payload = dt_engine._classify_day(
            day_key=day_key,
            d1_today=d1_today,
            d1_prev=d1_prev,
            rows=rows,
            daily_range_history=daily_range_history,
        )
        if payload is None:
            prev_day_key = day_key
            continue

        payload["event_date"] = day_key
        payloads.append(payload)
        daily_range_history.append(payload["day_range"])
        prev_day_key = day_key

    return payloads


def _pct(num: int, denom: int) -> float:
    return round(num / denom * 100, 1) if denom > 0 else 0.0


def _aggregate(payloads: list[dict]) -> dict:
    """Reproduce the ``/stats/day-type/frequency`` aggregation in memory.

    Returns the regime + archetype distribution (with per-archetype avg daily
    range / range% and last-seen date), the day-of-week breakdown, and the most
    recent classification. Every block carries a sample size ``n``.
    """
    n = len(payloads)

    arche_count: dict[str, int] = {a: 0 for a in dt_engine.ALL_ARCHETYPES}
    arche_ranges: dict[str, list[float]] = {a: [] for a in dt_engine.ALL_ARCHETYPES}
    arche_range_pcts: dict[str, list[float]] = {a: [] for a in dt_engine.ALL_ARCHETYPES}
    arche_last_seen: dict[str, str | None] = {a: None for a in dt_engine.ALL_ARCHETYPES}
    regime_count: dict[str, int] = {r: 0 for r in dt_engine.ALL_REGIMES}

    dow_arche: dict[str, dict[str, int]] = {d: defaultdict(int) for d in dt_engine.WEEKDAYS}
    dow_regime: dict[str, dict[str, int]] = {d: defaultdict(int) for d in dt_engine.WEEKDAYS}
    dow_total: dict[str, int] = {d: 0 for d in dt_engine.WEEKDAYS}

    for p in payloads:
        a = p["archetype"]
        r = p["regime"]
        if a not in arche_count:
            continue
        arche_count[a] += 1
        arche_ranges[a].append(p["day_range"])
        arche_range_pcts[a].append(p["day_range_pct"])
        arche_last_seen[a] = p["event_date"]
        if r in regime_count:
            regime_count[r] += 1
        dow = p["day_of_week"]
        if dow in dow_arche:
            dow_arche[dow][a] += 1
            if r in regime_count:
                dow_regime[dow][r] += 1
            dow_total[dow] += 1

    regimes_payload = {
        name: {"count": cnt, "pct": _pct(cnt, n)}
        for name, cnt in regime_count.items()
    }

    archetypes_payload = [
        {
            "name": a,
            "regime": dt_engine.REGIME_BY_ARCHETYPE[a],
            "count": arche_count[a],
            "pct": _pct(arche_count[a], n),
            "avg_range": round(_avg(arche_ranges[a]), 6),
            "avg_range_pct": round(_avg(arche_range_pcts[a]), 3),
            "last_seen_date": arche_last_seen[a],
        }
        for a in dt_engine.ALL_ARCHETYPES
    ]
    archetypes_payload.sort(key=lambda x: x["pct"], reverse=True)

    by_dow_payload: dict[str, dict] = {}
    for dow in dt_engine.WEEKDAYS:
        if dow_total[dow] == 0:
            continue
        top_arche = max(dow_arche[dow].items(), key=lambda kv: kv[1])
        top_regime = max(dow_regime[dow].items(), key=lambda kv: kv[1])
        by_dow_payload[dow] = {
            "top_archetype": top_arche[0],
            "top_regime": top_regime[0],
            "count": dow_total[dow],
        }

    return {
        "n": n,
        "regimes": regimes_payload,
        "archetypes": archetypes_payload,
        "by_day_of_week": by_dow_payload,
    }


def register(mcp) -> None:
    @mcp.tool()
    async def compute_day_type_stats(symbol: str = "BTCUSDT", days: int = 90) -> dict:
        """Classify each trading day and report how often each day-type occurs.

        Fetches deep 1H history from Binance (public, no API key), reconstructs
        the per-day session events the hosted product persists, then classifies
        every UTC day into one of 11 archetypes grouped into 4 regimes using the
        SAME deterministic rule engine — and aggregates the result for the model
        to interpret:

        - **trend** — ``asia_breakout_continuation``,
          ``london_breakout_continuation``, ``ny_breakout_continuation`` (a
          session expands in the day's direction and the next session continues).
        - **london_reverse** — ``asia_high_london_reversal`` /
          ``asia_low_london_reversal`` (London sweeps an Asia extreme then
          reverses).
        - **high_volatile** — ``power_of_3_long`` / ``power_of_3_short`` (AMD
          distribution) and ``double_sweep_expansion`` (both Asia and London
          swept).
        - **rare** — ``inside_day`` / ``outside_day`` (vs the prior day's range)
          and ``consolidation_drift`` (low-volatility catch-all).

        Each archetype carries its share of days (``pct``), average daily range
        and range%, and last-seen date; regimes carry their distribution; and a
        per-weekday breakdown shows the dominant archetype/regime for each day of
        week. ``today`` is the most recent classification.

        IMPORTANT — sample window: the hosted product classifies over its FULL
        candle history, but this tool only samples the last ``days`` days it
        fetches live (default ~90). The distribution here is a recent snapshot
        and will differ from the dashboard's long-run figures; cite the sample
        size (``day_types.n``) when interpreting, and treat any archetype with a
        handful of occurrences as noisy. Also note: D1 candles are synthesised
        from 1H bars (open=first, close=last, H/L = max/min), which can shift
        inside/outside-day edges vs the true daily candle.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex/metals (e.g. ``EUR_USD``,
                ``XAU_USD``) ARE supported when ``RF_OANDA_TOKEN`` is set;
                crypto needs no key.
            days: Lookback window in days (1H candles), capped at 180. ~60+ days
                gives a stable distribution.

        Returns:
            A dict with ``symbol``; ``window`` (``candles``, ``from``, ``to``
            ISO-UTC, ``days`` of coverage, ``note``); ``day_types`` (``n``,
            ``regimes`` distribution, ``archetypes`` list with pct/avg range,
            ``by_day_of_week``); and ``today`` (the latest day's full payload).
            On failure, a dict with an ``error`` key.
        """
        days = max(1, min(int(days), _MAX_DAYS))
        total = days * 24
        max_pages = max(2, (total // 1000) + 2)

        try:
            raw = await market.fetch_candles_paged(symbol, "1h", total=total, max_pages=max_pages)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not raw:
            return {"error": f"No candle data returned for {symbol}."}

        candles = _adapt_candles(raw)
        grouped = sess_engine._group_by_day_and_session(candles)

        # Synthesise a D1 candle per UTC day from that day's full 1H run (all
        # hours, including the 21:00–24:00 window the sessions ignore).
        by_full_day: dict[str, list[dict]] = defaultdict(list)
        for c in candles:
            by_full_day[c["timestamp"].strftime("%Y-%m-%d")].append(c)
        d1_by_day = {d: _synth_d1(cs) for d, cs in by_full_day.items()}

        payloads = _classify_history(grouped, d1_by_day)

        if len(payloads) < _MIN_DAYS:
            return {
                "error": (
                    f"Only {len(payloads)} classifiable days for {symbol.upper()} "
                    f"(got {len(raw)} 1H candles) — need at least {_MIN_DAYS} days "
                    "for a meaningful day-type distribution. Try more days."
                )
            }

        agg = _aggregate(payloads)
        today = payloads[-1] if payloads else None

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
                "classified_days": len(payloads),
                "note": (
                    "Recent live sample only — the hosted product classifies full "
                    "history, so this distribution differs from the dashboard. "
                    "D1 candles are synthesised from 1H bars."
                ),
            },
            "day_types": agg,
            "today": today,
        }
