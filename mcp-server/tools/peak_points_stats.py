"""
``compute_peak_points_stats`` — on-the-fly Peak Points statistics (crypto, keyless).

Fetches deep 1H history, buckets it into Asia/London/NY sessions per UTC day,
then for each completed day determines which SESSION printed the day's HIGH
(HOD) and which printed the day's LOW (LOD) — exactly the way the hosted
``/stats/peak-points`` product does. Returns:

- **hod_marginals** — P(HOD in Asia / London / NY): which session usually makes
  the day's high.
- **lod_marginals** — P(LOD in Asia / London / NY): which session usually makes
  the day's low.
- **matrix** — the joint distribution P(HOD session × LOD session): e.g. "if Asia
  made the LOW, which session usually makes the HIGH?" Read ``matrix[HOD][LOD]``.
- **by_direction** — the same joint matrix split into bullish vs bearish days.

The hosted product aggregates over its FULL candle history; this tool samples
only the last ~N days fetched live, so figures are a recent snapshot.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from data import binance
from data import market
from engines import peak_points_stats as engine
from engines import session_stats as sess_engine

# 1H is light; cap at a year like the other session stats tools.
_MAX_DAYS = 365
_MIN_DAYS = 5  # below this the matrix is meaningless


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


def _classify_days(grouped: dict[str, dict[str, list[dict]]]) -> list[dict]:
    """Build one ``peak_points`` row per day from grouped session candles.

    For each day, compute each session's range (via the session_stats engine),
    assemble the session-range list, then classify HOD/LOD via the peak-points
    engine. Days with no resolvable extreme are skipped.
    """
    rows: list[dict] = []
    for day_key in sorted(grouped.keys()):
        sessions_candles = grouped[day_key]
        sessions: list[dict] = []
        for sess_name in engine.SESSION_ORDER:
            ev = sess_engine._compute_session_range(
                sessions_candles.get(sess_name, []), sess_name, day_key, ""
            )
            if ev:
                row = dict(ev["data"])
                row["session"] = sess_name
                sessions.append(row)
        if not sessions:
            continue
        weekday_index = datetime.strptime(day_key, "%Y-%m-%d").weekday()
        data = engine.classify_day(sessions, weekday_index)
        if data:
            rows.append(data)
    return rows


def _matrix_block(rows: list[dict]) -> dict:
    """Wrap ``engine.build_matrix`` with a confidence label."""
    block = engine.build_matrix(rows)
    block["confidence"] = engine.confidence(block["sample_size"])
    return block


def register(mcp) -> None:
    @mcp.tool()
    async def compute_peak_points_stats(symbol: str = "BTCUSDT", days: int = 120) -> dict:
        """Compute Peak Points (HOD-session × LOD-session) statistics from live history.

        Fetches deep 1H candles from Binance (public, no API key), buckets them
        into Asia/London/New York sessions per UTC day (Asia 00:00-08:00, London
        08:00-13:00, NY 13:00-21:00), and for each completed day determines which
        SESSION printed the day's HIGH (HOD) and which printed the day's LOW
        (LOD) — exactly the way the hosted ``/stats/peak-points`` dashboard does.
        Returns structured JSON for the model to interpret:

        - **hod_marginals / hod_marginals_pct** — which session usually makes the
          day's high (P(HOD in Asia / London / NY)).
        - **lod_marginals / lod_marginals_pct** — which session usually makes the
          day's low.
        - **matrix / matrix_pct** — the JOINT distribution P(HOD session × LOD
          session). Read ``matrix_pct[HOD][LOD]``: the outer key is the session
          that printed the HIGH, the inner key the session that printed the LOW.
          This answers conditional questions — e.g. "if Asia made the LOW, which
          session usually makes the HIGH?" — by reading down the LOD column. The
          diagonal (same session made both extremes) is usually small; on rare
          flat/inside days it can be non-zero and is recorded honestly.
        - **by_direction** — the same joint matrix split into bullish-day vs
          bearish-day subsets (net_direction = the day's largest session up-leg
          vs down-leg).

        Every block carries a ``sample_size`` and a ``confidence`` label
        (HIGH >=50 / MEDIUM >=20 / LOW >=5 / INSUFFICIENT) so the model can weight
        it — a clean matrix off 6 days is noise, the same matrix off 200 is signal.

        IMPORTANT — sample window: the hosted product aggregates over its FULL
        candle history, but this tool only samples the last ``days`` days it
        fetches live (default ~120). Figures here are a recent snapshot and will
        differ from the dashboard's long-run numbers; cite the sample size when
        interpreting.

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex/metals (e.g. ``EUR_USD``,
                ``XAU_USD``) ARE supported when ``RF_OANDA_TOKEN`` is set (the
                hosted router covers forex + indices too); crypto needs no key.
            days: Lookback window in days (1H candles), capped at 365. Each day
                yields one HOD/LOD classification; ~60+ days gives stable rates.

        Returns:
            A dict with ``symbol``; ``window`` (``candles``, ``from``, ``to``
            ISO-UTC, ``days``, ``usable_days``, ``note``); ``sample_size`` /
            ``confidence``; ``hod_marginals`` + ``hod_marginals_pct``;
            ``lod_marginals`` + ``lod_marginals_pct``; ``matrix`` +
            ``matrix_pct`` (joint HOD×LOD); and ``by_direction`` (``bullish_day``
            / ``bearish_day``, each a matrix block with its own sample size +
            confidence). On failure, a dict with an ``error`` key.
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
        rows = _classify_days(grouped)

        if len(rows) < _MIN_DAYS:
            return {
                "error": (
                    f"Only {len(rows)} usable days for {symbol.upper()} "
                    f"(got {len(raw)} 1H candles) — need at least {_MIN_DAYS} days "
                    "for meaningful Peak Points stats. Try more days."
                )
            }

        overall = _matrix_block(rows)
        bull_rows = [r for r in rows if r.get("net_direction") == "bullish"]
        bear_rows = [r for r in rows if r.get("net_direction") == "bearish"]

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
                "usable_days": len(rows),
                "sessions_utc": "asia 00:00-08:00, london 08:00-13:00, new_york 13:00-21:00",
                "note": (
                    "Recent live sample only — the hosted product uses full "
                    "history, so these rates differ from the dashboard."
                ),
            },
            "sample_size": overall["sample_size"],
            "confidence": overall["confidence"],
            "hod_marginals": overall["hod_marginals"],
            "hod_marginals_pct": overall["hod_marginals_pct"],
            "lod_marginals": overall["lod_marginals"],
            "lod_marginals_pct": overall["lod_marginals_pct"],
            "matrix": overall["matrix"],
            "matrix_pct": overall["matrix_pct"],
            "by_direction": {
                "bullish_day": _matrix_block(bull_rows),
                "bearish_day": _matrix_block(bear_rows),
            },
        }
