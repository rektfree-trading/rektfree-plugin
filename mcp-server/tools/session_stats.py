"""
``compute_session_stats`` — on-the-fly session statistics (crypto, keyless).

Fetches deep 1H Binance history, runs the vendored pure-Python session detectors
per day/session, then aggregates the resulting in-memory events into the same
shape the hosted ``/stats/sessions`` router produces from persisted
``SessionEvent`` rows — avg range & range% per session, direction %, Asia→London
and London→NY sweep rates, NY continuation rate, Power-of-3 occurrence rate, and
a day-of-week breakdown.

The hosted product aggregates over its FULL candle history; this tool samples
only the last ~N days fetched live, so the rates will differ from the dashboard.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from data import binance
from engines import session_stats as engine
from tools._common import crypto_only_error

# Cap the lookback so a single call stays polite to Binance's rate limits.
# 180 days × 24h = 4320 1H candles ≈ 5 paged requests (1000/page).
_MAX_DAYS = 365
_MIN_CANDLES = 48  # backend's floor; below this aggregation is meaningless


def _adapt_candles(raw: list[dict]) -> list[dict]:
    """Reshape Binance candles for the detectors.

    The detectors read ``c["timestamp"]`` as a timezone-aware UTC ``datetime``
    (they call ``.strftime``/``.hour``/``.weekday()``); the fetcher returns a
    float unix-second ``time``. Convert each candle once here.
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


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _build_events(grouped: dict[str, dict[str, list[dict]]]) -> dict:
    """Run the detectors across every day/session (mirrors the orchestrator).

    Reproduces the per-day loop the backend's ``compute_session_stats`` runs —
    minus the DB writes — collecting events in memory for aggregation.
    """
    # Average daily range (all sessions combined) for Power-of-3 ADR baseline.
    daily_ranges: list[float] = []
    for sessions in grouped.values():
        all_day = [c for sc in sessions.values() for c in sc]
        if all_day:
            dh = max(float(c["high"]) for c in all_day)
            dl = min(float(c["low"]) for c in all_day)
            daily_ranges.append(dh - dl)
    avg_daily_range = _avg(daily_ranges)

    ranges: dict[str, list[dict]] = {"asia": [], "london": [], "new_york": []}
    asia_sweeps: list[dict] = []
    london_sweeps: list[dict] = []
    ny_conts: list[dict] = []
    p3s: list[dict] = []

    for day_key in sorted(grouped.keys()):
        sessions = grouped[day_key]
        asia_c = sessions.get("asia", [])
        london_c = sessions.get("london", [])
        ny_c = sessions.get("new_york", [])

        for sess_name in ("asia", "london", "new_york"):
            ev = engine._compute_session_range(sessions.get(sess_name, []), sess_name, day_key, "")
            if ev:
                ranges[sess_name].append(ev["data"])

        sweep = engine._detect_sweep(asia_c, london_c, "asia", "london", day_key)
        if sweep:
            asia_sweeps.append(sweep["data"])

        sweep = engine._detect_sweep(london_c, ny_c, "london", "new_york", day_key)
        if sweep:
            london_sweeps.append(sweep["data"])

        cont = engine._detect_ny_continuation(london_c, ny_c, day_key)
        if cont:
            ny_conts.append(cont["data"])

        p3 = engine._detect_power_of_3(asia_c, london_c, ny_c, avg_daily_range, day_key)
        if p3:
            p3s.append(p3["data"])

    return {
        "ranges": ranges,
        "asia_sweeps": asia_sweeps,
        "london_sweeps": london_sweeps,
        "ny_conts": ny_conts,
        "p3s": p3s,
    }


