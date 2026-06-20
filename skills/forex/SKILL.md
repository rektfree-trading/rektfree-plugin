---
name: forex
description: >-
  Forex & metals support setup and usage. Use when the user asks about analyzing
  forex/metals (EUR_USD, GBP_USD, USD_JPY, XAU_USD/gold, etc.), mentions OANDA,
  asks how to add their API token / set up forex, or hits the "needs an OANDA
  token" error. Explains that forex is bring-your-own-token and guides the setup.
---

# Forex & Metals (OANDA) — Setup & Usage

Crypto works with no keys (Binance is public). **Forex and metals need the user's
own OANDA API token** — the plugin never ships one. Almost every analysis tool
works on forex once the token is set; only `get_orderflow` and `get_derivatives`
stay crypto-only (OANDA has no tick or futures data).

## When the user wants forex

If they ask for a forex/metals symbol (anything with an underscore, e.g.
`EUR_USD`, `XAU_USD`) and get a "needs an OANDA API token" error, walk them
through setup:

1. **Get a token.** OANDA → Account → "Manage API Access" → generate a personal
   access token. A free **practice** (demo) account works and is the default.
2. **Set the environment variables** that the plugin's MCP server reads:
   - `RF_OANDA_TOKEN` — their token (required).
   - `RF_OANDA_ENV` — `practice` (default) or `live`, matching where the token
     was issued. (Or `RF_OANDA_BASE` for a custom host URL.)
   The simplest reliable way on macOS/Linux: add `export RF_OANDA_TOKEN=...` (and
   `export RF_OANDA_ENV=practice`) to their shell profile (`~/.zshrc` /
   `~/.bashrc`), then **fully restart Claude Code** so the MCP server picks up the
   new environment. (The server inherits the environment Claude Code launches
   with.) See `SETUP.md` for details.
3. **Verify.** After restart, `/smc EUR_USD 1h` (or any tool) should return real
   analysis instead of the token error. If a `/mcp` reconnect is needed, do that.

**Never ask the user to paste their token into the chat or a file** — it's a
secret; it only belongs in their own environment.

## Symbol format

Forex/metals use OANDA's underscore format — that's exactly the plugin's forex
convention: `EUR_USD`, `GBP_USD`, `USD_JPY`, `AUD_USD`, `XAU_USD` (gold),
`XAG_USD` (silver), etc. Crypto stays separator-free (`BTCUSDT`).

## What works on forex

All the structural/stat tools: `analyze_smc`, `get_levels`, `get_market_profile`,
`get_price_action`, `scan_confluence` / `scan_market`, `get_volatility`,
`get_correlations`, `get_daily_bias`, `get_ict_concepts`, `get_session_forecast`,
all the `compute_*_stats`, `run_backtest`, `discover_edges`. Sessions/killzones
apply too — and forex respects them more literally than 24/7 crypto.

**Not available for forex:** `get_orderflow` (no tick/footprint data) and
`get_derivatives` (no perp funding/OI). Those return a crypto-only message.

## Caveats to mention

- **Markets close on weekends** (Fri 21:00 → Sun 21:00 UTC). On weekends OANDA
  returns the last completed candles, so an intraday read may be stale — say so.
- **Practice vs live** pricing can differ slightly; it's fine for analysis.
- No macro/news awareness (same as crypto) — high-impact data can override the
  technical read.

See `SETUP.md` (plugin root) for the full install + token setup, including the
first-run dependency bootstrap.
