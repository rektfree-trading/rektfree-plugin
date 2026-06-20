"""
Shared helpers for tool modules.

Keeps the crypto-only guard and bias-string mapping consistent across every
tool so error messages and field encodings stay identical.
"""

from __future__ import annotations

from engines import smart_money


def crypto_only_error(symbol: str) -> dict | None:
    """Return an error dict if ``symbol`` looks like a forex pair, else None.

    Forex (OANDA) is bring-your-own-token and not wired up in this slice, so
    every keyless tool rejects ``_``-separated symbols with the same message.
    """
    if "_" in symbol:
        return {
            "error": (
                f"'{symbol}' looks like a forex pair. This tool only supports "
                "keyless crypto symbols (e.g. BTCUSDT) for now."
            )
        }
    return None


def bias_str(bias: int) -> str:
    """Map the engine's integer bias constant to a human string."""
    if bias == smart_money.BULLISH:
        return "bullish"
    if bias == smart_money.BEARISH:
        return "bearish"
    return "neutral"
