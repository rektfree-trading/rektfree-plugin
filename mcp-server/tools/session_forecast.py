"""
``get_session_forecast`` — probabilistic projection for the upcoming session
(crypto, keyless, computed in memory).

A *statistical* forecast, not an AI prediction: it fetches deep 1H Binance
history, buckets it into Asia/London/New York sessions with the vendored
``engines.session_stats`` detectors, then — for the session the UTC clock says
is **next** — computes the empirical frequency distributions over that session's
recent history:

  - expected range   (median + 25/75 percentile band, ``range_pct``)
  - sweep probability of the prior session's high/low (+ side skew + reversal
    rate after the sweep)
  - continuation-vs-reversal odds (New York only)
  - concrete projected levels off the live price + the prior session's actual
    high/low

This replicates the **pure** core of the backend's ``session_forecast.py`` (its
range/sweep/continuation frequency math) while replacing the DB-coupled
similar-session condition-matching with straight aggregation over the recent
live sample. There is **no macro/news input** here, so any forecast can be
overridden by an event; every probability is reported with its sample size
``n``. Reuses the vendored detectors (``engines.session_stats``) and the offline
clock (``tools.session_clock``) — nothing in this module imports ``app.*``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from data import binance
from data import market
from engines import session_stats as ss
from engines import session_forecast as fc
from tools import session_clock

# Same fetch envelope as tools/session_stats.py — polite to Binance rate limits.
_MAX_DAYS = 180
_MIN_CANDLES = 48  # backend's floor; below this aggregation is meaningless

# Forecast session -> (prior session key, sweep event_type the detector emits).
# The sweep detector names events "<prior>_sweep" and the *current* session is
# the sweeper. Asia has no upstream sweep (no NY->Asia detector in the backend).
_PRIOR = {
    "london": ("asia", "asia_sweep"),
    "new_york": ("london", "london_sweep"),
    "asia": (None, None),
}

# The clock can report "post_ny" (21:00-24:00) as the live session; the next
# tradeable session to forecast is Asia. Map the clock's next-session key onto
# the three stats sessions.
_NEXT_TRADEABLE = {
    "asia": "asia",
    "london": "london",
    "new_york": "new_york",
    "post_ny": "asia",
}


def _adapt_candles(raw: list[dict]) -> list[dict]:
    """Reshape Binance candles for the detectors (unix float -> UTC datetime).

    Identical adaptation to tools/session_stats.py — the detectors read
    ``c["timestamp"]`` as a tz-aware datetime.
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


def _build_history(grouped: dict) -> dict:
    """Run the detectors over every day/session, collecting events in memory.

    Mirrors the backend orchestrator's per-day loop (minus DB writes), keeping
    the raw candle lists per day so we can recover the most-recent *prior*
    session's actual high/low for level projection.
    """
    ranges: dict[str, list[dict]] = {"asia": [], "london": [], "new_york": []}
    asia_sweeps: list[dict] = []
    london_sweeps: list[dict] = []
    ny_conts: list[dict] = []

    for day_key in sorted(grouped.keys()):
        sessions = grouped[day_key]
        asia_c = sessions.get("asia", [])
        london_c = sessions.get("london", [])
        ny_c = sessions.get("new_york", [])

        for sess_name in ("asia", "london", "new_york"):
            ev = ss._compute_session_range(sessions.get(sess_name, []), sess_name, day_key, "")
            if ev:
                ranges[sess_name].append(ev["data"])

        sweep = ss._detect_sweep(asia_c, london_c, "asia", "london", day_key)
        if sweep:
            asia_sweeps.append(sweep["data"])

        sweep = ss._detect_sweep(london_c, ny_c, "london", "new_york", day_key)
        if sweep:
            london_sweeps.append(sweep["data"])

        cont = ss._detect_ny_continuation(london_c, ny_c, day_key)
        if cont:
            ny_conts.append(cont["data"])

    return {
        "ranges": ranges,
        "asia_sweep": asia_sweeps,
        "london_sweep": london_sweeps,
        "ny_conts": ny_conts,
    }


def _latest_prior_extremes(ranges: dict, prior_session: str | None) -> tuple[float | None, float | None]:
    """Most recent completed ``prior_session`` high/low (the liquidity to sweep).

    Range rows are appended in chronological day order, so the last one is the
    freshest. Returns (None, None) when there's no prior session (Asia forecast)
    or no history yet.
    """
    if not prior_session:
        return None, None
    rows = ranges.get(prior_session, [])
    if not rows:
        return None, None
    last = rows[-1]
    return last.get("high"), last.get("low")


