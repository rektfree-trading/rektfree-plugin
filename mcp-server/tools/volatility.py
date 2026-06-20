"""
``get_volatility`` — volatility & range context tool (crypto, keyless).

Fetches Binance intraday candles (for ATR / Bollinger / realized vol) and daily
candles (for ADR), runs the pure-Python volatility engine, and returns a clean
structured payload: ATR & ATR%, ADR with how much of today's range is used,
annualized realized volatility, Bollinger Band width with a squeeze read, and an
expansion-vs-contraction state. The host model interprets it for position
sizing, stop/target distances, and "is it about to move?" calls.
"""

from __future__ import annotations

from data import binance
from data import market
from engines import volatility as vol_engine


def register(mcp) -> None:
    @mcp.tool()
    async def get_volatility(
        symbol: str = "BTCUSDT",
        timeframe: str = "1h",
        atr_period: int = 14,
        adr_days: int = 14,
    ) -> dict:
        """Compute volatility & range context for a crypto symbol.

        Fetches candles from Binance (public, no API key) and derives the numbers
        traders use to size positions and judge whether there's room left to
        move: ATR and ATR% on the requested timeframe, Average Daily Range (ADR)
        with today's range and how much of the ADR is already used, annualized
        realized volatility, Bollinger Band width with a squeeze flag, and an
        overall expanding/contracting/neutral state. Returns structured JSON for
        the model to interpret — stop distance (~1× ATR), realistic targets
        (2–3× ATR), exhaustion warnings (high % of ADR used), and breakout
        anticipation (squeeze).

        Args:
            symbol: Binance crypto symbol with no separator, e.g. ``BTCUSDT``,
                ``ETHUSDT``, ``SOLUSDT``. Forex/metals (e.g. ``EUR_USD``,
                ``XAU_USD``) ARE supported when ``RF_OANDA_TOKEN`` is set;
                crypto needs no key.
            timeframe: Intraday timeframe for ATR/Bollinger/realized-vol —
                1m/5m/15m/1h/4h (aliases accepted). Default ``1h``. ADR always
                uses daily candles regardless of this.
            atr_period: Lookback for ATR, in candles of ``timeframe``. Default 14.
            adr_days: Number of completed days to average for ADR. Default 14.

        Returns:
            A dict shaped:
            ``{symbol, last_price, timeframe, atr:{value,pct,period,method},
            adr:{value,pct,days,today_range,pct_of_adr_used}, realized_vol:
            {annualized_pct,window,annualization}, bollinger:{width,squeeze,
            percentile,period}, state:{label,reason}}``. All prices are quote
            currency; ``*_pct`` fields are percent of last price. On failure, a
            dict with an ``error`` key.
        """
        atr_period = max(1, int(atr_period))
        adr_days = max(1, int(adr_days))

        # Window for realized vol & the squeeze lookback. Realized vol uses 30
        # periods; the BBW squeeze ranks against the last ~100 widths, which needs
        # ~120 closes. Pull a generous 300 intraday candles (also enough for a long
        # ATR50 comparison), and a longer ATR average needs >=51 candles.
        rv_window = 30
        squeeze_lookback = 100
        long_atr_period = 50
        bb_period = 20
        intraday_limit = 300

        try:
            interval = binance.normalize_timeframe(timeframe)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        # ADR uses daily candles; the last (current) day is partial so we average
        # the prior `adr_days` *completed* days and treat the latest as "today".
        try:
            intraday = await market.fetch_candles(symbol, timeframe, intraday_limit)
            daily = await market.fetch_candles(symbol, "1d", adr_days + 2)
        except binance.BinanceError as exc:
            return {"error": str(exc)}

        if not intraday or not daily:
            return {"error": f"No candle data returned for {symbol}."}

        # Need enough intraday candles for the longest computation we attempt.
        min_intraday = max(atr_period + 1, bb_period, rv_window + 1)
        if len(intraday) < min_intraday:
            return {
                "error": (
                    f"Not enough {timeframe} candles for {symbol}: got "
                    f"{len(intraday)}, need >= {min_intraday}."
                )
            }
        if len(daily) < 2:
            return {"error": f"Not enough daily candles for {symbol}."}

        highs = [c["high"] for c in intraday]
        lows = [c["low"] for c in intraday]
        closes = [c["close"] for c in intraday]
        last_price = closes[-1]

        # --- ATR (simple mean of true ranges) on the requested timeframe ---
        atr = vol_engine.atr_simple(highs, lows, closes, atr_period)
        atr_pct = (atr / last_price * 100.0) if last_price > 0 else 0.0
        # Longer ATR for the expansion/contraction comparison (best-effort).
        atr_long = vol_engine.atr_simple(highs, lows, closes, long_atr_period)

        # --- ADR over the last `adr_days` completed daily candles ---
        # Last daily candle is the current (partial) day → "today". The prior
        # `adr_days` candles are the completed days we average.
        today_candle = daily[-1]
        today_range = today_candle["high"] - today_candle["low"]
        completed = daily[:-1][-adr_days:]
        daily_ranges = [c["high"] - c["low"] for c in completed]
        adr = (sum(daily_ranges) / len(daily_ranges)) if daily_ranges else 0.0
        adr_pct = (adr / last_price * 100.0) if last_price > 0 else 0.0
        pct_of_adr_used = (today_range / adr * 100.0) if adr > 0 else 0.0

        # --- Realized volatility (annualized stdev of log returns) ---
        rv_pct, ann_factor = vol_engine.realized_vol(closes, rv_window, interval)

        # --- Bollinger Band width + squeeze ---
        widths = vol_engine.bbw_series(closes, bb_period, 2.0)
        bbw, bbw_pct_rank, is_squeeze = vol_engine.bbw_squeeze(
            widths, squeeze_lookback, squeeze_pct=0.25
        )

        # --- State: expansion vs contraction ---
        label, reason = _classify_state(atr, atr_long, is_squeeze, bbw_pct_rank, pct_of_adr_used)

        return {
            "symbol": symbol.upper(),
            "last_price": last_price,
            "timeframe": interval,
            "atr": {
                "value": atr,
                "pct": atr_pct,
                "period": atr_period,
                "method": "simple",
            },
            "adr": {
                "value": adr,
                "pct": adr_pct,
                "days": len(daily_ranges),
                "today_range": today_range,
                "pct_of_adr_used": pct_of_adr_used,
            },
            "realized_vol": {
                "annualized_pct": rv_pct,
                "window": rv_window,
                "annualization": f"sqrt({_ppy_label(interval)}) = {ann_factor:.2f}",
            },
            "bollinger": {
                "width": bbw,
                "squeeze": is_squeeze,
                "percentile": bbw_pct_rank,
                "period": bb_period,
            },
            "state": {"label": label, "reason": reason},
        }