def _agg_sessions(ranges: dict[str, list[dict]]) -> dict:
    """Per-session avg range/range% + direction %, mirroring the router SQL.

    Reproduces ``/summary``'s ``range_stats`` block: avg_range, avg_range_pct,
    bullish/bearish %, and avg range split by direction.
    """
    out: dict[str, dict] = {}
    for sess, rows in ranges.items():
        if not rows:
            continue
        total = len(rows)
        bull = [r for r in rows if r["direction"] == "bullish"]
        out[sess] = {
            "total_sessions": total,
            "avg_range": round(_avg([r["range"] for r in rows]), 6),
            "avg_range_pct": round(_avg([r["range_pct"] for r in rows]), 3),
            "bullish_pct": round(len(bull) / total * 100, 1),
            "bearish_pct": round((total - len(bull)) / total * 100, 1),
            "avg_bull_range": round(_avg([r["range"] for r in bull]), 6),
            "avg_bear_range": round(_avg([r["range"] for r in rows if r["direction"] == "bearish"]), 6),
        }
    return out


def _agg_sweeps(sweeps: list[dict], total_days: int) -> dict:
    """Sweep rate / side breakdown / reversal rate, mirroring the router SQL.

    ``total_days`` = days the prior session existed (the SQL denominator is
    ``COUNT(DISTINCT event_date)`` over the prior session's range events).
    """
    if total_days <= 0:
        return {}
    sweep_count = len(sweeps)
    swept_high = sum(1 for s in sweeps if s["swept_side"] == "high")
    swept_low = sum(1 for s in sweeps if s["swept_side"] == "low")
    swept_both = sum(1 for s in sweeps if s["swept_side"] == "both")
    reversals = sum(1 for s in sweeps if s["reversal"])
    return {
        "total_days": total_days,
        "sweep_count": sweep_count,
        "sweep_rate": round(sweep_count / total_days * 100, 1),
        "swept_high": swept_high,
        "swept_low": swept_low,
        "swept_both": swept_both,
        "reversal_rate": round(reversals / max(sweep_count, 1) * 100, 1),
    }


def _agg_ny_continuation(ny_conts: list[dict]) -> dict:
    if not ny_conts:
        return {}
    total = len(ny_conts)
    cont = sum(1 for r in ny_conts if r["continuation"])
    return {
        "total_days": total,
        "continuation_count": cont,
        "continuation_rate": round(cont / total * 100, 1),
        "reversal_rate": round((total - cont) / total * 100, 1),
    }


def _agg_power_of_3(p3s: list[dict], p3_eligible_days: int) -> dict:
    """Power-of-3 success + occurrence rate.

    ``occurrence_rate`` (a plugin-added field, no SQL equivalent) is how often
    the full AMD pattern even formed, over days that had both Asia + London.
    """
    if not p3s:
        return {}
    total = len(p3s)
    success = sum(1 for r in p3s if r["distribution_success"])
    out = {
        "total_patterns": total,
        "success_count": success,
        "success_rate": round(success / total * 100, 1),
        "swept_high": sum(1 for r in p3s if r["manipulation_side"] == "high"),
        "swept_low": sum(1 for r in p3s if r["manipulation_side"] == "low"),
        "avg_asia_range_pct": round(_avg([r["asia_range_pct_of_adr"] for r in p3s]), 1),
    }
    if p3_eligible_days > 0:
        out["eligible_days"] = p3_eligible_days
        out["occurrence_rate"] = round(total / p3_eligible_days * 100, 1)
    return out


def _agg_day_of_week(ranges: dict[str, list[dict]]) -> dict:
    """Per-session, per-weekday range + direction, mirroring ``/extended``."""
    out: dict[str, list] = {}
    for sess, rows in ranges.items():
        if not rows:
            continue
        by_dow: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_dow[r["day_of_week"]].append(r)
        entries = []
        for dow in engine.WEEKDAYS:
            drows = by_dow.get(dow)
            if not drows:
                continue
            cnt = len(drows)
            bull = sum(1 for r in drows if r["direction"] == "bullish")
            entries.append({
                "day": dow,
                "count": cnt,
                "avg_range": round(_avg([r["range"] for r in drows]), 6),
                "avg_range_pct": round(_avg([r["range_pct"] for r in drows]), 3),
                "bullish_pct": round(bull / max(cnt, 1) * 100, 1),
            })
        if entries:
            out[sess] = entries
    return out


