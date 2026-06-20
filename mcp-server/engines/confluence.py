"""
Pure confluence scoring engine — keyless, DB-free, AI-free.

This is a faithful re-implementation of the PURE scoring math from the backend
``app/services/confluence_scanner.py``, extracted so the plugin can grade a
setup on freshly fetched Binance candles with NO database, NO AI provider, and
NO asset lists. It returns the numeric score + factor breakdown + structural
levels; the host (Claude) does all prose interpretation.

What this module deliberately does NOT do (and why), mirroring the backend's
inputs that the plugin cannot supply:

* **avoid-signatures** (backend ``_load_avoid_signatures`` /
  ``_candidate_avoid_match``): NEUTRALIZED — skipped entirely. Those signatures
  live in the backend ``discovered_edges`` table; with no DB there is nothing to
  match, so we treat every candidate as "no avoid match" (purely subtractive in
  the backend anyway, so dropping it only ever *keeps* a signal).
* **historical sweep-rate** (backend ``_get_sweep_rate``): NEUTRALIZED — passed
  as ``None``. The scorer already handles ``None`` (the "High sweep rate" +1
  bonus simply never fires).
* **order-flow delta** (backend ``_fetch_orderflow_delta``): NEUTRALIZED —
  passed as ``None``. Footprint data is DB-backed and crypto-only there; with
  ``None`` the order-flow +1/-1 factor never fires.
* **derivatives data** (backend funding/long-short/taker): NEUTRALIZED — passed
  as ``None``; that factor never fires.
* **macro risk** (backend ``macro_calendar`` DB): NEUTRALIZED to "no macro
  risk". The plugin has no macro calendar, so we never *deduct* for macro. Note
  the backend's macro factor is additive ("No macro events" +1), so treating
  macro as absent simply awards that point — consistent with the backend's
  behavior when no event is within the 2h window.
* **TPO levels** (backend ``_compute_tpo_levels``): REUSED — it is pure (POC/
  VAH/VAL computed straight from candle arrays via the vendored
  ``market_profile`` engine), so we keep it and award the +2 TPO confluence.

Everything below preserves the EXACT point weights and ``MIN_SCORE`` from the
backend, including the 2026-05 recalibration where killzone / silver-bullet /
mss-after-sweep were dropped to +0 (still appended to the factor list for
narrative context, but no longer push a signal over threshold). The
recalibration comments are kept verbatim so the discipline stays visible.
"""

from __future__ import annotations

from engines import market_profile, smart_money

# ─────────────────────────────────────────────────────────────────────────
# Constants — copied verbatim from the backend scanner.
# ─────────────────────────────────────────────────────────────────────────

# Session windows (UTC hours)
KILLZONES = [
    (7, 9, "London Open"),
    (12, 14, "NY Open"),
]

# Silver Bullet windows (UTC hours) — subset of killzones, highest precision
SILVER_BULLETS = [
    (7, 8, "London Silver Bullet"),
    (14, 15, "NY AM Silver Bullet"),
    (18, 19, "NY PM Silver Bullet"),
]

# MIN_SCORE bumped 5 → 6 after the 2026-05 recalibration backtest. The
# 2026-03/05 production sample (n=65 settled, WR=30.8%) showed score was
# essentially uncorrelated with outcome at score>=5. After re-weighting
# (sweep/tpo +1, silver_bullet/killzone/mss_after_sweep +0), threshold 6
# is the operating point that gives ~0.5/day at ~48% WR — the best honest
# tradeoff in the data.
MIN_SCORE = 6  # Only HIGH confidence signals

# Max target distance (% from entry). Plugin is crypto-only, so only the
# crypto cap is used; forex/index caps are kept for parity/reference.
MAX_TARGET_PCT_CRYPTO = 2.0  # 2% max for crypto
MAX_TARGET_PCT_FOREX = 1.0   # 1% max for forex
MAX_TARGET_PCT_INDEX = 1.5   # 1.5% for indices

# Counter-trend trades require a higher score (backend [FIX 5]).
COUNTER_TREND_MIN_SCORE = 8


