"""
``get_session_card`` — on-the-fly "Session Potential" card for ONE session
(crypto, keyless).

Bundles the four hosted ``/stats/session-potential`` views for a single session
(asia / london / new_york) into one card, exactly the way the backend's
``per_session_card`` aggregator does — but with NO database. Fetches deep 1H
Binance history, buckets it into sessions per UTC day, builds per-day
``session_range`` summaries, and computes:

- **daily_direction** — long-day vs short-day split for days this session was
  present, plus a per-day-of-week breakdown.
- **hod_lod_potential** — how often this session prints the day's high / low /
  both / neither.
- **session_timing** — within the session, the wall-clock sub-window when its
  high vs low typically forms, bucketed by the day's overall direction.
- **session_breakouts** — tendency to break the PRIOR intraday session's
  high/low (the 6-cell grid: only_h / only_l / both / neither + h_then_l /
  l_then_h ordering). Asia has no intraday previous, so its breakouts block is
  null.
- **extension** — this session's own H-L range distribution + overshoot vs the
  prior session (reused from the session-extension engine).

The hosted product aggregates over its FULL history; this tool samples only the
last ~N days fetched live, so figures are a recent snapshot.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from data import binance
from data import market
from engines import session_extension_stats as ext_engine
from engines import session_stats as sess_engine
from tools import session_extension_stats as ext_tool

_MAX_DAYS = 365
_MIN_DAYS = 5
_VALID_SESSIONS = ("asia", "london", "new_york")


def _confidence(n: int) -> str:
    """n → HIGH / MEDIUM / LOW / INSUFFICIENT (``>=50 / >=20 / >=5 / else``)."""
    if n >= 50:
        return "HIGH"
    if n >= 20:
        return "MEDIUM"
    if n >= 5:
        return "LOW"
    return "INSUFFICIENT"


def _rate(num: int, den: int) -> float:
    return round(num / den * 100, 1) if den else 0.0


def _direction_for_session(day_summaries: dict[str, dict], session: str) -> dict:
    """Long/short split + per-DOW breakdown over days this session was present.

    Mirrors the backend's ``daily_direction`` aggregator, scoped to days that
    contain ``session`` (the per-session card scopes direction to those days).
    """
    long_count = short_count = 0
    dow_buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"long": 0, "short": 0})
    for day_rows in day_summaries.values():
        if session not in day_rows:
            continue
        s = ext_engine._compute_day_summary(day_rows)
        if s is None:
            continue
        if s["direction"] == "long":
            long_count += 1
        else:
            short_count += 1
        dow = s.get("day_of_week")
        if dow:
            dow_buckets[dow][s["direction"]] += 1

    n = long_count + short_count
    by_dow: dict[str, dict] = {}
    for dow in ext_engine.DOW_ORDER:
        if dow in dow_buckets:
            b = dow_buckets[dow]
            tot = b["long"] + b["short"]
            by_dow[dow] = {
                "long_pct": _rate(b["long"], tot),
                "short_pct": _rate(b["short"], tot),
                "count": tot,
            }
    return {
        "n": n,
        "long_pct": _rate(long_count, n),
        "short_pct": _rate(short_count, n),
        "by_day_of_week": by_dow,
    }


def _hod_lod_for_session(day_summaries: dict[str, dict], session: str) -> dict:
    """How often *session* prints the day's high / low / both / neither.

    Denominator = days this session was observed (matches the backend's
    ``hod_lod_potential`` per-session denominator).
    """
    seen = hod = lod = both = neither = 0
    for day_rows in day_summaries.values():
        if session not in day_rows:
            continue
        s = ext_engine._compute_day_summary(day_rows)
        if s is None:
            continue
        seen += 1
        is_hod = s["hod_session"] == session
        is_lod = s["lod_session"] == session
        if is_hod:
            hod += 1
        if is_lod:
            lod += 1
        if is_hod and is_lod:
            both += 1
        elif not is_hod and not is_lod:
            neither += 1
    return {
        "n": seen,
        "hod_pct": _rate(hod, seen),
        "lod_pct": _rate(lod, seen),
        "both_pct": _rate(both, seen),
        "neither_pct": _rate(neither, seen),
    }


def register(mcp) -> None:
    @mcp.tool()
    async def get_session_card(
        symbol: str = "BTCUSDT", session: str = "london", days: int = 120
    ) -> dict:
        """Get the "Session Potential" card for ONE session of a crypto symbol.

        Fetches deep 1H candles from Binance (public, no API key), buckets them
        into Asia/London/New York sessions per UTC day (Asia 00:00-08:00, London
        08:00-13:00, NY 13:00-21:00), and bundles the four hosted
        ``/stats/session-potential`` views for the requested ``session`` into one
        card — exactly the way the dashboard's per-session card does. Returns
        structured JSON for the model to interpret:

        - **direction** — long-day vs short-day split (up_leg >= down_leg) over
          days this session was present, plus a per-day-of-week breakdown
          (``by_day_of_week``).
        - **hod_lod** — how often this session prints the day's high (``hod_pct``),
          low (``lod_pct``), both (``both_pct``), or neither (``neither_pct``).
        - **timing** — within the session, the wall-clock sub-window when its high
          vs low typically forms, split by the day's overall direction
          (``long_expected`` / ``short_expected``, each with ``high_window`` /
          ``low_window`` / peak hours).
        - **breakouts** — tendency to break the PRIOR intraday session's high/low:
          a 6-cell grid (``only_h_pct`` / ``only_l_pct`` / ``both_pct`` /
          ``neither_pct``) plus the ordering when both break
          (``h_then_l_pct`` / ``l_then_h_pct``) and an ``extension_rate``. Asia has
          no intraday previous session, so its breakouts block is ``null``.
        - **extension** — this session's own H-L range distribution
          (median/mean/p25/p75 in quote units and %), plus the overshoot stats
          vs the prior session when applicable.

        Each block carries a sample size (``n``) and the card carries a
        ``confidence`` label (HIGH >=50 / MEDIUM >=20 / LOW >=5 / INSUFFICIENT)
        so the model can weight it.

        IMPORTANT — sample window: the hosted product aggregates over its FULL
        candle history, but this tool only samples the last ``days`` days it
        fetches live (default ~120). Figures here are a recent snapshot and will
        differ from the dashboard's long-run numbers; cite the sample size when
        interpreting.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex/metals (e.g. ``EUR_USD``,
                ``XAU_USD``) ARE supported when ``RF_OANDA_TOKEN`` is set; crypto
                needs no key.
            session: One of ``asia``, ``london``, ``new_york``. Defaults to
                ``london``.
            days: Lookback window in days (1H candles), capped at 365. ~60+ days
                gives stable rates.

        Returns:
            A dict with ``symbol``; ``session``; ``window`` (``candles``,
            ``from``, ``to`` ISO-UTC, ``days``, ``usable_days``, ``note``);
            ``sample_size`` / ``confidence``; ``direction``; ``hod_lod``;
            ``timing``; ``breakouts`` (or ``null`` for asia); and ``extension``.
            On failure, a dict with an ``error`` key.
        """
        sess = (session or "").strip().lower()
        if sess not in _VALID_SESSIONS:
            return {
                "error": (
                    f"Unknown session '{session}'. Expected one of "
                    f"{list(_VALID_SESSIONS)}."
                )
            }

        days = max(1, min(int(days), _MAX_DAYS))
        total = days * 24
        max_pages = max(2, (total // 1000) + 2)

        try:
            raw = await market.fetch_candles_paged(symbol, "1h", total=total, max_pages=max_pages)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not raw:
            return {"error": f"No candle data returned for {symbol}."}

        candles = ext_tool._adapt_candles(raw)
        grouped = sess_engine._group_by_day_and_session(candles)
        day_summaries = ext_tool._build_day_summaries(grouped)

        if len(day_summaries) < _MIN_DAYS:
            return {
                "error": (
                    f"Only {len(day_summaries)} usable days for {symbol.upper()} "
                    f"(got {len(raw)} 1H candles) — need at least {_MIN_DAYS} days "
                    "for a meaningful session card. Try more days."
                )
            }

        # Reuse the session-extension aggregators for extension + breakouts.
        extensions = ext_tool._agg_extensions(grouped, day_summaries)
        session_ranges = ext_tool._agg_session_ranges(day_summaries)

        direction_block = _direction_for_session(day_summaries, sess)
        hodlod_block = _hod_lod_for_session(day_summaries, sess)
        timing_block = ext_engine.session_timing_for(day_summaries, sess)

        # breakouts: asia has no intraday previous → null. Otherwise reuse the
        # session-extension grid (which is exactly the backend's breakout grid).
        if sess == "asia":
            breakouts_block = None
        else:
            breakouts_block = extensions.get(sess)

        # extension: this session's own range distribution.
        extension_block = session_ranges.get(sess)

        sample_size = hodlod_block["n"]

        from_iso = datetime.fromtimestamp(raw[0]["time"], tz=timezone.utc).isoformat()
        to_iso = datetime.fromtimestamp(raw[-1]["time"], tz=timezone.utc).isoformat()
        span_days = max(1, round((raw[-1]["time"] - raw[0]["time"]) / 86400))

        return {
            "symbol": symbol.upper(),
            "session": sess,
            "window": {
                "candles": len(raw),
                "from": from_iso,
                "to": to_iso,
                "days": span_days,
                "usable_days": len(day_summaries),
                "sessions_utc": "asia 00:00-08:00, london 08:00-13:00, new_york 13:00-21:00",
                "note": (
                    "Recent live sample only — the hosted product uses full "
                    "history, so these rates differ from the dashboard."
                ),
            },
            "sample_size": sample_size,
            "confidence": _confidence(sample_size),
            "direction": direction_block,
            "hod_lod": hodlod_block,
            "timing": timing_block,
            "breakouts": breakouts_block,
            "extension": extension_block,
        }
