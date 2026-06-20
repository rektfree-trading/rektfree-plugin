"""
``run_backtest`` — historical pattern frequency study (crypto, keyless).

Answers "how often does X lead to Y?" the way the hosted backtester
(``app/services/backtester.py``) does — but with NO database and NO AI key. The
hosted product queries a persisted ``session_events`` table, filters rows by
structured conditions, then aggregates the relevant outcome rate. This tool
computes those exact events IN MEMORY from a deep 1H Binance history (the
vendored session/SMC engines), filters by the SAME structured conditions, and
aggregates the SAME outcome — returning a compact frequency report the model
interprets.

Division of labour (important): the natural-language question
("how often does NY continue London on Mondays for ETH?") is parsed into
STRUCTURED conditions by Claude (the ``/backtest`` command / ``backtest`` skill),
NOT by this tool. This tool takes the structured params and does the data work.

Mirrors the backend's ``find_matching_events`` (the filter) and
``compute_outcomes`` (the per-event-type outcome + day-of-week breakdown +
confidence). It does NOT support ``macro_present`` (no macro/news data in this
slice) — the key is accepted and ignored with a note.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from data import binance
from data import market
from engines import event_query

# Lookback caps — match the session-stats tool so windows stay polite to Binance.
_MAX_DAYS = 365
_MIN_CANDLES = 48

# event_type → the OUTCOME this event answers ("X then Y?"), used for both the
# tool docstring and the confidence note label.
_OUTCOME_LABEL = {
    "session_range": "bullish direction",
    "asia_sweep": "reversal after the sweep",
    "london_sweep": "reversal after the sweep",
    "ny_continuation": "NY continuation of London",
    "power_of_3": "successful distribution",
    "smc_ob_test": "retest & hold of the order block",
    "smc_fvg_test": "fill of the fair-value gap",
    "smc_bos_test": "continuation after the break",
    "smc_choch_test": "reversal after the change of character",
    "smc_eq_test": "sweep & reversal of the equal level",
    "smc_sweep_test": "successful liquidity sweep",
}


def _rate(num: int, den: int) -> float:
    return round(num / den * 100, 1) if den else 0.0


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _confidence(n: int) -> str:
    """Same buckets as the backend's ``compute_outcomes``."""
    if n >= 50:
        return "HIGH"
    if n >= 20:
        return "MEDIUM"
    if n >= 5:
        return "LOW"
    return "INSUFFICIENT"


def _filter_events(events: list[dict], cond: dict) -> tuple[list[dict], list[str]]:
    """Filter the unified event set by structured conditions.

    Mirrors the backend's ``find_matching_events``: each present condition key
    narrows the set by exact match on the same field. Returns the matched events
    plus any notes (e.g. a DOW filter applied to an event family that carries no
    day-of-week, which the backend's persisted rows would have but the vendored
    SMC evaluator does not).
    """
    notes: list[str] = []
    out = list(events)

    # event_type is the primary discriminator (always set by the caller here).
    et = cond.get("event_type")
    if et:
        out = [e for e in out if e["event_type"] == et]

    if cond.get("session"):
        out = [e for e in out if e.get("session") == cond["session"]]

    if cond.get("day_of_week"):
        # SMC events carry no formation date → no day_of_week to match on.
        if et in event_query.SMC_EVENT_TYPES:
            notes.append(
                f"day_of_week='{cond['day_of_week']}' ignored: {et} events carry "
                "no formation date in the keyless engine (no DB), so they cannot "
                "be filtered by weekday."
            )
        else:
            out = [e for e in out if e.get("day_of_week") == cond["day_of_week"]]

    if cond.get("direction"):
        out = [e for e in out if e.get("direction") == cond["direction"]]

    if cond.get("sweep_side"):
        out = [e for e in out if e.get("sweep_side") == cond["sweep_side"]]

    if cond.get("htf_bias"):
        # htf_bias only exists on SMC events (mapped from the structure bias).
        out = [e for e in out if e.get("htf_bias") == cond["htf_bias"]]

    if cond.get("range_state"):
        # range_state (tight/wide) is not stamped on the vendored events.
        notes.append(
            f"range_state='{cond['range_state']}' ignored: the keyless engine "
            "does not tag events with a tight/wide range state."
        )

    if cond.get("macro_present") not in (None, ""):
        notes.append(
            "macro_present ignored: no macro/news data is available in this "
            "keyless slice."
        )

    return out, notes


