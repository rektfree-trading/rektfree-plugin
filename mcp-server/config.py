"""
Optional runtime configuration for the RektFree MCP server.

Crypto analysis needs zero config — Binance's public endpoints need no key.
**Forex/metals** (OANDA) is bring-your-own-token: the user sets these environment
variables and the server inherits them (see ``data/oanda.py``, which reads them
directly). Never commit a token.

    RF_OANDA_TOKEN   OANDA REST API token (required for forex/metals)
    RF_OANDA_ENV     "practice" (default) or "live" — selects the OANDA host
    RF_OANDA_BASE    optional full base-URL override (instead of RF_OANDA_ENV)

Only the candles endpoint is used, which needs just the Bearer token — no account
id. See ``SETUP.md`` and the ``forex`` skill for user-facing setup guidance.
"""

from __future__ import annotations

import os

OANDA_TOKEN: str | None = os.environ.get("RF_OANDA_TOKEN")
OANDA_ENV: str = os.environ.get("RF_OANDA_ENV", "practice")  # or "live"


def has_oanda() -> bool:
    """True when an OANDA token is configured (forex analysis available)."""
    token = (OANDA_TOKEN or "").strip()
    return bool(token) and not token.startswith("${")
