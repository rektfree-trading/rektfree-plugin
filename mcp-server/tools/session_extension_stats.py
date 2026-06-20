"""
``compute_session_extension_stats`` — on-the-fly session-extension statistics
(crypto, keyless).

Fetches deep 1H Binance history, buckets it into Asia/London/NY sessions per UTC
day, and answers: how often / how far does each session push BEYOND the prior
intraday session's range? Mirrors the hosted ``/stats/session-potential/*``
aggregators, but with NO database:

- **extensions** — per session (London vs Asia, NY vs London): how often it
  breaks the prior session's high only / low only / both / neither, the order
  (h_then_l / l_then_h) when both, and how far it overshoots (median/avg
  overshoot distance + multiple of the prior range).
- **session_range** — each session's own H−L distribution (median/avg/p25/p75)
  in quote units and %, so you can see typical vs outlier expansion.
- **daily_direction** — long-day vs short-day split (up_leg ≥ down_leg).
- **hod_lod** — per-session probability of printing the day's high / low.

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

_MAX_DAYS = 180
_MIN_DAYS = 5


def _adapt_candles(raw: list[dict]) -> list[dict]:
    """Reshape Binance candles: float unix ``time`` → tz-aware ``timestamp``."""
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


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _build_day_summaries(grouped: dict[str, dict[str, list[dict]]]) -> dict[str, dict]:
    """Per-day session-range dicts (for the extension engine) keyed by day."""
    out: dict[str, dict] = {}
    for day_key in sorted(grouped.keys()):
        sessions = grouped[day_key]
        day_rows: dict[str, dict] = {}
        for sess_name in ("asia", "london", "new_york"):
            ev = sess_engine._compute_session_range(sessions.get(sess_name, []), sess_name, day_key, "")
            if ev:
                day_rows[sess_name] = ev["data"]
        if day_rows:
            out[day_key] = day_rows
    return out


def _agg_session_ranges(day_summaries: dict[str, dict]) -> dict:
    """Per-session H−L distribution (raw + %) — ``extension_block`` per session."""
    raw_vals: dict[str, list[float]] = {s: [] for s in ext_engine.SESSIONS}
    pct_vals: dict[str, list[float]] = {s: [] for s in ext_engine.SESSIONS}
    for day_rows in day_summaries.values():
        for s in ext_engine.SESSIONS:
            r = day_rows.get(s)
            if r and r.get("range") is not None:
                raw_vals[s].append(float(r["range"]))
                pct_vals[s].append(float(r.get("range_pct") or 0))
    out: dict[str, dict] = {}
    for s in ext_engine.SESSIONS:
        if not raw_vals[s]:
            continue
        out[s] = {
            "n": len(raw_vals[s]),
            "range": ext_engine.extension_block(raw_vals[s]),
            "range_pct": ext_engine.extension_block(pct_vals[s], decimals=3),
        }
    return out


def _agg_extensions(
    grouped: dict[str, dict[str, list[dict]]],
    day_summaries: dict[str, dict],
) -> dict:
    """Per-session breakout-beyond-prior-session grid + overshoot distribution.

    For each (session, prior) pair in ``PREV_SESSION`` we walk the session's 1H
    candles to detect first H-break / first L-break vs the prior session's H/L
    (the extension), record the grid cell + ordering, and measure how far the
    session overshot the prior extreme (and as a multiple of the prior range).
    """
    out: dict[str, dict] = {}

    for sess, prev in ext_engine.PREV_SESSION.items():
        only_h = only_l = both = neither = 0
        h_then_l = l_then_h = 0
        sample = 0
        overshoot_dist: list[float] = []      # absolute overshoot beyond prior extreme
        overshoot_mult: list[float] = []      # overshoot / prior_range

        for day_key in sorted(grouped.keys()):
            day_rows = day_summaries.get(day_key, {})
            if prev not in day_rows or sess not in day_rows:
                continue
            prev_high = float(day_rows[prev].get("high") or 0)
            prev_low = float(day_rows[prev].get("low") or 0)
            if prev_high <= 0 or prev_low <= 0:
                continue
            prev_range = prev_high - prev_low

            sess_candles = grouped[day_key].get(sess, [])
            if not sess_candles:
                continue

            cell, seq = ext_engine._classify_breakout_with_sequencing(
                sess_candles, prev_high, prev_low
            )

            sample += 1
            if cell == "only_h":
                only_h += 1
            elif cell == "only_l":
                only_l += 1
            elif cell == "both":
                both += 1
                if seq == "h_then_l":
                    h_then_l += 1
                elif seq == "l_then_h":
                    l_then_h += 1
            else:
                neither += 1

            # Overshoot magnitude (only when an extension actually happened).
            sess_high = max(float(c["high"]) for c in sess_candles)
            sess_low = min(float(c["low"]) for c in sess_candles)
            over = 0.0
            if sess_high > prev_high:
                over = max(over, sess_high - prev_high)
            if sess_low < prev_low:
                over = max(over, prev_low - sess_low)
            if cell != "neither" and over > 0:
                overshoot_dist.append(over)
                if prev_range > 0:
                    overshoot_mult.append(over / prev_range)

        extended = only_h + only_l + both
        out[sess] = {
            "n": sample,
            "vs_prior_session": prev,
            "extension_rate": _rate(extended, sample),
            "only_h_pct": _rate(only_h, sample),
            "only_l_pct": _rate(only_l, sample),
            "both_pct": _rate(both, sample),
            "neither_pct": _rate(neither, sample),
            "h_then_l_pct": _rate(h_then_l, sample),
            "l_then_h_pct": _rate(l_then_h, sample),
            "avg_overshoot": round(_avg(overshoot_dist), 6),
            "avg_overshoot_multiple": round(_avg(overshoot_mult), 3),
            "overshoot_sample": len(overshoot_dist),
        }
    return out


def _agg_daily_direction(day_summaries: dict[str, dict]) -> dict:
    """Long-day vs short-day split (up_leg ≥ down_leg) + avg legs."""
    long_count = short_count = 0
    up_legs: list[float] = []
    down_legs: list[float] = []
    for day_rows in day_summaries.values():
        s = ext_engine._compute_day_summary(day_rows)
        if s is None:
            continue
        up_legs.append(s["up_leg"])
        down_legs.append(s["down_leg"])
        if s["direction"] == "long":
            long_count += 1
        else:
            short_count += 1
    n = long_count + short_count
    return {
        "n": n,
        "long_day_pct": _rate(long_count, n),
        "short_day_pct": _rate(short_count, n),
        "avg_up_leg": round(_avg(up_legs), 6),
        "avg_down_leg": round(_avg(down_legs), 6),
    }


def _agg_hod_lod(day_summaries: dict[str, dict]) -> dict:
    """Per-session P(prints day's high) / P(prints day's low)."""
    seen: dict[str, int] = {s: 0 for s in ext_engine.SESSIONS}
    hod: dict[str, int] = {s: 0 for s in ext_engine.SESSIONS}
    lod: dict[str, int] = {s: 0 for s in ext_engine.SESSIONS}
    qualifying = 0
    for day_rows in day_summaries.values():
        s = ext_engine._compute_day_summary(day_rows)
        if s is None:
            continue
        qualifying += 1
        for sess in ext_engine.SESSIONS:
            if sess in day_rows:
                seen[sess] += 1
        hod[s["hod_session"]] += 1
        lod[s["lod_session"]] += 1
    sessions_out: dict[str, dict] = {}
    for sess in ext_engine.SESSIONS:
        nn = seen[sess]
        sessions_out[sess] = {
            "n": nn,
            "hod_pct": _rate(hod[sess], nn),
            "lod_pct": _rate(lod[sess], nn),
        }
    return {"n": qualifying, "sessions": sessions_out}


def register(mcp) -> None:
    @mcp.tool()
    async def compute_session_extension_stats(symbol: str = "BTCUSDT", days: int = 90) -> dict:
        """Measure how often / how far each session extends beyond the prior one.

        Fetches deep 1H history from Binance (public, no API key), buckets it
        into Asia/London/New York sessions per UTC day, and answers the
        range-expansion questions the hosted ``/stats/session-potential``
        dashboard answers — for the model to interpret:

        - **extensions** — for London (vs Asia) and NY (vs London): the
          ``extension_rate`` (how often it breaks the prior session's range at
          all), the grid split (``only_h_pct`` / ``only_l_pct`` / ``both_pct`` /
          ``neither_pct``), the ordering when both break
          (``h_then_l_pct`` / ``l_then_h_pct``), and how far it overshoots
          (``avg_overshoot`` in quote units, ``avg_overshoot_multiple`` as a
          multiple of the prior session's range).
        - **session_range** — each session's own H−L distribution
          (median/mean/p25/p75) in quote units and %, to gauge typical vs
          outlier expansion.
        - **daily_direction** — long-day vs short-day split and average up/down
          legs.
        - **hod_lod** — per-session probability of printing the day's high/low.

        Every block carries a sample size ``n`` so the model can weight
        confidence — a rate from n=4 is noise, the same rate from n=120 is signal.

        IMPORTANT — sample window: the hosted product aggregates over its FULL
        candle history, but this tool only samples the last ``days`` days it
        fetches live (default ~90). Figures here are a recent snapshot and will
        differ from the dashboard's long-run numbers; cite the sample size when
        interpreting.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex/metals (e.g. ``EUR_USD``,
                ``XAU_USD``) ARE supported when ``RF_OANDA_TOKEN`` is set;
                crypto needs no key.
            days: Lookback window in days (1H candles), capped at 180. ~60+ days
                gives stable rates.

        Returns:
            A dict with ``symbol``; ``window`` (``candles``, ``from``, ``to``
            ISO-UTC, ``days``, ``note``); ``extensions`` (per-session breakout +
            overshoot block, each with ``n``); ``session_range`` (per-session H−L
            distribution); ``daily_direction``; and ``hod_lod``. On failure, a
            dict with an ``error`` key.
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
        day_summaries = _build_day_summaries(grouped)

        if len(day_summaries) < _MIN_DAYS:
            return {
                "error": (
                    f"Only {len(day_summaries)} usable days for {symbol.upper()} "
                    f"(got {len(raw)} 1H candles) — need at least {_MIN_DAYS} days "
                    "for meaningful session-extension stats. Try more days."
                )
            }

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
                "usable_days": len(day_summaries),
                "note": (
                    "Recent live sample only — the hosted product uses full "
                    "history, so these rates differ from the dashboard."
                ),
            },
            "extensions": _agg_extensions(grouped, day_summaries),
            "session_range": _agg_session_ranges(day_summaries),
            "daily_direction": _agg_daily_direction(day_summaries),
            "hod_lod": _agg_hod_lod(day_summaries),
        }
