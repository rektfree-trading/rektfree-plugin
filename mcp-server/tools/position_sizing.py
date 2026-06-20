"""
``calc_position_size`` — pre-trade position sizing & risk math (crypto + forex/metals).

This is the arithmetic a disciplined trader runs *before* clicking buy: given an
account size and the percent of it they're willing to lose, plus an entry and a
stop, how many units can they hold so that getting stopped out costs exactly that
much — and, if a target is given, what's the resulting reward:risk? Everything is
pure-Python; no AI, no broker calls beyond an optional candle fetch when the stop
needs to be derived from ATR. The host model interprets the structured payload.
"""

from __future__ import annotations

from data import binance
from data import market
from engines import volatility as vol_engine


# ---------------------------------------------------------------------------
# Pure, unit-testable helpers (no network, no MCP decorator)
# ---------------------------------------------------------------------------

def infer_side(entry: float, stop: float, target: float = 0.0, side: str = "") -> str:
    """Resolve trade direction → "long" or "short".

    Explicit ``side`` wins. Otherwise infer from stop vs entry (a stop *below*
    entry implies a long). If the stop is unusable (0 or == entry), fall back to
    target vs entry. Defaults to "long" when nothing is decisive.
    """
    s = (side or "").strip().lower()
    if s in ("long", "buy"):
        return "long"
    if s in ("short", "sell"):
        return "short"
    if stop > 0 and stop != entry:
        return "long" if stop < entry else "short"
    if target > 0 and target != entry:
        return "long" if target > entry else "short"
    return "long"


def derive_stop_from_atr(entry: float, atr: float, mult: float, side: str) -> float:
    """Suggested stop price = entry ∓ (mult × ATR), placed against the trade.

    For a long the stop sits *below* entry; for a short, *above*. Returns 0.0 if
    inputs can't produce a stop on the correct side of entry.
    """
    if entry <= 0 or atr <= 0 or mult <= 0:
        return 0.0
    dist = mult * atr
    return entry - dist if side == "long" else entry + dist


def compute_sizing(
    account_equity: float,
    risk_pct: float,
    entry: float,
    stop: float,
    target: float = 0.0,
    side: str = "",
    leverage: float = 0.0,
) -> dict:
    """Core sizing math. Returns the result dict or an ``{"error": ...}`` dict.

    All prices are in the instrument's QUOTE currency. ``position_size_units`` is
    risk_amount / stop_distance, so the per-unit loss at the stop times the size
    equals exactly ``risk_amount`` *when the quote currency is the account
    currency*. This helper does not fetch data; the stop must already be a real
    price (ATR derivation happens in the tool layer).
    """
    # --- input validation (return, never raise) ---
    if account_equity is None or account_equity <= 0:
        return {"error": "account_equity must be > 0."}
    if risk_pct is None or not (0 < risk_pct <= 100):
        return {"error": "risk_pct must be in (0, 100]."}
    if entry is None or entry <= 0:
        return {"error": "entry must be > 0."}
    if stop is None or stop <= 0:
        return {"error": "stop must be > 0 (or provide symbol + stop_atr_mult to derive it)."}
    if stop == entry:
        return {"error": "stop must differ from entry (stop distance is zero)."}

    resolved_side = infer_side(entry, stop, target, side)

    # Sanity: stop should be on the losing side of entry for the resolved side.
    if resolved_side == "long" and stop >= entry:
        return {"error": f"For a long, stop ({stop}) must be below entry ({entry})."}
    if resolved_side == "short" and stop <= entry:
        return {"error": f"For a short, stop ({stop}) must be above entry ({entry})."}

    risk_amount = account_equity * (risk_pct / 100.0)
    stop_distance = abs(entry - stop)
    stop_distance_pct = stop_distance / entry * 100.0
    position_size_units = risk_amount / stop_distance
    notional_value = position_size_units * entry

    result: dict = {
        "side": resolved_side,
        "account_equity": account_equity,
        "risk_pct": risk_pct,
        "risk_amount": risk_amount,
        "entry": entry,
        "stop": stop,
        "stop_distance": stop_distance,
        "stop_distance_pct": stop_distance_pct,
        "position_size_units": position_size_units,
        "notional_value": notional_value,
    }

    # --- optional leverage / margin ---
    if leverage and leverage > 0:
        result["leverage"] = leverage
        result["required_margin"] = notional_value / leverage

    # --- optional target → R:R, reward, expectancy framing ---
    if target and target > 0 and target != entry:
        # Target must be on the winning side for the resolved direction.
        target_ok = (resolved_side == "long" and target > entry) or (
            resolved_side == "short" and target < entry
        )
        target_distance = abs(target - entry)
        reward_amount = position_size_units * target_distance
        rr_ratio = target_distance / stop_distance if stop_distance > 0 else 0.0
        result["target"] = target
        result["target_distance"] = target_distance
        result["target_distance_pct"] = target_distance / entry * 100.0
        result["reward_amount"] = reward_amount
        result["rr_ratio"] = rr_ratio
        result["r_multiples"] = {
            "risk_1R": risk_amount,
            "reward_R": rr_ratio,
            "note": (
                f"At target you make {rr_ratio:.2f}R "
                f"(${reward_amount:.2f}) for 1R risked (${risk_amount:.2f}). "
                f"Breakeven win-rate ≈ {100.0 / (1.0 + rr_ratio):.1f}% before fees."
            )
            if rr_ratio > 0
            else "Target is not on the profitable side of entry.",
        }
        if not target_ok:
            result["target_warning"] = (
                f"Target ({target}) is on the LOSING side of entry for a "
                f"{resolved_side}; reward/R:R is shown as an absolute distance only."
            )

    result["notes"] = _build_notes(result)
    return result


