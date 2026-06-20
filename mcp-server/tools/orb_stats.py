"""
``compute_orb_stats`` — on-the-fly Opening Range Breakout statistics (keyless).

Fetches deep 5m Binance (or OANDA forex) history, runs the vendored pure-Python
ORB detector per RTH trading day, then aggregates the in-memory events the way
the hosted ``/stats/orb`` router does from persisted ``orb_period`` rows —
first-break-side distribution (high / low / none), two-sided-break rate, the
breakout outcome mix (only_h / only_l / both / neither), and ORB-size + up/down
extension distributions (raw and as multiples of the opening range).

The opening range is the first ``orb_minutes`` of the symbol's RTH session.
For 24/7 crypto the RTH open is a *synthetic* convention pinned to the US
equities open (13:30 UTC) — ORB is most meaningful on forex/indices, which have
a real cash open. 5m paging is heavy (288 candles/day), so the window is capped
modestly and the live sample is shallower than the dashboard's full history.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean

from data import binance
from data import market
from engines import orb_stats as engine

# 5m ORB resolution is data-heavy (288 candles/day). Cap the window so a single
# call stays polite. ~120 days × 288 ≈ 35k candles ≈ 35 paged requests; the hard
# cap of 180 keeps the heaviest call bounded.
_DEFAULT_DAYS = 120
_MAX_DAYS = 180
_MIN_DAYS = 5  # below this the rates are meaningless


def _adapt_candles(raw: list[dict]) -> list[dict]:
    """Reshape fetched candles for the detectors (float ``time`` → tz-aware UTC
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


def build_events(symbol: str, m5: list[dict], orb_minutes: int) -> list[dict]:
    """Run the ORB detector across every day (mirrors the backend per-day loop)."""
    convention_name, windows = engine.convention_for(symbol)
    by_day = _group_by_day(m5)
    events: list[dict] = []
    for day in sorted(by_day.keys()):
        data = engine.compute_orb_for_day(
            symbol=symbol,
            day=day,
            candles_today=by_day[day],
            convention_name=convention_name,
            windows=windows,
            orb_minutes=orb_minutes,
        )
        if data:
            events.append(data)
    return events


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
            "avg_orb_size": round(mean(r["orb_size"] for r in rows), 6),
            "neither_pct": round(sum(1 for r in rows if r["outcome"] == "neither") / cnt * 100, 1),
            "both_pct": round(sum(1 for r in rows if r["outcome"] == "both") / cnt * 100, 1),
        }
    return out


def register(mcp) -> None:
    @mcp.tool()
    async def compute_orb_stats(
        symbol: str = "BTCUSDT", days: int = 120, orb_minutes: int = 15
    ) -> dict:
        """Compute Opening Range Breakout (ORB) statistics for a symbol.

        Fetches deep 5m candles (Binance for crypto — public, no API key; OANDA
        for forex/indices when ``RF_OANDA_TOKEN`` is set). For each RTH trading
        day it builds the **opening range** — the high/low of the first
        ``orb_minutes`` of the session — then walks the rest of the session
        (post-ORB, through RTH-end) to record which side breaks first, whether
        BOTH sides break, the resulting outcome (only_h / only_l / both /
        neither), and how far price extends beyond the range. It aggregates the
        events exactly the way the hosted ``/stats/orb`` dashboard does. Returns
        structured JSON for the model to interpret: how often the opening range
        breaks (and which way first), how often it holds, and how far breakouts
        run as multiples of the range.

        IMPORTANT — synthetic open for crypto: for 24/7 crypto the RTH "open" is
        a *synthetic* convention pinned to the US equities open (13:30 UTC), so
        ORB is most meaningful on **forex/indices**, which have a true cash open.
        It is still computed for crypto, just interpret with that caveat.

        IMPORTANT — sample window: the hosted product aggregates over its FULL
        candle history; this tool only samples the last ``days`` days it fetches
        live. 5m history is heavy (288 candles/day), so ``days`` defaults to 120
        and is hard-capped at 180. Cite the sample size (each block's ``n``) when
        interpreting.

        Args:
            symbol: Symbol — crypto with no separator (``BTCUSDT``, ``ETHUSDT``),
                or underscore-separated forex/index (``EUR_USD``, ``XAU_USD``,
                ``NAS100_USD``) when ``RF_OANDA_TOKEN`` is set.
            days: Lookback window in days, capped at 180 (5m data is heavy).
                ~60+ days gives a stable sample.
            orb_minutes: Length of the opening range in minutes (default 15).
                Resolved on 5m candles, so multiples of 5 work cleanly.

        Returns:
            A dict with ``symbol``; ``window`` (``candles``, ``from``, ``to``
            ISO-UTC, ``days`` of coverage, ``orb_days``, ``orb_window_utc``,
            ``rth_convention``); ``breakouts`` (outcome mix, ``breakout_rate``,
            ``orb_hold_rate``, first-break side, ``two_side_pct``,
            ``avg_first_break_time``, ``n``, ``confidence``); ``extension``
            (ORB size + up/down extension distributions, raw and as multiples of
            the range, each with ``sample_size``/``confidence``); and
            ``day_of_week``. On failure, a dict with an ``error`` key.
        """
        days = max(1, min(int(days), _MAX_DAYS))
        orb_minutes = max(1, int(orb_minutes))
        total_m5 = days * 288  # 288 five-minute candles per day
        m5_pages = max(2, min(40, (total_m5 // 1000) + 2))

        try:
            raw_m5 = await market.fetch_candles_paged(
                symbol, "5m", total=total_m5, max_pages=m5_pages
            )
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not raw_m5:
            return {"error": f"No 5m candle data returned for {symbol}."}

        m5 = _adapt_candles(raw_m5)
        events = build_events(symbol.upper(), m5, orb_minutes)

        if len(events) < _MIN_DAYS:
            return {
                "error": (
                    f"Only {len(events)} ORB days for {symbol.upper()} — need at "
                    f"least {_MIN_DAYS} to compute meaningful ORB rates. Try a "
                    "longer window or a different symbol."
                )
            }

        from_iso = datetime.fromtimestamp(raw_m5[0]["time"], tz=timezone.utc).isoformat()
        to_iso = datetime.fromtimestamp(raw_m5[-1]["time"], tz=timezone.utc).isoformat()
        span_days = max(1, round((raw_m5[-1]["time"] - raw_m5[0]["time"]) / 86400))
        convention_name, _windows = engine.convention_for(symbol)
        orb_window = events[-1]["orb_window_utc"]

        return {
            "symbol": symbol.upper(),
            "window": {
                "candles_5m": len(raw_m5),
                "from": from_iso,
                "to": to_iso,
                "days": span_days,
                "orb_days": len(events),
                "orb_minutes": orb_minutes,
                "orb_window_utc": orb_window,
                "rth_convention": convention_name,
                "note": (
                    "Recent live 5m sample only — the hosted product uses full "
                    "history, so these rates differ from the dashboard. For 24/7 "
                    "crypto the RTH open is synthetic (13:30 UTC); ORB is most "
                    "meaningful on forex/indices."
                ),
            },
            "breakouts": engine.agg_breakouts(events),
            "extension": engine.agg_extension(events),
            "day_of_week": _agg_day_of_week(events),
        }