def register(mcp) -> None:
    @mcp.tool()
    async def get_session_forecast(symbol: str = "BTCUSDT", days: int = 90) -> dict:
        """Probabilistic projection for the upcoming/current trading session.

        A **frequency-based statistical forecast**, NOT an AI prediction and NOT
        a guarantee. Fetches deep 1H Binance candles (public, no API key),
        buckets them into Asia/London/New York sessions per UTC day with the same
        detectors the hosted product uses, then — for the session the UTC clock
        says is **next** — computes empirical distributions over that session's
        recent history and projects them onto the live price.

        It tells you: the expected range (median + a 25th/75th percentile band),
        how often this session sweeps the *prior* session's high/low (and which
        side, and how often that sweep reverses), whether New York tends to
        continue or reverse London, the session's bullish/bearish close skew, and
        concrete projected high/low levels off the current price plus the prior
        session's actual extremes (the liquidity a sweep would target).

        IMPORTANT — read these caveats every time:
          * These are **frequencies over a recent live sample** (default ~90
            days), not certainties and not the hosted dashboard's full-history
            figures. Always interpret each probability WITH its ``n``.
          * There is **no macro/news input** in this slice — a scheduled event
            (CPI, FOMC, etc.) can override any of these odds. Treat the forecast
            as a base rate, not a plan.
          * Asia has no upstream sweep (no prior intraday session to sweep) so
            ``sweep_prob`` is empty for an Asia forecast; ``continuation_prob``
            is only populated for a New York forecast.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex/metals (e.g. ``EUR_USD``,
                ``XAU_USD``) ARE supported when ``RF_OANDA_TOKEN`` is set;
                crypto needs no key.
            days: Lookback window in days (1H candles), capped at 180. ~60+ days
                gives stable rates; thin windows make the ``n`` small.

        Returns:
            A dict with ``symbol``; ``as_of`` (ISO-UTC now); ``forecast_session``
            (the session being forecast) and the live ``current_session``;
            ``window`` (candle/coverage metadata); ``expected_range``
            (``median``/``low``/``high`` in range%, with ``n``); ``direction``
            (bullish/bearish close skew); ``sweep_prob`` (prior-session sweep
            ``prob``, side skew, ``reversal_rate``, with ``n``);
            ``continuation_prob`` (NY continue vs reverse, with ``n``);
            ``projected_levels`` (anchor price, projected high/low, prior-session
            high/low); and a ``disclaimer``. On failure, a dict with ``error``.
        """
        days = max(1, min(int(days), _MAX_DAYS))
        total = days * 24
        max_pages = max(2, (total // 1000) + 2)

        try:
            raw = await market.fetch_candles_paged(symbol, "1h", total=total, max_pages=max_pages)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if len(raw) < _MIN_CANDLES:
            return {
                "error": (
                    f"Not enough candle data for {symbol}: got {len(raw)} 1H candles, "
                    f"need at least {_MIN_CANDLES}. Try a different symbol or fewer days."
                )
            }

        now = datetime.now(timezone.utc)
        clock = session_clock._build_clock(now)
        # Forecast the session the clock says is NEXT, mapped onto a tradeable
        # stats session (post_ny -> asia).
        forecast_session = _NEXT_TRADEABLE[clock["next_session"]]
        prior_session, _sweep_type = _PRIOR[forecast_session]

        candles = _adapt_candles(raw)
        grouped = ss._group_by_day_and_session(candles)
        hist = _build_history(grouped)

        ranges = hist["ranges"]
        fsession_rows = ranges.get(forecast_session, [])

        exp_range = fc.expected_range(fsession_rows)
        direction = fc.direction_skew(fsession_rows)

        # Sweep prob: forecast session sweeping the prior session. Denominator =
        # days the prior session existed (mirrors backend _agg_sweeps).
        if prior_session and forecast_session in ("london", "new_york"):
            sweep_rows = hist["asia_sweep"] if forecast_session == "london" else hist["london_sweep"]
            prior_days = len(ranges.get(prior_session, []))
            sweep_prob = fc.sweep_probability(sweep_rows, prior_days)
        else:
            sweep_prob = {"prob": 0.0, "n": 0, "note": "No upstream intraday session to sweep for Asia."}

        # Continuation only meaningful for New York vs London.
        if forecast_session == "new_york":
            continuation_prob = fc.continuation_probability(hist["ny_conts"])
        else:
            continuation_prob = {
                "continuation": 0.0,
                "reversal": 0.0,
                "n": 0,
                "note": "Continuation is a New-York-vs-London metric only.",
            }

        last_price = raw[-1]["close"]
        prior_high, prior_low = _latest_prior_extremes(ranges, prior_session)
        projected = fc.project_levels(last_price, exp_range["median"], prior_high, prior_low)

        from_iso = datetime.fromtimestamp(raw[0]["time"], tz=timezone.utc).isoformat()
        to_iso = datetime.fromtimestamp(raw[-1]["time"], tz=timezone.utc).isoformat()
        span_days = max(1, round((raw[-1]["time"] - raw[0]["time"]) / 86400))

        return {
            "symbol": symbol.upper(),
            "as_of": now.isoformat(),
            "current_session": clock["session"],
            "forecast_session": forecast_session,
            "prior_session": prior_session,
            "window": {
                "candles": len(raw),
                "from": from_iso,
                "to": to_iso,
                "days": span_days,
                "note": (
                    "Recent live sample only — frequencies, not the dashboard's "
                    "full-history figures."
                ),
            },
            "expected_range": exp_range,
            "direction": direction,
            "sweep_prob": sweep_prob,
            "continuation_prob": continuation_prob,
            "projected_levels": projected,
            "disclaimer": (
                "Statistical forecast: empirical frequencies over a recent sample, "
                "NOT an AI prediction or a guarantee. No macro/news input — a "
                "scheduled event can override these odds. Always read each "
                "probability with its sample size n."
            ),
        }
