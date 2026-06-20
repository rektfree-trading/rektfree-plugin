"""
``compute_pdh_pdl_stats`` — on-the-fly PDH/PDL touch statistics (crypto, keyless).

Fetches deep 1H + daily Binance history, runs the vendored pure-Python PDH/PDL
detector per UTC day (does today's price touch the *previous day's* high/low?),
then aggregates the resulting in-memory events into the same shape the hosted
``/stats/pdh-pdl`` router produces from persisted ``pdh_pdl_touch`` rows — sweep
rate of PDH / PDL, the outcome mix (pdh_only / pdl_only / both / neither),
hold-vs-reversal after a sweep, average touch times, and a day-of-week
breakdown.

The hosted product aggregates over its FULL candle history; this tool samples
only the last ~N days fetched live, so the rates will differ from the dashboard.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from data import binance
from engines import pdh_pdl_stats as engine
from tools._common import crypto_only_error

# Cap the lookback so a single call stays polite to Binance's rate limits.
_MAX_DAYS = 180
_MIN_DAYS = 10  # below this the rates are meaningless


def _adapt_candles(raw: list[dict]) -> list[dict]:
    """Reshape Binance candles for the detectors.

    The detectors read ``c["timestamp"]`` as a tz-aware UTC ``datetime`` (they
    call ``.date()``/``.hour``/``.minute``/``.weekday()``); the fetcher returns a
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


def _rate(num: int, den: int) -> float:
    return round(num / den * 100, 1) if den else 0.0


def _avg_minute(times: list[str]) -> str | None:
    """Average a list of ``HH:MM`` strings into an ``HH:MM`` time-of-day."""
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


def _build_events(
    d1_candles: list[dict],
    h1_candles: list[dict],
) -> list[dict]:
    """Run the touch detector across every day with a prior D1 + intraday 1H.

    Mirrors the backend's ``compute_pdh_pdl`` per-day loop minus the DB writes.
    """
    pdh_pdl_lookup = engine._build_pdh_pdl_lookup(d1_candles)
    d1_dates_sorted = sorted(pdh_pdl_lookup.keys())
    h1_by_day = engine._group_h1_by_day(h1_candles)

    events: list[dict] = []
    for today in sorted(h1_by_day.keys()):
        levels = engine._prior_d1_levels(today, d1_dates_sorted, pdh_pdl_lookup)
        if levels is None:
            continue  # no prior day to reference
        pdh, pdl = levels
        ev = engine.detect_pdh_pdl_touch(today, h1_by_day[today], pdh, pdl)
        if ev:
            events.append(ev)
    return events


def _agg_side(events: list[dict], side: str) -> dict:
    """Sweep / hold / reversal aggregation for one side (PDH or PDL).

    ``side`` is ``"pdh"`` or ``"pdl"``. ``n`` is the number of days evaluated
    (every day had a level to test). ``sweep_rate`` = % of days price reached the
    level; ``reversal_rate``/``hold_rate`` are conditioned on the sweep happening.
    """
    n = len(events)
    touched_key = f"touched_{side}"
    reversal_key = f"{side}_reversal"
    held_key = f"{side}_held"
    time_key = f"{side}_touch_time"

    swept = sum(1 for e in events if e[touched_key])
    reversals = sum(1 for e in events if e[reversal_key])
    holds = sum(1 for e in events if e[held_key])
    touch_times = [e[time_key] for e in events if e[touched_key] and e[time_key]]

    return {
        "n": n,
        "sweep_rate": _rate(swept, n),
        "sweep_count": swept,
        "reversal_rate_when_swept": _rate(reversals, swept),
        "hold_rate_when_swept": _rate(holds, swept),
        "avg_touch_time": _avg_minute(touch_times),
    }


def _agg_outcomes(events: list[dict]) -> dict:
    """Mutually-exclusive outcome mix, mirroring the router's outcome block."""
    n = len(events)
    counts = {"pdh_only": 0, "pdl_only": 0, "both": 0, "neither": 0}
    for e in events:
        counts[e["outcome"]] += 1
    return {
        "n": n,
        "pdh_only_pct": _rate(counts["pdh_only"], n),
        "pdl_only_pct": _rate(counts["pdl_only"], n),
        "both_pct": _rate(counts["both"], n),
        "neither_pct": _rate(counts["neither"], n),
    }


