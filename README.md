# RektFree Plugin

A self-contained [Claude Code](https://code.claude.com) plugin for **Smart Money
Concepts (SMC)** and **key-levels** market analysis on crypto — with **Claude
itself as the analyst**.

The plugin ships RektFree's pure-Python analysis engines behind a small MCP
server. Claude calls a tool to fetch live Binance data and run the analysis, then
interprets the structure for you. There are no AI-provider API keys to manage —
the model you're already talking to *is* the brain.

> **Status: v0.2 (in progress).** Two tools (`analyze_smc`, `get_levels`), two
> commands (`/smc`, `/levels`), two skills (SMC, levels), crypto only (Binance,
> keyless). Forex, the confluence scanner, stats, and briefs are planned next.

## What you get

| Piece | What it does |
|---|---|
| `analyze_smc` MCP tool | Fetches Binance OHLCV (no API key) and runs the full SMC engine: BOS/CHoCH, order blocks, FVGs, equal highs/lows, liquidity sweeps, breaker blocks, premium/discount range. Returns structured JSON. |
| `get_levels` MCP tool | Fetches Binance 15m candles (no API key) and computes time-based levels: daily/weekly/monthly highs, lows, and opens (current + previous period) plus Asia/London/NY session highs & lows. Returns structured JSON. |
| `/smc` command | `/smc BTCUSDT 4h` — runs SMC analysis and asks Claude for a trader-facing read. |
| `/levels` command | `/levels BTCUSDT` — maps the key levels and asks Claude for support/resistance, liquidity, and bias. |
| `smc` skill | Auto-activates when you ask about structure, order blocks, FVGs, liquidity, or bias — turns the raw numbers into a decision-oriented analysis. |
| `levels` skill | Auto-activates when you ask about support/resistance, PDH/PDL, session highs/lows, or where liquidity is resting. |

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
  commands/
    smc.md               # /smc slash command
    levels.md            # /levels slash command
  skills/
    smc/
      SKILL.md           # SMC skill — Claude as analyst
      reference.md       # full SMC playbook (definitions + rules)
    levels/
      SKILL.md           # levels skill — Claude as analyst
      reference.md       # full key-levels playbook (definitions + rules)
  mcp-server/
    server.py            # FastMCP server — analyze_smc, get_levels tools
    requirements.txt     # mcp, httpx
    config.py            # optional env config (reserved for forex/OANDA)
    engines/
      smart_money.py     # vendored pure SMC analyzer (unchanged)
      levels.py          # vendored pure key-levels engine (unchanged)
    data/
      binance.py         # keyless Binance candle fetcher
```

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
- More tools: `get_market_profile`, `get_orderflow`, `scan_confluence`,
  `compute_stats`.
- `/brief`, `/scan`, `/stats` commands and their skills.