def _build_notes(result: dict) -> list[str]:
    """Honest, trader-facing caveats attached to every result."""
    notes = [
        "Units are derived from price-distance risk: position_size_units = "
        "risk_amount / stop_distance. The loss at your stop equals risk_amount "
        "ONLY when the instrument's quote currency is your account currency.",
        "This holds for USDT-quoted crypto (e.g. BTCUSDT) and all *_USD "
        "forex/metals/indices (EUR_USD, XAU_USD, NAS100_USD) when the account is "
        "in USD. For non-USD-quoted pairs (USD_JPY, EUR_GBP) the per-unit risk is "
        "in the QUOTE currency — convert to your account currency before trusting "
        "the size.",
        "For crypto, 'units' = base-asset units (e.g. BTC); notional is in quote. "
        "For forex via OANDA, 'units' = base-currency units (10000 units ≈ 0.1 "
        "standard lot).",
        "No fees, slippage, funding, or spread are modeled. This is risk-based "
        "sizing, not a guarantee of fill or of an exact loss.",
    ]
    if result.get("leverage"):
        notes.append(
            "required_margin = notional / leverage. Leverage changes margin and "
            "liquidation risk, NOT your sizing — your dollar risk is still set by "
            "the stop distance."
        )
    return notes


# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------

def register(mcp) -> None:
    @mcp.tool()
    async def calc_position_size(
        account_equity: float,
        risk_pct: float = 1.0,
        entry: float = 0.0,
        stop: float = 0.0,
        target: float = 0.0,
        side: str = "",
        symbol: str = "",
        timeframe: str = "1h",
        stop_atr_mult: float = 0.0,
        atr_period: int = 14,
        leverage: float = 0.0,
    ) -> dict:
        """Size a trade by risk: how many units to hold for a fixed % account risk.

        Given an account size and the percent of it you'll risk, plus an entry and
        a stop, computes the position size whose loss-at-stop equals exactly your
        intended dollar risk. If a target is supplied, also returns reward:risk and
        the breakeven win-rate. If you don't have a stop price, pass ``symbol`` +
        ``stop_atr_mult`` and the tool fetches candles, computes ATR, and places a
        stop at ``entry ∓ stop_atr_mult × ATR`` (against the trade direction).

        Use this when the user says things like "I have $10k, risk 1%, entry 100,
        stop 95 — how big?" or "size a long here with a 1.5×ATR stop and 3R target".

        Args:
            account_equity: Account size in the QUOTE/account currency (e.g. USD).
                Must be > 0.
            risk_pct: Percent of equity to risk on this trade. 1.0 = 1%. Must be in
                (0, 100]. Default 1.0.
            entry: Entry price (quote currency). Must be > 0.
            stop: Stop-loss price. If 0, supply ``symbol`` + ``stop_atr_mult`` to
                derive it from ATR. The resolved stop must differ from entry and sit
                on the losing side of the trade.
            target: Optional take-profit price → enables R:R, reward amount, and
                breakeven win-rate.
            side: "long"/"short". If empty, inferred from stop vs entry (stop below
                entry → long), then from target.
            symbol: Optional — needed only to derive a stop from ATR. Crypto with no
                separator (``BTCUSDT``) → Binance keyless; forex/metals with an
                underscore (``EUR_USD``, ``XAU_USD``) → OANDA.
            timeframe: Timeframe for the ATR fetch (1m/5m/15m/1h/4h/1d). Default 1h.
            stop_atr_mult: ATR multiple for a derived stop (e.g. 1.5). Ignored when
                ``stop`` is given. Default 0 (no derivation).
            atr_period: Lookback for the ATR used to derive a stop. Default 14.
            leverage: Optional. If > 0, also report required_margin = notional /
                leverage. Sizing/dollar-risk are unaffected by leverage.

        Returns:
            A dict shaped (target/leverage fields present only when supplied):
            ``{side, account_equity, risk_pct, risk_amount, entry, stop,
            stop_distance, stop_distance_pct, position_size_units, notional_value,
            leverage, required_margin, target, target_distance, target_distance_pct,
            reward_amount, rr_ratio, r_multiples:{risk_1R,reward_R,note},
            notes:[...]}``. When the stop is ATR-derived, an ``atr`` block records
            the value/period/timeframe used. On bad input or data failure, a dict
            with an ``error`` key (never raises).

        CAVEATS (also in ``notes``): sizing is exact only when the instrument's
        quote currency is your account currency (USDT crypto, *_USD pairs); for
        non-USD quotes convert per-unit risk yourself. No fees/slippage/funding
        modeled. Crypto units = base asset; forex units = OANDA base-currency units
        (10000 ≈ 0.1 lot).
        """
        # --- cheap up-front validation that doesn't need data ---
        if account_equity is None or account_equity <= 0:
            return {"error": "account_equity must be > 0."}
        if not (0 < risk_pct <= 100):
            return {"error": "risk_pct must be in (0, 100]."}
        if entry is None or entry <= 0:
            return {"error": "entry must be > 0."}

        atr_meta: dict | None = None

        # --- derive stop from ATR if needed ---
        if (not stop or stop <= 0) and symbol and stop_atr_mult and stop_atr_mult > 0:
            atr_period = max(1, int(atr_period))
            try:
                interval = binance.normalize_timeframe(timeframe)
            except binance.BinanceError as exc:
                return {"error": str(exc)}
            try:
                limit = max(atr_period + 5, 100)
                candles = await market.fetch_candles(symbol, timeframe, limit)
            except binance.BinanceError as exc:
                return {"error": str(exc)}
            if not candles or len(candles) < atr_period + 1:
                return {
                    "error": (
                        f"Not enough {timeframe} candles for {symbol} to compute "
                        f"ATR{atr_period} (need >= {atr_period + 1})."
                    )
                }
            highs = [c["high"] for c in candles]
            lows = [c["low"] for c in candles]
            closes = [c["close"] for c in candles]
            atr = vol_engine.atr_simple(highs, lows, closes, atr_period)
            if atr <= 0:
                return {"error": f"Computed ATR was 0 for {symbol}; cannot derive a stop."}
            resolved_side = infer_side(entry, 0.0, target, side)
            stop = derive_stop_from_atr(entry, atr, stop_atr_mult, resolved_side)
            atr_meta = {
                "value": atr,
                "period": atr_period,
                "timeframe": interval,
                "multiple": stop_atr_mult,
                "method": "simple",
                "derived_side": resolved_side,
                "last_price": closes[-1],
            }

        if not stop or stop <= 0:
            return {
                "error": (
                    "No usable stop: pass `stop`, or `symbol` + `stop_atr_mult` "
                    "(and an entry) to derive one from ATR."
                )
            }

        result = compute_sizing(
            account_equity=account_equity,
            risk_pct=risk_pct,
            entry=entry,
            stop=stop,
            target=target,
            side=side,
            leverage=leverage,
        )
        if "error" not in result and atr_meta is not None:
            result["atr"] = atr_meta
            result["stop_source"] = "atr_derived"
            result.setdefault("notes", []).append(
                f"Stop was derived from ATR: entry "
                f"{'−' if result['side'] == 'long' else '+'} "
                f"{stop_atr_mult}×ATR({atr_meta['period']}, {atr_meta['timeframe']}) "
                f"= {result['stop']:.6g}. ATR uses a simple mean of true ranges."
            )
        elif "error" not in result:
            result["stop_source"] = "explicit"
        return result