# ─────────────────────────────────────────────────────────────────────────
# Pure candle helpers — adapted to the plugin's candle dict shape.
#
# Plugin candles are ``{"time": <unix seconds float>, "open","high","low",
# "close","volume": floats}`` (see data/binance.py). The backend used
# ``c["timestamp"]`` datetimes; here we read floats directly. The math is
# otherwise identical.
# ─────────────────────────────────────────────────────────────────────────


def _compute_adr_ratio(candles: list[dict]) -> float | None:
    """Today's range as a ratio of the average daily range.

    Adapted from the backend ``_compute_adr_ratio``: groups candles into UTC
    calendar days using the unix-second ``time`` field instead of a datetime.
    """
    if not candles:
        return None

    import datetime as _dt

    days: dict[str, dict] = {}
    for c in candles:
        dk = _dt.datetime.fromtimestamp(c["time"], _dt.timezone.utc).strftime("%Y-%m-%d")
        h, l = float(c["high"]), float(c["low"])
        if dk not in days:
            days[dk] = {"high": h, "low": l}
        else:
            days[dk]["high"] = max(days[dk]["high"], h)
            days[dk]["low"] = min(days[dk]["low"], l)

    if len(days) < 3:
        return None

    sorted_days = sorted(days.keys())
    today = sorted_days[-1]
    today_range = days[today]["high"] - days[today]["low"]

    prior_ranges = [days[d]["high"] - days[d]["low"] for d in sorted_days[:-1]]
    if not prior_ranges:
        return None
    adr = sum(prior_ranges) / len(prior_ranges)

    return today_range / adr if adr > 0 else None


def _compute_atr(candles: list[dict], period: int = 14) -> float | None:
    """ATR from candles. Identical math to the backend ``_compute_atr``."""
    if not candles or len(candles) < period + 1:
        return None

    trs = []
    for i in range(1, len(candles)):
        h = float(candles[i]["high"])
        l = float(candles[i]["low"])
        pc = float(candles[i - 1]["close"])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)

    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def _compute_tpo_levels(candles: list[dict]) -> dict | None:
    """Compute POC, VAH, VAL from recent candles.

    PURE — reused from the backend ``_compute_tpo_levels``. Only needs candle
    arrays; runs the vendored ``market_profile`` engine. Reads the plugin's
    float ``time`` key directly (the backend read ``c["timestamp"].timestamp()``).
    """
    if not candles or len(candles) < 20:
        return None

    try:
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        closes = [float(c["close"]) for c in candles]
        times = [float(c["time"]) for c in candles]

        profiles = market_profile.compute_profiles(
            highs, lows, closes, times,
            timeframe="1H", max_sessions=1,
        )
        if profiles:
            p = profiles[0]
            return {"poc": p.poc, "vah": p.vah, "val": p.val}
    except Exception:
        return None
    return None


# ─────────────────────────────────────────────────────────────────────────
# Pure SMC-derived helpers — copied verbatim from the backend scanner.
# These take only an SMCResult + price/direction, so they port unchanged.
# ─────────────────────────────────────────────────────────────────────────


def _check_recent_sweep(
    smc_result: smart_money.SMCResult,
    direction: str,
    num_candles: int,
) -> smart_money.LiquiditySweep | None:
    """Check if a liquidity sweep occurred recently on the OPPOSITE side."""
    if not smc_result.liquidity_sweeps:
        return None

    cutoff_index = num_candles - 30

    for sweep in reversed(smc_result.liquidity_sweeps):
        if sweep.bar_index < cutoff_index:
            break
        if direction == "long" and sweep.bias == smart_money.BULLISH:
            return sweep
        if direction == "short" and sweep.bias == smart_money.BEARISH:
            return sweep

    return None


def _check_choch_after_sweep(
    smc_result: smart_money.SMCResult,
    sweep: smart_money.LiquiditySweep,
    direction: str,
) -> smart_money.StructureBreak | None:
    """Check if a CHoCH/BOS occurred AFTER the liquidity sweep."""
    if not smc_result.structures:
        return None

    for struct in smc_result.structures:
        if struct.end_index <= sweep.bar_index:
            continue
        if direction == "long" and struct.bias == smart_money.BULLISH:
            return struct
        if direction == "short" and struct.bias == smart_money.BEARISH:
            return struct

    return None