def _aggregate(events: list[dict], event_type: str) -> dict:
    """Aggregate the OUTCOME for the matched events by event type.

    Mirrors the per-``event_type`` branches of the backend's
    ``compute_outcomes`` — the same success metric and rate definitions, each
    reported alongside its sample size ``n``.
    """
    n = len(events)
    out: dict = {"n": n}
    if n == 0:
        return out

    data = [e["_data"] for e in events]

    if event_type in ("asia_sweep", "london_sweep"):
        out["swept_high"] = sum(1 for d in data if d.get("swept_side") == "high")
        out["swept_low"] = sum(1 for d in data if d.get("swept_side") == "low")
        out["swept_both"] = sum(1 for d in data if d.get("swept_side") == "both")
        rev = sum(1 for d in data if d.get("reversal"))
        out["reversal_count"] = rev
        out["reversal_rate"] = _rate(rev, n)

    elif event_type == "ny_continuation":
        cont = sum(1 for d in data if d.get("continuation"))
        out["continuation_rate"] = _rate(cont, n)
        out["reversal_rate"] = _rate(n - cont, n)

    elif event_type == "session_range":
        bull = sum(1 for d in data if d.get("direction") == "bullish")
        out["bullish_rate"] = _rate(bull, n)
        out["bearish_rate"] = _rate(n - bull, n)
        out["avg_range_pct"] = round(_avg([d["range_pct"] for d in data if d.get("range_pct") is not None]), 3)

    elif event_type == "power_of_3":
        success = sum(1 for d in data if d.get("distribution_success"))
        out["success_rate"] = _rate(success, n)
        out["swept_high"] = sum(1 for d in data if d.get("manipulation_side") == "high")
        out["swept_low"] = sum(1 for d in data if d.get("manipulation_side") == "low")

    elif event_type == "smc_ob_test":
        retested = sum(1 for d in data if d.get("retested"))
        held = sum(1 for d in data if d.get("held"))
        out["retest_rate"] = _rate(retested, n)
        out["hold_rate_when_retested"] = _rate(held, retested)
        out["hold_rate_overall"] = _rate(held, n)

    elif event_type == "smc_fvg_test":
        filled = sum(1 for d in data if d.get("filled"))
        out["fill_rate"] = _rate(filled, n)
        out["avg_fill_pct"] = round(_avg([d["filled_pct"] for d in data if d.get("filled_pct") is not None]), 1)

    elif event_type == "smc_bos_test":
        cont = sum(1 for d in data if d.get("continuation"))
        out["continuation_rate"] = _rate(cont, n)
        out["avg_max_move_pct"] = round(_avg([d["max_move_pct"] for d in data if d.get("max_move_pct") is not None]), 4)

    elif event_type == "smc_choch_test":
        rev = sum(1 for d in data if d.get("reversed"))
        out["reversal_rate"] = _rate(rev, n)
        out["avg_max_move_pct"] = round(_avg([d["max_move_pct"] for d in data if d.get("max_move_pct") is not None]), 4)

    elif event_type == "smc_eq_test":
        swept = sum(1 for d in data if d.get("swept"))
        rev = sum(1 for d in data if d.get("reversed"))
        out["sweep_rate"] = _rate(swept, n)
        out["reversal_rate"] = _rate(rev, n)
        out["reversal_rate_when_swept"] = _rate(rev, swept)

    elif event_type == "smc_sweep_test":
        success = sum(1 for d in data if d.get("success"))
        out["success_rate"] = _rate(success, n)
        out["avg_max_move_pct"] = round(_avg([d["max_move_pct"] for d in data if d.get("max_move_pct") is not None]), 4)

    out["confidence"] = _confidence(n)
    return out


