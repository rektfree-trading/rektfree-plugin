"""
SMC (Smart Money Concepts) hit-rate evaluation engine — PURE / keyless.

This is a vendored, database-free port of the backend's
``app/services/smc_stats.py``. It keeps the *evaluation math* identical: every
``_eval_*`` function below is copied verbatim from the backend so the outcomes a
detected pattern is scored against (OB retest/hold, FVG fill, BOS continuation,
CHoCH reversal, EQH/EQL sweep+reversal, liquidity-sweep success) match the
hosted product byte-for-byte.

What's DIFFERENT from the backend:
- No DB. The backend persists every per-structure outcome as a ``SessionEvent``
  row and aggregates with SQL in the ``/stats/smc`` router. Here the
  sliding-window helper (:func:`evaluate_smc_outcomes`) runs the same window
  loop and collects outcomes in memory; the tool layer aggregates them in
  Python (mirroring the router's ``/summary/{symbol}`` math).
- SMC dataclasses come from the plugin's vendored ``engines.smart_money``
  (``smart_money.OrderBlock`` etc.), NOT from ``app.services.smart_money``.

The backend evaluators read candles as dicts with ``c["high"]``, ``c["low"]``,
``c["close"]`` and derive date/session from a ``timestamp`` datetime. The plugin
fetches candles as ``{time, open, high, low, close, volume}`` floats, so the
helper adapts: high/low/close are already the right keys, and date/session are
derived from the unix-second ``time`` field via :func:`_ts_to_date` /
:func:`_hour_to_session`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from engines.smart_money import (
    BULLISH,
    EqualLevel,
    FairValueGap,
    LiquiditySweep,
    OrderBlock,
    StructureBreak,
    analyze,
)

# --- Sliding window parameters (verbatim from backend smc_stats.py) ---------
WINDOW_SIZE = 200
WINDOW_STEP = 50

# Look-forward limits (in candles / hours on 1H)
OB_LOOKAHEAD = 24
FVG_LOOKAHEAD = 48
BOS_LOOKAHEAD = 8
CHOCH_LOOKAHEAD = 12
EQ_LOOKAHEAD = 6
SWEEP_LOOKAHEAD = 12

# Threshold percentages
BOS_CONTINUATION_PCT = 0.3
CHOCH_REVERSAL_PCT = 0.5
EQ_REVERSAL_PCT = 0.3
SWEEP_SUCCESS_PCT = 1.0

# The 1H swing/eql params the plugin's SMC tool uses for 1H (see tools/smc.py
# ``_swing_params``). The backend calls analyze() with its own defaults; here we
# pass these explicitly to match the plugin's 1H SMC analysis.
SWING_LENGTH_1H = 20
INTERNAL_LENGTH = 5
EQL_THRESHOLD = 0.15
EQL_LENGTH_1H = 5


# ---------------------------------------------------------------------------
# Pure helpers (verbatim from backend)
# ---------------------------------------------------------------------------

def _hour_to_session(hour: int) -> str:
    """Map UTC hour to trading session name."""
    if 0 <= hour < 8:
        return "asia"
    elif 8 <= hour < 13:
        return "london"
    elif 13 <= hour < 21:
        return "new_york"
    else:
        return "off_hours"


def _ts_to_date(unix: float) -> date:
    return datetime.fromtimestamp(unix, tz=timezone.utc).date()


def _pct_move(base: float, target: float) -> float:
    if base == 0:
        return 0.0
    return abs(target - base) / base * 100


# ---------------------------------------------------------------------------
# Pattern outcome evaluators (verbatim from backend smc_stats.py)
# ---------------------------------------------------------------------------

def _eval_ob(ob: OrderBlock, candles: list[dict], start_idx: int) -> dict:
    """Did price retest the OB within OB_LOOKAHEAD candles?

    First we require price to MOVE AWAY from the OB zone (at least 3 candles
    where price is outside the OB range), then check if price RETURNS.
    """
    retested = False
    retested_within = 0
    held = False
    moved_away = False
    away_count = 0
    end = min(start_idx + OB_LOOKAHEAD, len(candles))

    for i in range(start_idx, end):
        c = candles[i]

        if ob.bias == BULLISH:
            # Price is "away" if its low is above the OB high (moved up from the OB)
            if c["low"] > ob.high:
                away_count += 1
            if away_count >= 3:
                moved_away = True
            # Retest = after moving away, price dips back into the OB zone
            if moved_away and c["low"] <= ob.high:
                retested = True
                retested_within = i - start_idx + 1
                held = c["close"] >= ob.low  # bounced above OB low
                break
        else:
            # Price is "away" if its high is below the OB low (moved down)
            if c["high"] < ob.low:
                away_count += 1
            if away_count >= 3:
                moved_away = True
            if moved_away and c["high"] >= ob.low:
                retested = True
                retested_within = i - start_idx + 1
                held = c["close"] <= ob.high  # rejected below OB high
                break

    return {
        "ob_bias": "bullish" if ob.bias == BULLISH else "bearish",
        "ob_high": round(ob.high, 6),
        "ob_low": round(ob.low, 6),
        "retested": retested,
        "retested_within": retested_within,
        "held": held,
        "trend_at_formation": None,  # set by caller
    }


def _eval_fvg(fvg: FairValueGap, candles: list[dict], start_idx: int) -> dict:
    """Did price fill (enter) the FVG within FVG_LOOKAHEAD candles?

    Skip the first 3 candles after formation to let price move away from
    the gap. Only then check if price RETURNS to fill it.
    """
    filled = False
    filled_within = 0
    filled_pct = 0.0
    gap_size = fvg.top - fvg.bottom
    max_fill = 0.0
    # Skip first 3 candles — price needs to move away before we test fill
    eval_start = start_idx + 3
    end = min(start_idx + FVG_LOOKAHEAD, len(candles))

    for i in range(eval_start, end):
        c = candles[i]
        if fvg.bias == BULLISH:
            # Bullish FVG sits below price; fill = price dips into gap
            if c["low"] <= fvg.top:
                penetration = fvg.top - max(c["low"], fvg.bottom)
                if penetration > max_fill:
                    max_fill = penetration
                if not filled:
                    filled = True
                    filled_within = i - start_idx + 1
        else:
            # Bearish FVG sits above price; fill = price rallies into gap
            if c["high"] >= fvg.bottom:
                penetration = min(c["high"], fvg.top) - fvg.bottom
                if penetration > max_fill:
                    max_fill = penetration
                if not filled:
                    filled = True
                    filled_within = i - start_idx + 1

    filled_pct = (max_fill / gap_size * 100) if gap_size > 0 else 0.0

    return {
        "fvg_bias": "bullish" if fvg.bias == BULLISH else "bearish",
        "fvg_top": round(fvg.top, 6),
        "fvg_bottom": round(fvg.bottom, 6),
        "filled": filled,
        "filled_within": filled_within,
        "filled_pct": round(filled_pct, 2),
        "trend_at_formation": None,
    }


def _eval_bos(brk: StructureBreak, candles: list[dict], start_idx: int) -> dict:
    """After a BOS, did price continue 0.3%+ in that direction within 4 candles?"""
    continuation = False
    max_move_pct = 0.0
    ref = brk.level
    end = min(start_idx + BOS_LOOKAHEAD, len(candles))

    for i in range(start_idx, end):
        c = candles[i]
        if brk.bias == BULLISH:
            move = _pct_move(ref, c["high"])
            if c["high"] > ref:
                max_move_pct = max(max_move_pct, move)
        else:
            move = _pct_move(ref, c["low"])
            if c["low"] < ref:
                max_move_pct = max(max_move_pct, move)

    continuation = max_move_pct >= BOS_CONTINUATION_PCT

    return {
        "bos_bias": "bullish" if brk.bias == BULLISH else "bearish",
        "level": round(brk.level, 6),
        "continuation": continuation,
        "max_move_pct": round(max_move_pct, 4),
        "trend_at_formation": None,
    }


def _eval_choch(brk: StructureBreak, candles: list[dict], start_idx: int) -> dict:
    """After a CHoCH, did price reverse 0.5%+ in the new direction within 8 candles?"""
    reversed_ = False
    max_move_pct = 0.0
    ref = brk.level
    end = min(start_idx + CHOCH_LOOKAHEAD, len(candles))

    for i in range(start_idx, end):
        c = candles[i]
        # CHoCH bias = the NEW direction
        if brk.bias == BULLISH:
            move = _pct_move(ref, c["high"])
            if c["high"] > ref:
                max_move_pct = max(max_move_pct, move)
        else:
            move = _pct_move(ref, c["low"])
            if c["low"] < ref:
                max_move_pct = max(max_move_pct, move)

    reversed_ = max_move_pct >= CHOCH_REVERSAL_PCT

    return {
        "choch_bias": "bullish" if brk.bias == BULLISH else "bearish",
        "level": round(brk.level, 6),
        "reversed": reversed_,
        "max_move_pct": round(max_move_pct, 4),
    }


def _eval_eq(eq: EqualLevel, candles: list[dict], start_idx: int) -> dict:
    """After an EQH/EQL is swept, did price reverse 0.3%+ within 6 candles?"""
    swept = False
    reversed_ = False
    reversal_pct = 0.0
    ref = eq.level
    end = min(start_idx + EQ_LOOKAHEAD, len(candles))

    for i in range(start_idx, end):
        c = candles[i]
        if eq.type == "EQH":
            # Expect sweep above then reversal down
            if c["high"] > ref:
                swept = True
            if swept:
                move_down = _pct_move(ref, c["low"])
                if c["low"] < ref:
                    reversal_pct = max(reversal_pct, move_down)
        else:
            # EQL: expect sweep below then reversal up
            if c["low"] < ref:
                swept = True
            if swept:
                move_up = _pct_move(ref, c["high"])
                if c["high"] > ref:
                    reversal_pct = max(reversal_pct, move_up)

    reversed_ = reversal_pct >= EQ_REVERSAL_PCT

    return {
        "eq_type": eq.type,
        "level": round(eq.level, 6),
        "swept": swept,
        "reversed": reversed_,
        "reversal_pct": round(reversal_pct, 4),
    }


def _eval_sweep(sweep: LiquiditySweep, candles: list[dict], start_idx: int) -> dict:
    """After a liquidity sweep, did price move 1%+ in expected direction within 12 candles?"""
    success = False
    max_move_pct = 0.0
    ref = sweep.level
    end = min(start_idx + SWEEP_LOOKAHEAD, len(candles))

    for i in range(start_idx, end):
        c = candles[i]
        if sweep.bias == BULLISH:
            move = _pct_move(ref, c["high"])
            if c["high"] > ref:
                max_move_pct = max(max_move_pct, move)
        else:
            move = _pct_move(ref, c["low"])
            if c["low"] < ref:
                max_move_pct = max(max_move_pct, move)

    success = max_move_pct >= SWEEP_SUCCESS_PCT

    return {
        "sweep_type": sweep.type,
        "level": round(sweep.level, 6),
        "success": success,
        "max_move_pct": round(max_move_pct, 4),
    }


# ---------------------------------------------------------------------------
# Sliding-window orchestration (in-memory replication of backend loop)
# ---------------------------------------------------------------------------

# Minimum candles required to run the window loop with usable look-forwards.
MIN_CANDLES = WINDOW_SIZE + max(OB_LOOKAHEAD, FVG_LOOKAHEAD, SWEEP_LOOKAHEAD)


def evaluate_smc_outcomes(candles: list[dict]) -> dict[str, list[dict]]:
    """Run the backend's sliding-window SMC evaluation in memory.

    Mirrors ``compute_smc_stats`` in the backend's ``services/smc_stats.py``:
    slides a ``WINDOW_SIZE``-candle window with ``WINDOW_STEP`` stride over the
    full 1H history; for each window it runs :func:`analyze`, then scores every
    detected OB / FVG / BOS / CHoCH / EQH-EQL / liquidity-sweep against the
    FUTURE candles using the ``_eval_*`` evaluators. Outcomes are de-duplicated
    across overlapping windows by absolute candle index (same keying scheme as
    the backend's ``seen_keys``) and collected in memory instead of persisted.

    Each candle dict must carry float ``time`` (unix seconds) plus
    ``open/high/low/close`` (the shape produced by
    ``data.binance.fetch_candles_paged``).

    Returns a dict keyed by event type
    (``ob_test``/``fvg_test``/``bos_test``/``choch_test``/``eq_test``/
    ``sweep_test``), each value a list of per-structure outcome dicts (the same
    dicts the backend would store in ``SessionEvent.data``, plus ``session``).
    """
    out: dict[str, list[dict]] = {
        "ob_test": [],
        "fvg_test": [],
        "bos_test": [],
        "choch_test": [],
        "eq_test": [],
        "sweep_test": [],
    }

    n = len(candles)
    if n < WINDOW_SIZE + 1:
        return out

    opens = [c["open"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    times = [c["time"] for c in candles]

    lookahead_max = max(OB_LOOKAHEAD, FVG_LOOKAHEAD, SWEEP_LOOKAHEAD)
    seen_keys: set[str] = set()

    def _session_for(abs_idx: int) -> str:
        hour = datetime.fromtimestamp(times[abs_idx], tz=timezone.utc).hour
        return _hour_to_session(hour)

    for win_start in range(0, n - WINDOW_SIZE + 1, WINDOW_STEP):
        win_end = win_start + WINDOW_SIZE
        if win_end >= n:
            break
        lookahead_end = min(win_end + lookahead_max, n)

        smc = analyze(
            opens[win_start:win_end],
            highs[win_start:win_end],
            lows[win_start:win_end],
            closes[win_start:win_end],
            times[win_start:win_end],
            swing_length=SWING_LENGTH_1H,
            internal_length=INTERNAL_LENGTH,
            eql_threshold=EQL_THRESHOLD,
            eql_length=EQL_LENGTH_1H,
        )

        # Forward candles: window tail + lookahead, sliced from the absolute
        # series so evaluator indexing matches the backend (which slices
        # candles[win_start:lookahead_end]).
        fwd_candles = candles[win_start:lookahead_end]
        fwd_len = len(fwd_candles)

        trend = "bullish" if smc.trend_bias == BULLISH else "bearish"

        # ---- Order Blocks ----
        for ob in smc.order_blocks:
            abs_idx = win_start + ob.bar_index
            key = f"ob_{abs_idx}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            fwd_start = ob.bar_index + 1
            if fwd_start >= fwd_len:
                continue
            result = _eval_ob(ob, fwd_candles, fwd_start)
            result["trend_at_formation"] = trend
            result["session"] = _session_for(abs_idx)
            out["ob_test"].append(result)

        # ---- Fair Value Gaps ----
        for fvg in smc.fair_value_gaps:
            abs_idx = win_start + fvg.bar_index
            key = f"fvg_{abs_idx}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            fwd_start = fvg.bar_index + 1
            if fwd_start >= fwd_len:
                continue
            result = _eval_fvg(fvg, fwd_candles, fwd_start)
            result["trend_at_formation"] = trend
            result["session"] = _session_for(abs_idx)
            out["fvg_test"].append(result)

        # ---- BOS / CHoCH ----
        for brk in smc.structures:
            abs_idx = win_start + brk.end_index
            if brk.type == "BOS":
                key = f"bos_{abs_idx}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                fwd_start = brk.end_index + 1
                if fwd_start >= fwd_len:
                    continue
                result = _eval_bos(brk, fwd_candles, fwd_start)
                result["trend_at_formation"] = trend
                result["session"] = _session_for(abs_idx)
                out["bos_test"].append(result)
            elif brk.type == "CHoCH":
                key = f"choch_{abs_idx}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                fwd_start = brk.end_index + 1
                if fwd_start >= fwd_len:
                    continue
                result = _eval_choch(brk, fwd_candles, fwd_start)
                result["trend_at_formation"] = trend
                result["session"] = _session_for(abs_idx)
                out["choch_test"].append(result)

        # ---- Equal Highs / Lows ----
        for eq in smc.equal_levels:
            abs_idx = win_start + eq.curr_index
            key = f"eq_{abs_idx}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            fwd_start = eq.curr_index + 1
            if fwd_start >= fwd_len:
                continue
            result = _eval_eq(eq, fwd_candles, fwd_start)
            result["session"] = _session_for(abs_idx)
            out["eq_test"].append(result)

        # ---- Liquidity Sweeps ----
        for sweep in smc.liquidity_sweeps:
            abs_idx = win_start + sweep.bar_index
            key = f"sweep_{abs_idx}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            fwd_start = sweep.bar_index + 1
            if fwd_start >= fwd_len:
                continue
            result = _eval_sweep(sweep, fwd_candles, fwd_start)
            result["session"] = _session_for(abs_idx)
            out["sweep_test"].append(result)

    return out
