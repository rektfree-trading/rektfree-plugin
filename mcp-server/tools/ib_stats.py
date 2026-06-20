"""
``compute_ib_stats`` — on-the-fly Initial Balance statistics (crypto, keyless).

Fetches deep 5m (with 1H fallback) Binance history, runs the vendored pure-Python
IB detector per UTC trading day (IB = the first hour of the RTH session, which is
13:30-14:30 UTC for crypto on the synthetic-NY clock), then aggregates the
resulting in-memory events into the same shape the hosted ``/stats/ib`` router
produces from persisted ``ib_period`` rows — IB-range distribution, breakout
outcome mix (only_h / only_l / both / neither), first-break side, IB-hold
(neither-broke) rate, extension distributions and the size-to-extension ratio.

The hosted product aggregates over its FULL candle history; this tool samples
only the last ~N days fetched live, so the rates will differ from the dashboard.
The IB window needs 5-minute candles to resolve its 13:30 start — 5m history is
heavy, so the live sample here is shallower than the session/PDH tools.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, median

from data import binance
from data import market
from engines import ib_stats as engine

# 5m IB resolution is data-heavy (288 candles/day). Cap the window so a single
# call stays polite — ~45 days × 288 = ~13k candles ≈ 13 paged requests.
_MAX_DAYS = 60
_DEFAULT_M5_PAGES = 16
_MIN_DAYS = 10  # below this the rates are meaningless


def _adapt_candles(raw: list[dict]) -> list[dict]:
    """Reshape Binance candles for the detectors (float ``time`` → tz-aware UTC
    ``datetime`` at ``c["timestamp"]``)."""
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


def _group_by_day(candles: list[dict]) -> dict:
    grouped: dict = defaultdict(list)
    for c in candles:
        grouped[c["timestamp"].date()].append(c)
    return grouped


def _rate(num: int, den: int) -> float:
    return round(num / den * 100, 1) if den else 0.0


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return float(sorted_values[f])
    return float(sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f))


def _dist(values: list[float], decimals: int = 6) -> dict:
    """median / mean / min / max / p25 / p75 + ``n`` — mirrors the router's
    ``extension_block`` distribution shape."""
    n = len(values)
    if n == 0:
        return {"n": 0, "median": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0,
                "p25": 0.0, "p75": 0.0}
    sv = sorted(float(v) for v in values)
    return {
        "n": n,
        "median": round(float(median(sv)), decimals),
        "mean": round(float(mean(sv)), decimals),
        "min": round(sv[0], decimals),
        "max": round(sv[-1], decimals),
        "p25": round(_percentile(sv, 0.25), decimals),
        "p75": round(_percentile(sv, 0.75), decimals),
    }


def _avg_minute(times: list[str]) -> str | None:
    mins: list[int] = []
    for t in times:
        if t and ":" in t:
            try:
                h, m = t.split(":")
                mins.append(int(h) * 60 + int(m))
            except (ValueError, TypeError):
                pass
    if not mins:
        return None
    avg = int(round(sum(mins) / len(mins)))
    avg = max(0, min(24 * 60 - 1, avg))
    return f"{avg // 60:02d}:{avg % 60:02d}"


def _build_events(symbol: str, m5: list[dict], h1: list[dict]) -> list[dict]:
    """Run the IB detector across every day (mirrors the backend per-day loop)."""
    convention_name, windows = engine.convention_for(symbol)
    m5_by_day = _group_by_day(m5)
    h1_by_day = _group_by_day(h1)

    all_days = sorted(set(m5_by_day.keys()) | set(h1_by_day.keys()))
    events: list[dict] = []
    for day in all_days:
        data = engine.compute_ib_for_day(
            symbol=symbol,
            day=day,
            m5_today=m5_by_day.get(day, []),
            h1_today=h1_by_day.get(day, []),
            convention_name=convention_name,
            windows=windows,
        )
        if data:
            events.append(data)
    return events


def _agg_breakouts(events: list[dict]) -> dict:
    """Outcome mix + first-break side + IB-hold rate, mirroring /breakouts."""
    n = len(events)
    counts = {"only_h": 0, "only_l": 0, "both": 0, "neither": 0}
    side = {"high": 0, "low": 0, "none": 0}
    break_times: list[str] = []
    for e in events:
        counts[e["outcome"]] += 1
        fbs = e.get("first_break_side")
        side[fbs if fbs in ("high", "low") else "none"] += 1
        if e.get("first_break_time"):
            break_times.append(e["first_break_time"])
    # IB held = neither side broke out (price stayed inside the opening range).
    return {
        "n": n,
        "only_h_pct": _rate(counts["only_h"], n),
        "only_l_pct": _rate(counts["only_l"], n),
        "both_pct": _rate(counts["both"], n),
        "neither_pct": _rate(counts["neither"], n),
        "breakout_rate": _rate(n - counts["neither"], n),
        "ib_hold_rate": _rate(counts["neither"], n),
        "first_break_high_pct": _rate(side["high"], n),
        "first_break_low_pct": _rate(side["low"], n),
        "first_break_none_pct": _rate(side["none"], n),
        "avg_first_break_time": _avg_minute(break_times),
    }


def _agg_extension(events: list[dict]) -> dict:
    """IB size + extension distributions + size/extension ratio, mirroring
    /extension and /size-extension-ratio."""
    ib_size = [e["ib_size"] for e in events if e.get("ib_size") is not None]
    ib_size_pct = [e["ib_size_pct"] for e in events if e.get("ib_size_pct") is not None]
    up = [e["ib_up_extension"] for e in events if e.get("ib_up_extension") is not None]
    down = [e["ib_down_extension"] for e in events if e.get("ib_down_extension") is not None]
    mx = [e["max_extension"] for e in events if e.get("max_extension") is not None]
    ratio = [e["size_to_extension_ratio"] for e in events
             if e.get("size_to_extension_ratio") is not None]
    return {
        "n": len(events),
        "ib_size": _dist(ib_size),
        "ib_size_pct": _dist(ib_size_pct, decimals=3),
        "ib_up_extension": _dist(up),
        "ib_down_extension": _dist(down),
        "max_extension": _dist(mx),
        "size_to_extension_ratio": _dist(ratio, decimals=3),
    }


def _agg_day_of_week(events: list[dict]) -> dict:
    by_dow: dict = defaultdict(list)
    for e in events:
        by_dow[e["day_of_week"]].append(e)
    out: dict = {}
    for dow in engine.WEEKDAYS:
        rows = by_dow.get(dow)
        if not rows:
            continue
        cnt = len(rows)
        out[dow] = {
            "count": cnt,
            "avg_ib_size_pct": round(mean(r["ib_size_pct"] for r in rows), 3),
            "neither_pct": _rate(sum(1 for r in rows if r["outcome"] == "neither"), cnt),
            "both_pct": _rate(sum(1 for r in rows if r["outcome"] == "both"), cnt),
        }
    return out


def register(mcp) -> None:
    @mcp.tool()
    async def compute_ib_stats(symbol: str = "BTCUSDT", days: int = 90) -> dict:
        """Compute Initial Balance (opening-range) statistics for a crypto symbol.

        Fetches deep 5m (with 1H fallback) candles from Binance (public, no API
        key). For each UTC trading day it measures the **Initial Balance** — the
        first hour of the RTH session, 13:30-14:30 UTC for crypto on the
        synthetic-NY clock — then walks the rest of the session (post-IB, to
        20:00 UTC) to record breakouts and extensions, exactly the way the hosted
        product does, and aggregates the events the way the ``/stats/ib``
        dashboard does. Returns structured JSON for the model to interpret: how
        wide the opening range typically is, how often it breaks (above / below /
        both / neither), which side breaks first, how far price extends beyond
        the IB, and how often the IB simply *holds* (price never breaks out).

        IMPORTANT — sample window: the hosted product aggregates over its FULL
        candle history; this tool only samples the last ``days`` days it fetches
        live. The IB window needs 5-minute candles to resolve its 13:30 start, and
        5m history is heavy, so the window is capped at 60 days and the live
        sample is shallower than the session/PDH tools. Cite the sample size
        (each block's ``n``) when interpreting.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex/metals (e.g. ``EUR_USD``,
                ``XAU_USD``) ARE supported when ``RF_OANDA_TOKEN`` is set;
                crypto needs no key.
            days: Lookback window in days, capped at 60 (5m data is heavy).
                ~30+ days gives stable rates.

        Returns:
            A dict with ``symbol``; ``window`` (``candles``, ``from``, ``to``
            ISO-UTC, ``days`` of coverage, ``ib_window_utc``); ``breakouts``
            (outcome mix, ``breakout_rate``, ``ib_hold_rate``, first-break side,
            ``avg_first_break_time``, ``n``); ``extension`` (IB size + up/down/max
            extension + size-to-extension ratio distributions, each with ``n``);
            and ``day_of_week``. On failure, a dict with an ``error`` key.
        """
        days = max(1, min(int(days), _MAX_DAYS))
        total_m5 = days * 288  # 288 five-minute candles per day
        m5_pages = max(2, min(_DEFAULT_M5_PAGES, (total_m5 // 1000) + 2))
        total_h1 = days * 24
        h1_pages = max(2, (total_h1 // 1000) + 2)

        try:
            raw_m5 = await market.fetch_candles_paged(
                symbol, "5m", total=total_m5, max_pages=m5_pages
            )
            raw_h1 = await market.fetch_candles_paged(
                symbol, "1h", total=total_h1, max_pages=h1_pages
            )
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not raw_m5 and not raw_h1:
            return {"error": f"No candle data returned for {symbol}."}

        m5 = _adapt_candles(raw_m5)
        h1 = _adapt_candles(raw_h1)
        events = _build_events(symbol.upper(), m5, h1)

        if len(events) < _MIN_DAYS:
            return {
                "error": (
                    f"Only {len(events)} IB days for {symbol.upper()} — need at "
                    f"least {_MIN_DAYS} to compute meaningful IB rates. Try a "
                    "longer window or a different symbol."
                )
            }

        # Window reporting: prefer the (denser) 5m series; fall back to 1H.
        ref = raw_m5 if raw_m5 else raw_h1
        from_iso = datetime.fromtimestamp(ref[0]["time"], tz=timezone.utc).isoformat()
        to_iso = datetime.fromtimestamp(ref[-1]["time"], tz=timezone.utc).isoformat()
        span_days = max(1, round((ref[-1]["time"] - ref[0]["time"]) / 86400))
        convention_name, windows = engine.convention_for(symbol)
        ib_window = f"{windows['ib'][0]}-{windows['ib'][1]}"

        # Source mix — how many days resolved on 5m vs the 1H fallback.
        src_5m = sum(1 for e in events if e.get("candle_source") == "5m")

        return {
            "symbol": symbol.upper(),
            "window": {
                "candles_5m": len(raw_m5),
                "candles_1h": len(raw_h1),
                "from": from_iso,
                "to": to_iso,
                "days": span_days,
                "ib_days": len(events),
                "ib_window_utc": ib_window,
                "rth_convention": convention_name,
                "candle_source_5m_days": src_5m,
                "note": (
                    "Recent live sample only — the hosted product uses full history, "
                    "so these rates differ from the dashboard."
                ),
            },
            "breakouts": _agg_breakouts(events),
            "extension": _agg_extension(events),
            "day_of_week": _agg_day_of_week(events),
        }