def _find_draw_on_liquidity(
    smc_result: smart_money.SMCResult,
    current_price: float,
    direction: str,
) -> tuple[float, str] | None:
    """Find the nearest unswept liquidity target in the trade direction."""
    swept_levels = {round(s.level, 2) for s in smc_result.liquidity_sweeps}
    candidates: list[tuple[float, str]] = []

    for eq in smc_result.equal_levels:
        if round(eq.level, 2) in swept_levels:
            continue
        candidates.append((eq.level, eq.type))

    if smc_result.swing_high > 0 and round(smc_result.swing_high, 2) not in swept_levels:
        candidates.append((smc_result.swing_high, "Swing High"))
    if smc_result.swing_low > 0 and round(smc_result.swing_low, 2) not in swept_levels:
        candidates.append((smc_result.swing_low, "Swing Low"))

    if direction == "long":
        targets = [(p, d) for p, d in candidates if p > current_price]
        targets.sort(key=lambda x: x[0])
    else:
        targets = [(p, d) for p, d in candidates if p < current_price]
        targets.sort(key=lambda x: -x[0])

    return targets[0] if targets else None


def _check_ote_zone(
    ob: smart_money.OrderBlock,
    swing_high: float,
    swing_low: float,
    direction: str,
) -> bool:
    """Check if an OB sits within the OTE zone (0.618-0.786 fib retracement)."""
    rng = swing_high - swing_low
    if rng <= 0:
        return False

    ob_mid = (ob.high + ob.low) / 2

    if direction == "long":
        ote_high = swing_high - 0.618 * rng
        ote_low = swing_high - 0.786 * rng
        return ote_low <= ob_mid <= ote_high
    else:
        ote_low = swing_low + 0.618 * rng
        ote_high = swing_low + 0.786 * rng
        return ote_low <= ob_mid <= ote_high


def _find_nearest_structure_target(
    smc_result: smart_money.SMCResult,
    current_price: float,
    direction: str,
    max_pct: float,
) -> float | None:
    """Find the nearest structural level as target, capped to max_pct distance.

    Looks at: opposite-side OBs, FVGs, swing H/L, equal levels.
    Returns the NEAREST one within max_pct, or the max_pct cap if none found.
    Copied verbatim from the backend ``_find_nearest_structure_target``.
    """
    candidates: list[float] = []

    # Opposite-side OBs (bearish OBs above for longs, bullish OBs below for shorts)
    for ob in smc_result.order_blocks:
        ob_edge = ob.low if direction == "long" else ob.high
        if direction == "long" and ob.bias == smart_money.BEARISH and ob_edge > current_price:
            candidates.append(ob_edge)
        elif direction == "short" and ob.bias == smart_money.BULLISH and ob_edge < current_price:
            candidates.append(ob_edge)

    # FVGs in the target direction
    for fvg in smc_result.fair_value_gaps:
        if direction == "long" and fvg.mid > current_price:
            candidates.append(fvg.bottom)  # conservative: bottom of FVG
        elif direction == "short" and fvg.mid < current_price:
            candidates.append(fvg.top)  # conservative: top of FVG

    # Swing high/low
    if direction == "long" and smc_result.swing_high > current_price:
        candidates.append(smc_result.swing_high)
    elif direction == "short" and smc_result.swing_low > 0 and smc_result.swing_low < current_price:
        candidates.append(smc_result.swing_low)

    # Equal levels
    for eq in smc_result.equal_levels:
        if direction == "long" and eq.level > current_price:
            candidates.append(eq.level)
        elif direction == "short" and eq.level < current_price:
            candidates.append(eq.level)

    # Filter to within max_pct
    max_dist = current_price * max_pct / 100
    valid = []
    for c in candidates:
        dist = abs(c - current_price)
        if 0 < dist <= max_dist:
            valid.append(c)

    if not valid:
        # No structure level within cap — use the cap itself
        if direction == "long":
            return current_price * (1 + max_pct / 100)
        else:
            return current_price * (1 - max_pct / 100)

    # Return nearest
    if direction == "long":
        return min(valid)
    else:
        return max(valid)