def _is_success(event_type: str, d: dict) -> bool:
    """Per-event-type success metric for the day-of-week breakdown.

    Same definitions as the backend's ``compute_outcomes._is_success``.
    """
    if event_type == "session_range":
        return d.get("direction") == "bullish"
    if event_type in ("asia_sweep", "london_sweep"):
        return bool(d.get("reversal"))
    if event_type == "ny_continuation":
        return bool(d.get("continuation"))
    if event_type == "power_of_3":
        return bool(d.get("distribution_success"))
    return d.get("direction") == "bullish"


def _day_of_week(events: list[dict], event_type: str) -> dict:
    """Per-weekday count + success rate (session-family events only).

    Mirrors the backend's ``by_day_of_week`` block. SMC events have no weekday,
    so this returns ``{}`` for them.
    """
    if event_type in event_query.SMC_EVENT_TYPES:
        return {}
    label = {
        "session_range": "bullish",
        "asia_sweep": "reversal",
        "london_sweep": "reversal",
        "ny_continuation": "continuation",
        "power_of_3": "success",
    }.get(event_type, "bullish")

    buckets: dict[str, dict] = {}
    for e in events:
        dow = e.get("day_of_week", "Unknown")
        b = buckets.setdefault(dow, {"total": 0, "success": 0})
        b["total"] += 1
        if _is_success(event_type, e["_data"]):
            b["success"] += 1

    return {
        dow: {
            "count": b["total"],
            f"{label}_pct": _rate(b["success"], b["total"]),
        }
        for dow, b in buckets.items()
    }


