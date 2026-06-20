# RektFree Plugin

A self-contained [Claude Code](https://code.claude.com) plugin for **Smart Money
Concepts (SMC)**, **key levels**, **Market Profile**, **order flow**,
**confluence scoring**, **session & SMC hit-rate stats**, and **futures
positioning** market analysis on crypto — with **Claude itself as the analyst**.

The plugin ships RektFree's pure-Python analysis engines behind a small MCP
server. Claude calls a tool to fetch live Binance data and run the analysis, then
interprets the structure for you. There are no AI-provider API keys to manage —
the model you're already talking to *is* the brain.

> **Status: v0.2 (in progress).** Twelve tools — `analyze_smc`, `get_levels`,
> `get_market_profile`, `get_orderflow`, `scan_confluence`, `scan_market`,
> `compute_session_stats`, `compute_smc_stats`, `get_derivatives`,
> `get_volatility`, `get_correlations`, `get_session_clock` — plus `/analyze`
> and `/brief` synthesis layers; thirteen commands and twelve skills, crypto
> only (Binance spot + futures, keyless). Forex (OANDA, BYO-token) is next.

## What you get

| Piece | What it does |
|---|---|
| `analyze_smc` MCP tool | Fetches Binance OHLCV (no API key) and runs the full SMC engine: BOS/CHoCH, order blocks, FVGs, equal highs/lows, liquidity sweeps, breaker blocks, premium/discount range. Returns structured JSON. |
| `get_levels` MCP tool | Fetches Binance 15m candles (no API key) and computes time-based levels: daily/weekly/monthly highs, lows, and opens (current + previous period) plus Asia/London/NY session highs & lows. |
| `get_market_profile` MCP tool | Computes per-session Market Profile / TPO from Binance candles: POC, Value Area (VAH/VAL), and the bucketed letter profile. |
| `get_orderflow` MCP tool | Reconstructs footprint / order flow on the fly from Binance's keyless public aggregated-trades feed: per-price-level buy/sell volume, per-candle delta, running CVD, and large trades. |
| `scan_confluence` MCP tool | Grades a setup with the 0–N Smart Money confluence score across 1H + 4H (requires an aligned order block near price). Deterministic — no AI, no macro/DB inputs. Returns the score, factor breakdown, direction, target, and invalidation. |
| `scan_market` MCP tool | Runs `scan_confluence` across a watchlist concurrently and returns the symbols **ranked** by score — market triage: "any setups right now?" Custom symbol lists, `only_actionable` filter, and an `actionable` count. |
| `compute_session_stats` MCP tool | Statistical edge: scans deep 1H history and reports per-session avg ranges, Asia→London / London→NY **sweep rates**, NY continuation rate, Power-of-3 occurrence, and a day-of-week breakdown (each with sample size). |
| `compute_smc_stats` MCP tool | SMC **hit rates** from a sliding window over 1H history: OB retest & hold rate, FVG fill rate & depth, BOS continuation rate, CHoCH reversal rate, EQH/EQL sweep, and liquidity-sweep success — each with its sample size `n`. |
| `get_derivatives` MCP tool | **Futures positioning** from keyless Binance Futures: funding rate (current %, annualized, next-funding countdown), open interest (value + change/trend), long/short account ratio (**global crowd + top-trader**), and taker buy/sell flow — with trend series for squeeze-risk reads. |
| `get_volatility` MCP tool | **Volatility & range context**: ATR (%), ADR + how much of today's range is used, annualized realized vol, Bollinger-band width / squeeze, and an expansion-vs-contraction state — for position sizing and "is a move coming?" |
| `get_correlations` MCP tool | **Cross-asset correlation**: timestamp-aligned log-return Pearson matrix across a watchlist + each symbol vs BTC, with a recent-vs-older **regime shift** (tightening / decoupling) for confirmation vs diversification. |
| `get_session_clock` MCP tool | Pure UTC **session/killzone clock**: current session & phase, next session + minutes, and the active/next killzone — powers `/brief`. |
| `/analyze` command + `synthesis` skill | The flagship read: orchestrates **all** the tools (HTF + entry-TF SMC, levels, profile, order flow, derivatives, confluence) into one weighted brief — bias, key levels, flow, positioning, session context, a trade idea with target & invalidation, and risks. Auto-activates on "what's the setup / full read / bias / trade idea" questions. |
| `/brief` command + `brief` skill | A forward-looking **pre-session brief**: anchors on the session clock (what session we're in, what's next, the killzone), then wraps `/analyze` + `compute_session_stats` into a session game-plan with statistical tendencies and an if-then watch-list. |
| `/smc` `/levels` `/profile` `/orderflow` `/scan` `/market` `/sessions` `/smcstats` `/derivatives` `/volatility` `/correlations` commands | One-shot wrappers, e.g. `/scan BTCUSDT` or `/market` — run a tool and ask Claude for a trader-facing read. |
| `smc` · `levels` · `tpo` · `orderflow` · `scan` · `sessions` · `smcstats` · `derivatives` · `volatility` · `correlations` skills | Auto-activate on the matching questions (structure/OBs/FVGs; support/resistance/PDH/PDL/sessions; POC/value area; delta/CVD/absorption; setup grading; session sweep rates; SMC hit rates; funding/OI/squeeze; ATR/ADR/squeeze; correlation/decoupling) and turn the raw numbers into decision-oriented analysis. |

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
    analyze.md  brief.md  smc.md  levels.md  profile.md  orderflow.md
    scan.md  market.md  sessions.md  smcstats.md  derivatives.md
    volatility.md  correlations.md
  skills/                  # one SKILL.md + reference.md each
    synthesis/  brief/  smc/  levels/  tpo/  orderflow/  scan/  sessions/
    smcstats/  derivatives/  volatility/  correlations/
  mcp-server/
    server.py            # FastMCP server — auto-discovers tools/*.register(mcp)
    requirements.txt     # mcp, httpx
    config.py            # optional env config (reserved for forex/OANDA)
    tools/
      _common.py         # shared crypto-only guard + bias helper
      smc.py  levels.py  market_profile.py  orderflow.py  confluence.py
      session_stats.py  smc_stats.py  derivatives.py  scan_market.py
      volatility.py  correlations.py  session_clock.py
    engines/             # pure analyzers (vendored from backend where applicable)
      smart_money.py  levels.py  market_profile.py  orderflow.py  confluence.py
      session_stats.py  smc_stats.py  volatility.py  correlations.py
    data/
      binance.py         # keyless Binance candle fetcher (+ shared retry/backoff, paged history)
      agg_trades.py      # keyless Binance aggregated-trades fetcher (order flow)
      derivatives.py     # keyless Binance Futures fetchers (funding/OI/long-short/taker)
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

## Development & tests

The server has a pytest suite under `mcp-server/tests/`:

```bash
cd mcp-server
pip install -r requirements-dev.txt
pytest                  # offline: pure engines, guards, retry logic, session clock
RF_LIVE_TESTS=1 pytest  # also run the live Binance contract tests (network)
```

The offline suite is fully deterministic (no network) and covers the analysis
engines, the data-layer retry/backoff, the shared guards, and the session clock.
The `live`-marked tests hit the public Binance API and assert every registered
MCP tool returns a clean payload end-to-end; they're skipped unless
`RF_LIVE_TESTS=1`.

**Engine-sync note:** the `engines/` analyzers are vendored from the
`rektfree-backend` repo. If those backend services change, re-copy them here and
re-run the suite (see `PLUGIN_STATUS.md` in the backend repo).

## Roadmap

- Forex/metals via OANDA (bring-your-own token) — `RF_OANDA_*` config is already
  stubbed in `config.py`.
- Deeper stat history — the on-the-fly stats currently sample the last ~3 months
  of 1H (Binance paging); the hosted product uses full history.
- A release tag once forex lands → **v0.2**.
