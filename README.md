# RektFree Plugin

A self-contained [Claude Code](https://code.claude.com) plugin for **Smart Money
Concepts (SMC)**, **key levels**, **Market Profile**, **order flow**, and
**confluence scoring** market analysis on crypto — with **Claude itself as the
analyst**.

The plugin ships RektFree's pure-Python analysis engines behind a small MCP
server. Claude calls a tool to fetch live Binance data and run the analysis, then
interprets the structure for you. There are no AI-provider API keys to manage —
the model you're already talking to *is* the brain.

> **Status: v0.2 (in progress).** Seven tools (`analyze_smc`, `get_levels`,
> `get_market_profile`, `get_orderflow`, `scan_confluence`,
> `compute_session_stats`, `compute_smc_stats`) plus a `/analyze` synthesis layer
> that weaves them together; eight commands and eight skills, crypto only
> (Binance, keyless). Forex (OANDA, BYO-token) and pre-session briefs are next.

## What you get

| Piece | What it does |
|---|---|
| `analyze_smc` MCP tool | Fetches Binance OHLCV (no API key) and runs the full SMC engine: BOS/CHoCH, order blocks, FVGs, equal highs/lows, liquidity sweeps, breaker blocks, premium/discount range. Returns structured JSON. |
| `get_levels` MCP tool | Fetches Binance 15m candles (no API key) and computes time-based levels: daily/weekly/monthly highs, lows, and opens (current + previous period) plus Asia/London/NY session highs & lows. |
| `get_market_profile` MCP tool | Computes per-session Market Profile / TPO from Binance candles: POC, Value Area (VAH/VAL), and the bucketed letter profile. |
| `get_orderflow` MCP tool | Reconstructs footprint / order flow on the fly from Binance's keyless public aggregated-trades feed: per-price-level buy/sell volume, per-candle delta, running CVD, and large trades. |
| `scan_confluence` MCP tool | Grades a setup with the 0–N Smart Money confluence score across 1H + 4H (requires an aligned order block near price). Deterministic — no AI, no macro/DB inputs. Returns the score, factor breakdown, direction, target, and invalidation. |
| `compute_session_stats` MCP tool | Statistical edge: scans deep 1H history and reports per-session avg ranges, Asia→London / London→NY **sweep rates**, NY continuation rate, Power-of-3 occurrence, and a day-of-week breakdown (each with sample size). |
| `compute_smc_stats` MCP tool | SMC **hit rates** from a sliding window over 1H history: OB retest & hold rate, FVG fill rate & depth, BOS continuation rate, CHoCH reversal rate, EQH/EQL sweep, and liquidity-sweep success — each with its sample size `n`. |
| `/analyze` command + `synthesis` skill | The flagship read: orchestrates **all** the tools (HTF + entry-TF SMC, levels, profile, order flow, confluence) into one weighted brief — bias, key levels, flow, session context, a trade idea with target & invalidation, and risks. Auto-activates on "what's the setup / full read / bias / trade idea" questions. |
| `/smc` `/levels` `/profile` `/orderflow` `/scan` `/sessions` `/smcstats` commands | One-shot wrappers, e.g. `/scan BTCUSDT` — run a single tool and ask Claude for a trader-facing read. |
| `smc` · `levels` · `tpo` · `orderflow` · `scan` · `sessions` · `smcstats` skills | Auto-activate on the matching questions (structure/OBs/FVGs; support/resistance/PDH/PDL/sessions; POC/value area; delta/CVD/absorption; setup grading; session sweep rates; SMC hit rates) and turn the raw numbers into decision-oriented analysis. |

## Requirements

- **Python 3.10+** on your PATH (`python3`).
- The MCP server's two dependencies. Install them once:

  ```bash
  pip install -r mcp-server/requirements.txt
  # (mcp, httpx)
  ```

- Network access to `api.binance.com` (public endpoint — no account needed).

## Install

From a Claude Code session:

```
/plugin marketplace add rektfree-trading/rektfree-plugin
/plugin install rektfree-plugin@rektfree
```

(The repo is private during the beta — you'll need GitHub access to the
`rektfree-trading` org for the clone to succeed.)

Then reload, and try:

```
/smc BTCUSDT 1h
```

…or just ask in plain English: *"What's the SMC structure on ETH right now?"*

## Using the MCP server outside Claude Code

The server speaks standard [MCP](https://modelcontextprotocol.io) over stdio, so
Claude Desktop, Cursor, and other MCP clients can connect to it directly:

```json
{
  "mcpServers": {
    "rektfree": {
      "command": "python3",
      "args": ["/absolute/path/to/rektfree-plugin/mcp-server/server.py"],
      "env": { "PYTHONPATH": "/absolute/path/to/rektfree-plugin/mcp-server" }
    }
  }
}
```

(The slash command and skill are Claude Code-specific; the tool is portable.)

## Layout

```
rektfree-plugin/
  .claude-plugin/
    plugin.json          # plugin manifest
    marketplace.json     # makes this repo installable as a marketplace
  .mcp.json              # registers the stdio MCP server
  commands/                # slash commands
    analyze.md  smc.md  levels.md  profile.md  orderflow.md  scan.md  sessions.md  smcstats.md
  skills/                  # one SKILL.md + reference.md each
    synthesis/  smc/  levels/  tpo/  orderflow/  scan/  sessions/  smcstats/
  mcp-server/
    server.py            # FastMCP server — auto-discovers tools/*.register(mcp)
    requirements.txt     # mcp, httpx
    config.py            # optional env config (reserved for forex/OANDA)
    tools/
      _common.py         # shared crypto-only guard + bias helper
      smc.py  levels.py  market_profile.py  orderflow.py  confluence.py
      session_stats.py  smc_stats.py
    engines/             # vendored pure analyzers (unchanged from backend)
      smart_money.py  levels.py  market_profile.py  orderflow.py  confluence.py
      session_stats.py  smc_stats.py
    data/
      binance.py         # keyless Binance candle fetcher (+ shared retry/backoff, paged history)
      agg_trades.py      # keyless Binance aggregated-trades fetcher (order flow)
```

`synthesis` has no MCP tool of its own — it's a pure orchestration skill that
calls the other tools and weighs their output. Both data fetchers share one
retry/backoff helper, so transient Binance rate limits (429/418) and 5xx/network
blips are retried automatically rather than surfacing as hard errors.

Each tool lives in its own `tools/<name>.py` exposing `register(mcp)`; the server
auto-discovers them, so adding a tool never touches `server.py`.

## How it works

```
/smc or a question
      │
      ▼
  smc skill ──▶ analyze_smc (MCP tool)
                   │
                   ├─ data/binance.py   fetch OHLCV (keyless)
                   └─ engines/smart_money.py   run SMC analysis
                   │
                   ▼
              structured JSON
                   │
                   ▼
       Claude interprets ──▶ your trader-facing read
```

## Roadmap

- Forex/metals via OANDA (bring-your-own token) — `RF_OANDA_*` config is already
  stubbed in `config.py`.
- `/brief` — a pre-session brief command/skill that wraps `/analyze` with session
  timing.
- Deeper stat history — the on-the-fly stats currently sample the last ~3 months
  of 1H (Binance paging); the hosted product uses full history.