def register(mcp) -> None:
    @mcp.tool()
    async def run_backtest(
        symbol: str = "BTCUSDT",
        event_type: str = "",
        session: str = "",
        day_of_week: str = "",
        direction: str = "",
        sweep_side: str = "",
        htf_bias: str = "",
        range_state: str = "",
        days: int = 180,
    ) -> dict:
        """Backtest a historical pattern: "how often does X lead to Y?" (crypto).

        Computes — IN MEMORY, no database, no AI key — the same statistical
        outcome study the hosted backtester runs. It fetches deep 1H Binance
        history (public, no key), runs the vendored session + SMC engines to
        rebuild every detected event with its outcome, filters that set by the
        structured conditions you pass, and aggregates the OUTCOME for the chosen
        ``event_type`` (e.g. continuation rate, retest-&-hold rate, reversal
        rate) into ``{n, rate(s), day-of-week breakdown, avg moves}`` with a
        small-sample confidence note.

        This tool takes STRUCTURED conditions — the natural-language question is
        parsed into these params by the caller (the ``/backtest`` command or the
        ``backtest`` skill), not here.

        IMPORTANT — sample window: results are a RECENT live sample (the last
        ``days`` of 1H history, default ~180), NOT the full history the hosted
        dashboard aggregates. Always cite ``matched.n`` — a rate from n<5 is
        noise. There is NO macro/news data in this slice, so ``macro_present``
        is accepted but ignored (and so is ``range_state``, which the keyless
        engine does not tag).

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex/metals (e.g. ``EUR_USD``,
                ``XAU_USD``) ARE supported when ``RF_OANDA_TOKEN`` is set;
                crypto needs no key.
            event_type: The pattern to study. One of:
                ``session_range``, ``asia_sweep`` (London sweeps Asia),
                ``london_sweep`` (NY sweeps London), ``ny_continuation``,
                ``power_of_3``, ``smc_ob_test``, ``smc_fvg_test``,
                ``smc_bos_test``, ``smc_choch_test``, ``smc_eq_test``,
                ``smc_sweep_test``. Leave empty to get the list of valid types.
            session: Trading session filter (``asia``/``london``/``new_york``).
                Only meaningful for ``session_range``.
            day_of_week: ``Monday``..``Sunday``. Session-family events only —
                SMC events carry no formation date and the filter is noted as
                ignored for them.
            direction: ``bullish``/``bearish`` — the event's direction
                (session direction, NY direction, P3 distribution, or SMC bias).
            sweep_side: ``high``/``low``/``both`` — which side was swept
                (sweeps + Power-of-3 manipulation side).
            htf_bias: ``bullish``/``bearish`` — SMC structure bias (same as the
                SMC event's direction).
            range_state: Accepted but ignored (no tight/wide tagging here).
            days: Lookback in days of 1H history, capped at 365. ~60+ gives
                stable rates; the default ~180 tightens them.

        Returns:
            A dict with ``symbol``; echoed ``conditions``; ``window``
            (``candles``, ``from``/``to`` ISO-UTC, ``days``); ``matched`` (``n``);
            ``outcomes`` (the event-type-specific rates, each 0–100, with ``n``
            and a ``confidence`` bucket); ``day_of_week`` (per-weekday count +
            success rate, session events only); and ``notes`` (sample-window +
            any ignored conditions). When ``event_type`` is empty, returns the
            list of valid event types with a hint. On failure, an ``error`` key.
        """
        if not event_type:
            return {
                "error": "event_type is required.",
                "valid_event_types": list(event_query.ALL_EVENT_TYPES),
                "hint": (
                    "Pick one event_type, then narrow with optional conditions "
                    "(session, day_of_week, direction, sweep_side, htf_bias). "
                    "Each type answers a specific outcome — e.g. ny_continuation "
                    "→ how often NY continues London; smc_ob_test → retest & "
                    "hold rate; asia_sweep/london_sweep → post-sweep reversal "
                    "rate."
                ),
            }

        if event_type not in event_query.ALL_EVENT_TYPES:
            return {
                "error": f"Unknown event_type '{event_type}'.",
                "valid_event_types": list(event_query.ALL_EVENT_TYPES),
            }

        days = max(1, min(int(days), _MAX_DAYS))
        total = days * 24
        max_pages = max(2, (total // 1000) + 2)

        try:
            raw = await market.fetch_candles_paged(
                symbol, "1h", total=total, max_pages=max_pages
            )
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if len(raw) < _MIN_CANDLES:
            return {
                "error": (
                    f"Not enough candle data for {symbol}: got {len(raw)} 1H "
                    f"candles, need at least {_MIN_CANDLES}. Try a different "
                    "symbol or fewer days."
                )
            }

        all_events = event_query.build_event_set(raw)

        conditions = {
            "symbol": symbol.upper(),
            "event_type": event_type,
            "session": session,
            "day_of_week": day_of_week,
            "direction": direction,
            "sweep_side": sweep_side,
            "htf_bias": htf_bias,
            "range_state": range_state,
        }
        # Drop empty keys so the filter only applies the conditions actually set.
        active = {k: v for k, v in conditions.items() if v not in ("", None)}

        matched, filter_notes = _filter_events(all_events, active)
        outcomes = _aggregate(matched, event_type)
        dow = _day_of_week(matched, event_type)

        from_iso = datetime.fromtimestamp(raw[0]["time"], tz=timezone.utc).isoformat()
        to_iso = datetime.fromtimestamp(raw[-1]["time"], tz=timezone.utc).isoformat()
        span_days = max(1, round((raw[-1]["time"] - raw[0]["time"]) / 86400))

        notes = [
            (
                "Recent live sample only — the hosted backtester aggregates over "
                "FULL history, so these rates differ from the dashboard. Cite "
                f"matched.n ({len(matched)}) when interpreting."
            ),
            f"This study answers: rate of {_OUTCOME_LABEL.get(event_type, event_type)}.",
        ]
        notes.extend(filter_notes)
        if len(matched) < 5:
            notes.append(
                "Sample is very small (n<5) — treat any rate as noise, not edge."
            )

        return {
            "symbol": symbol.upper(),
            "conditions": active,
            "window": {
                "candles": len(raw),
                "timeframe": "1h",
                "from": from_iso,
                "to": to_iso,
                "days": span_days,
            },
            "matched": {"n": len(matched)},
            "outcomes": outcomes,
            "day_of_week": dow,
            "notes": notes,
        }
