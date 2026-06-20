"""
``compute_eth_profile_stats`` — on-the-fly ETH Profile / prev-VA-POC test.

Fetches deep 15m + 1H history (Binance keyless, or OANDA forex), builds a daily
RTH-bounded TPO/volume profile per day (REUSING the vendored ``market_profile``
engine), captures each day's POC / VAH / VAL, then walks the NEXT day's intraday
1H candles to measure how often price touches the PRIOR day's POC / VAH / VAL —
plus the average touch time within the day and an RTH-range distribution. It
aggregates the in-memory events the way the hosted ``/stats/eth-profile`` router
does from persisted ``eth_profile_test`` rows.

This is the heaviest plugin stats tool: a per-day chronological walk over 15m +
1H history, with a TPO profile computed for every day. Paging is bounded and
``days`` is capped — as with every plugin stats tool, accuracy depends on how
much history is fetched, so cite the sample size.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from data import binance
from data import market
from engines import eth_profile_stats as engine

# 15m + 1H per-day walk. 90 days × 96 (15m) ≈ 8.6k candles + 90×24 (1H) ≈ 2.2k.
# Cap modestly — this tool computes a TPO profile per day.
_DEFAULT_DAYS = 90
_MAX_DAYS = 150
_MIN_DAYS = 5


def _adapt_candles(raw: list[dict]) -> list[dict]:
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
            "prev_poc_pct": round(sum(1 for r in rows if r["touched_prev_poc"]) / cnt * 100, 1),
            "prev_vah_pct": round(sum(1 for r in rows if r["touched_prev_vah"]) / cnt * 100, 1),
            "prev_val_pct": round(sum(1 for r in rows if r["touched_prev_val"]) / cnt * 100, 1),
        }
    return out


def register(mcp) -> None:
    @mcp.tool()
    async def compute_eth_profile_stats(symbol: str = "BTCUSDT", days: int = 90) -> dict:
        """Compute ETH Profile / previous-day VA-POC touch statistics.

        Fetches deep 15m + 1H candles (Binance for crypto — public, no API key;
        OANDA for forex/indices when ``RF_OANDA_TOKEN`` is set). For each RTH
        trading day it builds an **RTH-bounded TPO profile** (reusing the same
        Market Profile engine as ``get_market_profile``), captures that day's
        **POC / VAH / VAL**, then walks the NEXT day chronologically to detect
        whether price **touched the prior day's POC / VAH / VAL** and at what
        time. It aggregates the events exactly the way the hosted
        ``/stats/eth-profile`` dashboard does. Returns structured JSON for the
        model to interpret: how reliably yesterday's value-area levels get
        revisited the next day (a mean-reversion / magnet edge), when in the day
        the touch typically happens, and how wide the RTH range runs.

        IMPORTANT — synthetic open for crypto: the RTH window for 24/7 crypto is
        a *synthetic* convention pinned to the US equities open (13:30-20:00 UTC).
        It is most meaningful on forex/indices with a real cash session.

        IMPORTANT — sample window + cost: this is the heaviest stats tool (a TPO
        profile per day over a chronological walk). The hosted product aggregates
        over its FULL history; this tool only samples the last ``days`` it fetches
        live (default 90, hard cap 150). Accuracy depends on history depth — cite
        the sample size (``touch.n``) when interpreting.

        Args:
            symbol: Symbol — crypto with no separator (``BTCUSDT``, ``ETHUSDT``),
                or underscore-separated forex/index (``EUR_USD``, ``NAS100_USD``)
                when ``RF_OANDA_TOKEN`` is set.
            days: Lookback window in days, capped at 150. ~60+ gives a stable
                sample.

        Returns:
            A dict with ``symbol``; ``window`` (``candles_15m``, ``candles_1h``,
            ``from``, ``to`` ISO-UTC, ``days``, ``profile_days``,
            ``rth_window_utc``, ``rth_convention``); ``touch``
            (``prev_poc_pct`` / ``prev_vah_pct`` / ``prev_val_pct`` touch rates,
            ``avg_prev_*_touch_time`` HH:MM UTC, ``tpo_quality_normal_pct``,
            ``n``, ``confidence``); ``extension`` (RTH-range distribution); and
            ``day_of_week``. On failure, a dict with an ``error`` key.
        """
        days = max(1, min(int(days), _MAX_DAYS))
        total_15m = days * 96   # 96 fifteen-minute candles per day
        total_1h = days * 24
        m15_pages = max(2, min(30, (total_15m // 1000) + 2))
        h1_pages = max(2, (total_1h // 1000) + 2)

        try:
            raw_15m = await market.fetch_candles_paged(
                symbol, "15m", total=total_15m, max_pages=m15_pages
            )
            raw_1h = await market.fetch_candles_paged(
                symbol, "1h", total=total_1h, max_pages=h1_pages
            )
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not raw_15m or not raw_1h:
            return {
                "error": (
                    f"Insufficient candle data for {symbol} "
                    f"(15m={len(raw_15m)}, 1h={len(raw_1h)})."
                )
            }

        m15 = _adapt_candles(raw_15m)
        h1 = _adapt_candles(raw_1h)
        events = engine.build_events(
            symbol.upper(), _group_by_day(m15), _group_by_day(h1)
        )

        if len(events) < _MIN_DAYS:
            return {
                "error": (
                    f"Only {len(events)} profile days for {symbol.upper()} — need "
                    f"at least {_MIN_DAYS} to compute meaningful touch rates. Try a "
                    "longer window or a different symbol."
                )
            }

        ref = raw_15m
        from_iso = datetime.fromtimestamp(ref[0]["time"], tz=timezone.utc).isoformat()
        to_iso = datetime.fromtimestamp(ref[-1]["time"], tz=timezone.utc).isoformat()
        span_days = max(1, round((ref[-1]["time"] - ref[0]["time"]) / 86400))
        convention_name, windows = engine.convention_for(symbol)
        rth_window = f"{windows['rth'][0]}-{windows['rth'][1]}"

        return {
            "symbol": symbol.upper(),
            "window": {
                "candles_15m": len(raw_15m),
                "candles_1h": len(raw_1h),
                "from": from_iso,
                "to": to_iso,
                "days": span_days,
                "profile_days": len(events),
                "rth_window_utc": rth_window,
                "rth_convention": convention_name,
                "note": (
                    "Recent live sample only — the hosted product uses full "
                    "history, so these rates differ from the dashboard. For 24/7 "
                    "crypto the RTH window is synthetic (13:30-20:00 UTC)."
                ),
            },
            "touch": engine.agg_touch(events),
            "extension": engine.agg_extension(events),
            "day_of_week": _agg_day_of_week(events),
        }