# ─────────────────────────────────────────────────────────────────────────
# The scorer — copied verbatim from the backend ``_score_confluence``,
# preserving every point weight and recalibration note.
# ─────────────────────────────────────────────────────────────────────────


def _score_confluence(
    smc_result: smart_money.SMCResult,
    smc_4h: smart_money.SMCResult | None,
    smc_daily: smart_money.SMCResult | None,
    current_price: float,
    hour_utc: int,
    minute_utc: int,
    has_macro_risk: bool,
    num_candles: int,
    orderflow_delta: float | None = None,
    tpo_levels: dict | None = None,
    sweep_rate: float | None = None,
    derivatives_data: dict | None = None,
) -> tuple[int, list[str], str, bool]:
    """ICT Checklist-based confluence scoring.

    Returns (score, factors, direction, is_counter_trend).
    """
    score = 0
    factors = []
    bull_signals = 0
    bear_signals = 0

    # ═══════════════════════════════════════════════════════
    # Factor 1: HTF Directional Bias (D1 + 4H)
    # ═══════════════════════════════════════════════════════
    htf_bias = 0

    if smc_daily and smc_daily.trend_bias != 0:
        htf_bias = smc_daily.trend_bias
        trend_dir = "Bullish" if htf_bias == smart_money.BULLISH else "Bearish"
        score += 1
        factors.append(f"Daily {trend_dir} bias")
        if htf_bias == smart_money.BULLISH:
            bull_signals += 1
        else:
            bear_signals += 1

    if smc_4h and smc_4h.trend_bias != 0:
        h4_dir = "Bullish" if smc_4h.trend_bias == smart_money.BULLISH else "Bearish"
        if htf_bias == 0:
            htf_bias = smc_4h.trend_bias
        if smc_4h.trend_bias == htf_bias or htf_bias == 0:
            score += 1
            factors.append(f"4H confirms {h4_dir}")
            if smc_4h.trend_bias == smart_money.BULLISH:
                bull_signals += 1
            else:
                bear_signals += 1

    # Determine direction from HTF
    if bull_signals > bear_signals:
        direction = "long"
    elif bear_signals > bull_signals:
        direction = "short"
    elif smc_result.trend_bias == smart_money.BULLISH:
        direction = "long"
    else:
        direction = "short"

    # [FIX 5] Detect counter-trend: 1H trend disagrees with HTF
    is_counter_trend = False
    if htf_bias != 0:
        htf_dir = "long" if htf_bias == smart_money.BULLISH else "short"
        one_h_dir = "long" if smc_result.trend_bias == smart_money.BULLISH else "short"
        if direction != htf_dir or one_h_dir != htf_dir:
            is_counter_trend = True

    # ═══════════════════════════════════════════════════════
    # Factor 5: Entry Zone — OB near price (REQUIRED)
    # ═══════════════════════════════════════════════════════
    matched_ob = None
    for ob in smc_result.order_blocks:
        dist_pct = abs(current_price - (ob.high + ob.low) / 2) / current_price * 100
        if dist_pct < 0.5:
            if (direction == "long" and ob.bias == smart_money.BULLISH) or \
               (direction == "short" and ob.bias == smart_money.BEARISH):
                matched_ob = ob
                break

    # [FIX 2] No aligned OB near price = no signal (strictly enforced)
    if not matched_ob:
        return 0, [], direction, is_counter_trend

    ob_dir = "Bullish" if matched_ob.bias == smart_money.BULLISH else "Bearish"
    score += 2
    factors.append(f"{ob_dir} OB at {matched_ob.low:.2f}-{matched_ob.high:.2f}")

    # FVG overlap bonus
    for fvg in smc_result.fair_value_gaps:
        dist_pct = abs(current_price - fvg.mid) / current_price * 100
        if dist_pct < 0.5 and (
            (direction == "long" and fvg.bias == smart_money.BULLISH) or
            (direction == "short" and fvg.bias == smart_money.BEARISH)
        ):
            score += 1
            factors.append(f"FVG overlap at {fvg.bottom:.2f}-{fvg.top:.2f}")
            break

    # OTE zone check
    if _check_ote_zone(matched_ob, smc_result.swing_high, smc_result.swing_low, direction):
        score += 1
        factors.append("OB in OTE zone (0.618-0.786)")

    # ═══════════════════════════════════════════════════════
    # Factor 3+4: Liquidity Sweep → CHoCH sequence
    # Recalibrated 2026-05 from production backtest (n=65 settled):
    #   - sweep:        +1 → +2 (with-sweep WR 39.4% vs no-sweep 22%)
    #   - mss_after_sweep: +1 → 0 (n=12, WR 16.7%; ANTI-predictive — likely
    #     because by the time CHoCH prints, the entry chase is too late)
    # ═══════════════════════════════════════════════════════
    sweep = _check_recent_sweep(smc_result, direction, num_candles)
    if sweep:
        score += 2
        side = "lows" if direction == "long" else "highs"
        factors.append(f"Sweep of {side} at {sweep.level:.2f}")

        mss = _check_choch_after_sweep(smc_result, sweep, direction)
        if mss:
            # No score bump — backtest shows mss-after-sweep is anti-predictive.
            # Still surface the factor for narrative context.
            factors.append(f"{mss.type} after sweep at {mss.level:.2f}")

    # ═══════════════════════════════════════════════════════
    # Factor 2: Draw on Liquidity
    # ═══════════════════════════════════════════════════════
    dol = _find_draw_on_liquidity(smc_result, current_price, direction)
    if dol:
        level_price, level_desc = dol
        dist_pct = abs(level_price - current_price) / current_price * 100
        if dist_pct < 5.0:
            score += 1
            factors.append(f"Draw on liquidity: {level_desc} at {level_price:.2f}")

    # ═══════════════════════════════════════════════════════
    # Factor 6: Killzone / Silver Bullet timing
    # Recalibrated 2026-05: killzone/silver-bullet bonuses dropped to 0.
    #   - silver_bullet: was +2, observed WR 16.7% (n=12, lift -14%)
    #   - killzone:      was +1, observed WR 23.1% (n=13, lift -8%)
    #   - outside killzones: WR 37.5% (n=40, lift +7%)
    # Hypothesis: bonuses pulled the scanner into the noisy first 15-30min
    # of session liquidity grabs that frequently chop both ways. We still
    # surface them as factors for narrative context but they no longer
    # push a signal over the threshold.
    # ═══════════════════════════════════════════════════════
    total_min = hour_utc * 60 + minute_utc
    in_silver_bullet = False

    for start, end, name in SILVER_BULLETS:
        if start * 60 <= total_min < end * 60:
            # No score bump — backtest shows silver-bullet windows are
            # anti-predictive on our universe.
            factors.append(f"{name}")
            in_silver_bullet = True
            break

    if not in_silver_bullet:
        for start, end, name in KILLZONES:
            if start <= hour_utc < end:
                # No score bump — see note above.
                factors.append(f"{name} killzone")
                break

    # Session stats boost — kept at +1. Historical sweep-rate > 60% is
    # the only timing-adjacent signal that survived backtest (lift +4%
    # over baseline; with-sweep + high_sweep_rate together hits 44.8% WR).
    #
    # NEUTRALIZED in the plugin: there is no session-events DB, so
    # ``sweep_rate`` is always None and this factor never fires.
    if sweep_rate is not None and sweep_rate > 0.60:
        score += 1
        factors.append(f"High sweep rate ({sweep_rate:.0%})")

    # ═══════════════════════════════════════════════════════
    # Factor 7: Premium/Discount zone
    # [FIX 4] Require > 20% discount or > 80% premium to score
    # ═══════════════════════════════════════════════════════
    if smc_result.swing_high > 0 and smc_result.swing_low > 0:
        rng = smc_result.swing_high - smc_result.swing_low
        if rng > 0:
            pct = (current_price - smc_result.swing_low) / rng * 100
            if pct < 20 and direction == "long":
                score += 1
                factors.append(f"Deep discount zone ({pct:.0f}%)")
            elif pct > 80 and direction == "short":
                score += 1
                factors.append(f"Deep premium zone ({pct:.0f}%)")

    # ═══════════════════════════════════════════════════════
    # Factor 8: Macro event risk
    #
    # NEUTRALIZED in the plugin: no macro calendar DB. We always pass
    # has_macro_risk=False, so this +1 always fires — matching the
    # backend's behavior when no event is within its 2h window.
    # ═══════════════════════════════════════════════════════
    if not has_macro_risk:
        score += 1
        factors.append("No macro events")

    # ═══════════════════════════════════════════════════════
    # Factor 9: Order flow + Derivatives
    #
    # NEUTRALIZED in the plugin: footprint/derivatives are DB-backed, so
    # orderflow_delta and derivatives_data are always None. Neither the
    # +1/-1 order-flow factor nor the derivatives factor ever fires.
    # ═══════════════════════════════════════════════════════
    if orderflow_delta is not None:
        delta_confirms = (orderflow_delta > 0 and direction == "long") or \
                         (orderflow_delta < 0 and direction == "short")
        if delta_confirms:
            score += 1
            side = "buyers" if orderflow_delta > 0 else "sellers"
            factors.append(f"Order flow confirms ({side})")
        else:
            score -= 1
            factors.append("Order flow diverges")

    if derivatives_data:
        deriv_signals = 0
        fr = derivatives_data.get("funding_rate", 0)
        ls = derivatives_data.get("long_short_ratio")
        taker = derivatives_data.get("taker_buy_sell_ratio")

        if direction == "long" and fr < -0.0003:
            deriv_signals += 1
        elif direction == "short" and fr > 0.0005:
            deriv_signals += 1

        if ls:
            if direction == "long" and ls < 0.8:
                deriv_signals += 1
            elif direction == "short" and ls > 1.3:
                deriv_signals += 1

        if taker:
            if direction == "long" and taker > 1.1:
                deriv_signals += 1
            elif direction == "short" and taker < 0.9:
                deriv_signals += 1

        if deriv_signals >= 2:
            score += 1
            factors.append(f"Derivatives confirm ({deriv_signals}/3 signals)")
        elif deriv_signals == 0 and fr != 0:
            score -= 1
            factors.append("Derivatives oppose direction")

    # ═══════════════════════════════════════════════════════
    # Factor 10: Multi-TF alignment + TPO confluence
    # ═══════════════════════════════════════════════════════
    tf_aligned = 0
    target_bias = smart_money.BULLISH if direction == "long" else smart_money.BEARISH
    if smc_result.trend_bias == target_bias:
        tf_aligned += 1
    if smc_4h and smc_4h.trend_bias == target_bias:
        tf_aligned += 1
    if smc_daily and smc_daily.trend_bias == target_bias:
        tf_aligned += 1

    if tf_aligned >= 3:
        score += 1
        factors.append("Full MTF alignment (1H+4H+D)")

    # TPO confluence — upweighted from +1 to +2 after 2026-05 backtest.
    # Observed WR 35.9% with tpo_align (n=39, +5% lift) and 40.0% paired
    # with sweep (n=25, +9% lift). One of two consistently positive
    # factors alongside `sweep` itself. PURE — kept active in the plugin.
    if tpo_levels and matched_ob:
        ob_mid = (matched_ob.high + matched_ob.low) / 2
        ob_range = matched_ob.high - matched_ob.low
        tolerance = max(ob_range, current_price * 0.003)

        for level_name, level_price in [
            ("POC", tpo_levels["poc"]),
            ("VAH", tpo_levels["vah"]),
            ("VAL", tpo_levels["val"]),
        ]:
            if abs(ob_mid - level_price) <= tolerance:
                score += 2
                factors.append(f"OB aligns with {level_name} ({level_price:.2f})")
                break

    return score, factors, direction, is_counter_trend