def register(mcp) -> None:
    @mcp.tool()
    async def compute_session_stats(symbol: str = "BTCUSDT", days: int = 180) -> dict:
        """Compute session statistics for a crypto symbol from live history.

        Fetches deep 1H candles from Binance (public, no API key), buckets them
        into Asia/London/New York sessions per UTC day, and runs the same
        detectors the hosted product uses — then aggregates the events the way
        the ``/stats/sessions`` dashboard does. Returns structured JSON for the
        model to interpret: which session is most volatile, how often London
        sweeps Asia (and which side), whether NY tends to continue or reverse
        London, how often the Power-of-3 pattern completes, and how all of that
        breaks down by day of week.

        IMPORTANT — sample window: the hosted product aggregates over its FULL
        candle history (often a year+), but this tool only samples the last
        ``days`` days it fetches live (default ~180). Rates here are a recent
        snapshot and will differ from the dashboard's long-run figures; cite the
        sample size (``window.days``) when interpreting.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex pairs (with ``_``) are not
                supported in this slice.
            days: Lookback window in days (1H candles), capped at 365. Each day
                yields up to 3 session events; ~60+ days gives stable rates,
                and the deeper default (~180) tightens them further.

        Returns:
            A dict with ``symbol``; ``window`` (``candles``, ``from``, ``to``
            ISO-UTC, ``days`` of actual coverage); ``sessions`` (per-session
            avg range/range%, direction %); ``sweeps`` (``asia_sweep`` =
            London-swept-Asia, ``london_sweep`` = NY-swept-London, each with
            ``sweep_rate``/side counts/``reversal_rate``); ``ny_continuation``
            (continuation vs reversal rate); ``power_of_3`` (success +
            occurrence rate); and ``day_of_week`` (per-session weekday
            breakdown). On failure, a dict with an ``error`` key.
        """
        if err := crypto_only_error(symbol):
            return err

        days = max(1, min(int(days), _MAX_DAYS))
        total = days * 24
        # ~1000 candles/page; pad max_pages so the full window is fetchable.
        max_pages = max(2, (total // 1000) + 2)

        try:
            raw = await binance.fetch_candles_paged(symbol, "1h", total=total, max_pages=max_pages)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if len(raw) < _MIN_CANDLES:
            return {
                "error": (
                    f"Not enough candle data for {symbol}: got {len(raw)} 1H candles, "
                    f"need at least {_MIN_CANDLES}. Try a different symbol or fewer days."
                )
            }

        candles = _adapt_candles(raw)
        grouped = engine._group_by_day_and_session(candles)
        events = _build_events(grouped)

        # Denominators (mirror the router's COUNT(DISTINCT event_date) per prior session).
        asia_days = len(events["ranges"]["asia"])
        london_days = len(events["ranges"]["london"])
        # Power-of-3 is eligible on days that had both Asia and London candles.
        p3_eligible = sum(
            1 for s in grouped.values() if s.get("asia") and s.get("london")
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
                "note": (
                    "Recent live sample only — the hosted product uses full history, "
                    "so these rates differ from the dashboard."
                ),
            },
            "sessions": _agg_sessions(events["ranges"]),
            "sweeps": {
                "asia_sweep": _agg_sweeps(events["asia_sweeps"], asia_days),
                "london_sweep": _agg_sweeps(events["london_sweeps"], london_days),
            },
            "ny_continuation": _agg_ny_continuation(events["ny_conts"]),
            "power_of_3": _agg_power_of_3(events["p3s"], p3_eligible),
            "day_of_week": _agg_day_of_week(events["ranges"]),
        }