def _ppy_label(interval: str) -> str:
    """Human label for the periods-per-year used in annualization."""
    ppy = vol_engine.PERIODS_PER_YEAR.get(interval, 365 * 24)
    return f"{ppy:g} periods/yr"


def _classify_state(
    atr: float,
    atr_long: float,
    is_squeeze: bool,
    bbw_percentile: float,
    pct_of_adr_used: float,
) -> tuple[str, str]:
    """Classify expansion vs contraction from ATR ratio + BBW squeeze.

    Primary signal: short ATR vs long ATR average. >1.15 = expanding (ranges
    growing), <0.85 = contracting. A Bollinger squeeze (BBW near its recent low)
    reinforces a contraction/coiling read even if ATR is mid-range. Returns
    ``(label, one-line reason)``.
    """
    ratio = (atr / atr_long) if atr_long > 0 else 1.0

    if is_squeeze:
        return (
            "contracting",
            f"Bollinger squeeze (BBW in bottom {bbw_percentile*100:.0f}% of recent range), "
            f"ATR is {ratio:.2f}× its longer average — compression, expansion likely.",
        )
    if ratio >= 1.15:
        note = ""
        if pct_of_adr_used >= 100:
            note = " Today's range already exceeds the average daily range — late-move risk."
        return (
            "expanding",
            f"ATR is {ratio:.2f}× its longer average — ranges growing / trending.{note}",
        )
    if ratio <= 0.85:
        return (
            "contracting",
            f"ATR is {ratio:.2f}× its longer average — ranges shrinking / coiling.",
        )
    return (
        "neutral",
        f"ATR is {ratio:.2f}× its longer average with no squeeze — normal volatility.",
    )
