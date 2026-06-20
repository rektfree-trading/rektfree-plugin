"""
``backtest_rr`` — R-multiple equity-curve backtest (crypto keyless; forex via OANDA).

A REAL first-touch trade simulation, complementary to ``run_backtest`` (which is a
frequency-only "how often does X lead to Y?" study). This tool turns the SAME
detected events into actual TRADES — defines a stop from ATR and a target from a
reward multiple, walks the candles forward to the first touch, and aggregates the
realised R-multiples into an equity curve plus expectancy / profit-factor /
drawdown statistics.

Division of labour matches the rest of the plugin: it fetches data and runs the
pure ``engines.strategy_sim`` math, returning structured JSON. Claude interprets.
No AI calls, no keys (beyond the optional OANDA token for forex/metals).

SCOPE NOTE: this models SESSION-FAMILY events only
(``session_range``/``asia_sweep``/``london_sweep``/``ny_continuation``/
``power_of_3``). The SMC-family events (``smc_*``) carry NO formation timestamp in
the keyless engine (``evaluate_smc_outcomes`` drops the date), so they cannot be
mapped to an entry candle and are rejected with a note — the same limitation that
makes day-of-week filtering impossible for them in ``run_backtest``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from data import binance
from data import market
from engines import event_query
from engines import strategy_sim

_MAX_DAYS = 365
_MIN_CANDLES = 48

# event_type → direction key in the flat event dict (all session-family events
# expose ``direction`` except sweeps, which we derive from the sweep side below).
_SESSION_TYPES = event_query.SESSION_EVENT_TYPES


def _event_direction(event: dict) -> str | None:
    """Map an event to a trade direction (``long``/``short``).

    Most session events carry ``direction`` (``bullish``/``bearish``). Sweeps
    carry ``sweep_side`` + a ``reversal`` flag instead: a swept HIGH that reverses
    is a SHORT setup, a swept LOW that reverses is a LONG setup. A sweep with no
    reversal (continuation) trades WITH the sweep side. ``both`` is ambiguous and
    skipped.
    """
    et = event.get("event_type")
    if et in ("asia_sweep", "london_sweep"):
        side = event.get("sweep_side")
        reversal = bool(event.get("reversal"))
        if side == "high":
            return strategy_sim.SHORT if reversal else strategy_sim.LONG
        if side == "low":
            return strategy_sim.LONG if reversal else strategy_sim.SHORT
        return None  # 'both' — ambiguous
    direction = event.get("direction")
    if direction == "bullish":
        return strategy_sim.LONG
    if direction == "bearish":
        return strategy_sim.SHORT
    return None


def simulate_events(
    candles: list[dict],
    events: list[dict],
    *,
    stop_atr_mult: float,
    target_r: float,
    atr_period: int,
    max_hold_bars: int,
) -> tuple[list[float], dict]:
    """Run every event through the simulator → (r_multiples, skip-reason counts).

    Pure: takes already-built session-family events and candles, resolves each
    event's entry candle, sizes the stop from ATR at entry, and simulates. Events
    with no entry candle / no direction / no forward bars / zero ATR are skipped
    and counted by reason.
    """
    r_multiples: list[float] = []
    skipped = {
        "no_entry_candle": 0,
        "no_direction": 0,
        "no_forward_bars": 0,
        "zero_atr": 0,
    }

    for ev in events:
        entry_idx = strategy_sim.resolve_entry_index(candles, ev)
        if entry_idx is None:
            skipped["no_entry_candle"] += 1
            continue
        direction = _event_direction(ev)
        if direction is None:
            skipped["no_direction"] += 1
            continue

        atr = strategy_sim.atr_at(candles, entry_idx, atr_period)
        stop_distance = stop_atr_mult * atr
        if stop_distance <= 0:
            skipped["zero_atr"] += 1
            continue

        entry_price = candles[entry_idx]["close"]
        trade = strategy_sim.simulate_trade(
            candles,
            entry_idx=entry_idx,
            direction=direction,
            entry=entry_price,
            stop_distance=stop_distance,
            target_r=target_r,
            max_hold_bars=max_hold_bars,
        )
        if trade is None:
            skipped["no_forward_bars"] += 1
            continue
        r_multiples.append(trade["r"])

    return r_multiples, skipped


def register(mcp) -> None:
    @mcp.tool()
    async def backtest_rr(
        symbol: str = "BTCUSDT",
        event_type: str = "",
        days: int = 180,
        stop_atr_mult: float = 1.0,
        target_r: float = 2.0,
        atr_period: int = 14,
        max_hold_bars: int = 48,
    ) -> dict:
        """Backtest an event as REAL trades → equity curve + R-multiple stats.

        Complementary to ``run_backtest`` (frequency only). This fetches deep 1H
        history, rebuilds the detected events with the vendored session engines,
        then for each signal opens a trade: entry at the signal candle's close,
        direction from the event (bullish→long, bearish→short; sweeps go with/against
        the swept side by whether they reversed), stop at ``stop_atr_mult × ATR``,
        target at ``target_r × stop_distance``. It WALKS the next ``max_hold_bars``
        candles and books the FIRST touch (stop → −1R, target → +target_r R, both
        in one bar → −1R stop-first), or a fractional R time-exit at the close if
        neither is hit. The realised R-multiples become an equity curve plus
        expectancy, win rate, profit factor, and max drawdown (all in R).

        SCOPE: session-family events only — ``session_range``, ``asia_sweep``,
        ``london_sweep``, ``ny_continuation``, ``power_of_3``. SMC events
        (``smc_*``) carry no formation timestamp in the keyless engine and cannot
        be mapped to an entry candle, so they are rejected.

        Args:
            symbol: Crypto symbol with no separator (``BTCUSDT``); forex/metals
                (``EUR_USD``, ``XAU_USD``) supported when ``RF_OANDA_TOKEN`` is set.
            event_type: One of the session-family types above. Leave empty to get
                the list of valid types.
            days: Lookback in days of 1H history, capped at 365. Default 180.
            stop_atr_mult: Stop distance as a multiple of ATR at entry. Default 1.0.
            target_r: Reward multiple — target = ``target_r × stop_distance``.
                Default 2.0.
            atr_period: ATR lookback in candles, measured at entry. Default 14.
            max_hold_bars: Max forward candles before a time-based exit. Default 48.

        Returns:
            A dict with ``symbol``, ``event_type``, ``params``, ``window``
            (candles/from/to ISO-UTC/days), ``stats`` (trades, win_rate,
            avg_win_R, avg_loss_R, expectancy_R, profit_factor, total_R,
            max_drawdown_R), ``equity_curve`` (cumulative-R points, possibly
            downsampled — ``stats.trades`` is the true n), ``confidence`` bucket,
            ``skipped`` (events dropped, by reason), and honest ``notes``. On bad
            input or a fetch failure, a dict with an ``error`` key (never raises).
        """
        if not event_type:
            return {
                "error": "event_type is required.",
                "valid_event_types": list(_SESSION_TYPES),
                "hint": (
                    "backtest_rr simulates session-family events as real trades. "
                    "SMC events are not supported (no formation timestamp). Pick "
                    "one of the listed types."
                ),
            }

        if event_type in event_query.SMC_EVENT_TYPES:
            return {
                "error": (
                    f"event_type '{event_type}' is an SMC event and cannot be "
                    "simulated here: the keyless SMC engine drops the formation "
                    "date, so there is no entry candle to walk forward from. Use "
                    "run_backtest for SMC hit-rates, or pick a session-family "
                    "event_type."
                ),
                "valid_event_types": list(_SESSION_TYPES),
            }

        if event_type not in _SESSION_TYPES:
            return {
                "error": f"Unknown event_type '{event_type}'.",
                "valid_event_types": list(_SESSION_TYPES),
            }

        days = max(1, min(int(days), _MAX_DAYS))
        stop_atr_mult = float(stop_atr_mult)
        target_r = float(target_r)
        atr_period = max(1, int(atr_period))
        max_hold_bars = max(1, int(max_hold_bars))
        if stop_atr_mult <= 0:
            return {"error": "stop_atr_mult must be > 0."}
        if target_r <= 0:
            return {"error": "target_r must be > 0."}

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
                    f"candles, need at least {_MIN_CANDLES}."
                )
            }

        all_events = event_query.build_event_set(raw)
        events = [e for e in all_events if e.get("event_type") == event_type]

        r_multiples, skipped = simulate_events(
            raw,
            events,
            stop_atr_mult=stop_atr_mult,
            target_r=target_r,
            atr_period=atr_period,
            max_hold_bars=max_hold_bars,
        )

        stats = strategy_sim.aggregate_stats(r_multiples)
        full_curve = stats.pop("equity_curve")
        returned_curve = strategy_sim.downsample(full_curve, cap=500)
        n = stats["trades"]

        from_iso = datetime.fromtimestamp(raw[0]["time"], tz=timezone.utc).isoformat()
        to_iso = datetime.fromtimestamp(raw[-1]["time"], tz=timezone.utc).isoformat()
        span_days = max(1, round((raw[-1]["time"] - raw[0]["time"]) / 86400))

        notes = [
            "First-touch simulation: on a bar that spans both stop and target, "
            "the STOP is assumed filled first (conservative — intrabar path is "
            "unknown, so results are an approximation).",
            "NO fees, slippage, or funding are modelled.",
            "Recent live sample only — the last ~"
            f"{span_days}d of 1H history, NOT full history.",
            f"Entry is the close of the signal's confirming session candle; stop = "
            f"{stop_atr_mult}× ATR{atr_period} at entry; target = {target_r}R.",
        ]
        if n < 5:
            notes.append(
                "Sample is very small (n<5) — treat expectancy/profit-factor as "
                "noise, not edge."
            )
        if len(returned_curve) < len(full_curve):
            notes.append(
                f"equity_curve downsampled to {len(returned_curve)} points from "
                f"{len(full_curve)} (stats.trades is the true n)."
            )

        return {
            "symbol": symbol.upper(),
            "event_type": event_type,
            "params": {
                "days": days,
                "stop_atr_mult": stop_atr_mult,
                "target_r": target_r,
                "atr_period": atr_period,
                "max_hold_bars": max_hold_bars,
            },
            "window": {
                "candles": len(raw),
                "timeframe": "1h",
                "from": from_iso,
                "to": to_iso,
                "days": span_days,
            },
            "signals_detected": len(events),
            "stats": stats,
            "equity_curve": returned_curve,
            "confidence": strategy_sim.confidence(n),
            "skipped": skipped,
            "notes": notes,
        }
