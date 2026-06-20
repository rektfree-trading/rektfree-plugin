"""
Optional runtime configuration for the RektFree MCP server.

Everything here is optional — crypto analysis works with zero config because
Binance's public endpoints need no key. Forex/OANDA support (future) will read
its credentials from the ``RF_OANDA_*`` variables below.

Values are read from the process environment, which the plugin's MCP config can
populate via ``${user_config.KEY}`` substitution (see ``.mcp.json``).
"""

from __future__ import annotations

import os

# OANDA (forex) — not yet wired into a tool; reserved for the BYO-keys path.
OANDA_TOKEN: str | None = os.environ.get("RF_OANDA_TOKEN")
OANDA_ACCOUNT_ID: str | None = os.environ.get("RF_OANDA_ACCOUNT_ID")
OANDA_ENV: str = os.environ.get("RF_OANDA_ENV", "practice")  # or "live"


def has_oanda() -> bool:
    """True when OANDA credentials are present (forex analysis available)."""
    return bool(OANDA_TOKEN and OANDA_ACCOUNT_ID)