# ─────────────────────────────────────────────────────────────────────────
# Clean entrypoint for the plugin tool.
# ─────────────────────────────────────────────────────────────────────────


def score_setup(
    smc_1h: smart_money.SMCResult,
    smc_4h: smart_money.SMCResult | None,
    candles_1h: list[dict],
    candles_4h: list[dict],
    current_price: float,
    now_utc,
) -> dict:
    """Grade a setup by stacking SMC confluence across 1H + 4H.

    This is the plugin's deterministic, structural-only confluence grade. It
    mirrors the backend scanner's scoring math EXACTLY but neutralizes every
    DB/AI input the plugin can't supply (see module docstring): no daily SMC,
    no avoid-signatures, no historical sweep-rate, no order-flow delta, no
    derivatives, no macro DB. Macro is treated as "no event" (the backend's +1
    "No macro events" fires), so this is a clean structural ceiling on the
    score — Claude does the prose interpretation.

    Args:
        smc_1h: SMCResult from the 1H candles (swing_length=20).
        smc_4h: SMCResult from the 4H candles (swing_length=10), or None.
        candles_1h: 1H candle dicts (for ATR / ADR / TPO).
        candles_4h: 4H candle dicts (currently unused by the scorer, accepted
            for symmetry and future use).
        current_price: Last close on 1H.
        now_utc: A timezone-aware ``datetime`` in UTC (for killzone timing).

    Returns:
        ``{score, min_score, meets_threshold, direction, is_counter_trend,
        factors, target, invalidation}``.
    """
    hour_utc = now_utc.hour
    minute_utc = now_utc.minute

    # NEUTRALIZED inputs — see module docstring for the rationale on each:
    smc_daily = None          # no separate daily fetch in the plugin slice
    has_macro_risk = False    # no macro calendar DB → treat as no event risk
    orderflow_delta = None    # no footprint DB
    sweep_rate = None         # no session-events DB
    derivatives_data = None   # no derivatives DB

    # TPO is pure (computed from 1H candles) — kept active.
    tpo_levels = _compute_tpo_levels(candles_1h)

    score, factors, direction, is_counter_trend = _score_confluence(
        smc_1h,
        smc_4h,
        smc_daily,
        current_price,
        hour_utc,
        minute_utc,
        has_macro_risk,
        num_candles=len(candles_1h),
        orderflow_delta=orderflow_delta,
        tpo_levels=tpo_levels,
        sweep_rate=sweep_rate,
        derivatives_data=derivatives_data,
    )

    # Threshold + counter-trend gating, mirroring scan_symbol. We DON'T return
    # None here (that's the backend's emit/skip decision) — the plugin always
    # reports the grade and lets Claude apply the go/no-go read.
    meets_threshold = score >= MIN_SCORE
    if is_counter_trend and score < COUNTER_TREND_MIN_SCORE:
        # Counter-trend setups need a higher bar; surface that they fail it.
        meets_threshold = False

    # Structural target — nearest level within the crypto cap (plugin is
    # crypto-only). Mirrors _find_nearest_structure_target in scan_symbol.
    target = _find_nearest_structure_target(
        smc_1h, current_price, direction, MAX_TARGET_PCT_CRYPTO,
    )

    # Dynamic ATR-based invalidation (backend [FIX 6]): 1.5x ATR, else 1%.
    atr = _compute_atr(candles_1h)
    if atr and atr > 0:
        atr_mult = 1.5
        if direction == "long":
            invalidation = current_price - (atr * atr_mult)
        else:
            invalidation = current_price + (atr * atr_mult)
    else:
        if direction == "long":
            invalidation = current_price * 0.99
        else:
            invalidation = current_price * 1.01

    return {
        "score": score,
        "min_score": MIN_SCORE,
        "meets_threshold": meets_threshold,
        "direction": direction,
        "is_counter_trend": is_counter_trend,
        "factors": factors,
        "target": target,
        "invalidation": invalidation,
    }