def _agg_day_of_week(events: list[dict]) -> dict:
    """Per-weekday touch fractions, mirroring the router's by_day_of_week."""
    by_dow: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_dow[e["day_of_week"]].append(e)
    out: dict[str, dict] = {}
    for dow in engine.WEEKDAYS:
        rows = by_dow.get(dow)
        if not rows:
            continue
        cnt = len(rows)
        out[dow] = {
            "count": cnt,
            "pdh_pct": _rate(sum(1 for r in rows if r["touched_pdh"]), cnt),
            "pdl_pct": _rate(sum(1 for r in rows if r["touched_pdl"]), cnt),
            "both_pct": _rate(sum(1 for r in rows if r["outcome"] == "both"), cnt),
            "neither_pct": _rate(sum(1 for r in rows if r["outcome"] == "neither"), cnt),
        }
    return out


def register(mcp) -> None:
    @mcp.tool()
    async def compute_pdh_pdl_stats(symbol: str = "BTCUSDT", days: int = 90) -> dict:
        """Compute previous-day-high / previous-day-low touch stats for a crypto symbol.

        Fetches deep 1H + daily candles from Binance (public, no API key). For
        each UTC day it takes the *previous* day's high (PDH) and low (PDL) and
        checks whether today's intraday price reached them — exactly the touch
        rule the hosted product uses — then aggregates the events the way the
        ``/stats/pdh-pdl`` dashboard does. Returns structured JSON for the model
        to interpret: how often PDH / PDL get swept, the outcome mix
        (pdh_only / pdl_only / both / neither), whether a sweep tends to *reverse*
        (rejection / liquidity grab) or *hold* (acceptance / breakout), when the
        sweeps tend to happen, and a day-of-week breakdown.

        IMPORTANT — sample window: the hosted product aggregates over its FULL
        candle history, but this tool only samples the last ``days`` days it
        fetches live (default ~90). Rates here are a recent snapshot and will
        differ from the dashboard's long-run figures; cite the sample size
        (``window.days`` / each block's ``n``) when interpreting.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex pairs (with ``_``) are not
                supported in this slice.
            days: Lookback window in days, capped at 180. ~30+ days gives stable
                rates; the level convention is the UTC calendar day (00:00 UTC).

        Returns:
            A dict with ``symbol``; ``window`` (``candles``, ``from``, ``to``
            ISO-UTC, ``days`` of coverage); ``pdh`` and ``pdl`` (each with
            ``sweep_rate``, ``reversal_rate_when_swept``, ``hold_rate_when_swept``,
            ``avg_touch_time``, and sample size ``n``); ``outcomes`` (the mutually
            exclusive mix); and ``day_of_week``. On failure, a dict with an
            ``error`` key.
        """
        if err := crypto_only_error(symbol):
            return err

        days = max(1, min(int(days), _MAX_DAYS))
        total_h1 = days * 24
        max_pages = max(2, (total_h1 // 1000) + 2)
        # Need one extra daily candle for the prior-day reference; pad a little.
        total_d1 = days + 5

        try:
            raw_h1 = await binance.fetch_candles_paged(
                symbol, "1h", total=total_h1, max_pages=max_pages
            )
            raw_d1 = await binance.fetch_candles(symbol, "1d", min(total_d1, 1000))
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not raw_h1 or not raw_d1:
            return {"error": f"No candle data returned for {symbol}."}

        h1 = _adapt_candles(raw_h1)
        d1 = _adapt_candles(raw_d1)
        events = _build_events(d1, h1)

        if len(events) < _MIN_DAYS:
            return {
                "error": (
                    f"Only {len(events)} comparable days for {symbol.upper()} — "
                    f"need at least {_MIN_DAYS} to compute meaningful PDH/PDL rates. "
                    "Try a longer window or a different symbol."
                )
            }

        from_iso = datetime.fromtimestamp(raw_h1[0]["time"], tz=timezone.utc).isoformat()
        to_iso = datetime.fromtimestamp(raw_h1[-1]["time"], tz=timezone.utc).isoformat()
        span_days = max(1, round((raw_h1[-1]["time"] - raw_h1[0]["time"]) / 86400))

        return {
            "symbol": symbol.upper(),
            "window": {
                "candles": len(raw_h1),
                "from": from_iso,
                "to": to_iso,
                "days": span_days,
                "rth_convention": "utc_day",
                "note": (
                    "Recent live sample only — the hosted product uses full history, "
                    "so these rates differ from the dashboard."
                ),
            },
            "pdh": _agg_side(events, "pdh"),
            "pdl": _agg_side(events, "pdl"),
            "outcomes": _agg_outcomes(events),
            "day_of_week": _agg_day_of_week(events),
        }
