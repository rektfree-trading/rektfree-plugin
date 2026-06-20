# RektFree — Setup & Troubleshooting

## Install (one step)

```
/plugin marketplace add rektfree-trading/rektfree-plugin
/plugin install rektfree-plugin@rektfree
```

That's it. No manual `pip install`. The MCP server bootstraps its own
dependencies on first launch.

## What happens on first run

The server is launched through `mcp-server/bootstrap.py`. On the **very first**
launch it:

1. Creates a small, isolated Python environment (a venv) in a per-user cache
   dir:
   - macOS: `~/Library/Caches/rektfree-plugin/venv`
   - Linux: `~/.cache/rektfree-plugin/venv` (respects `XDG_CACHE_HOME`)
   - Windows: `%LOCALAPPDATA%\rektfree-plugin\venv`
2. Installs the pinned dependencies (`mcp`, `httpx`) into it.
3. Launches the actual server.

This one-time setup takes roughly **10–30 seconds**. We use a cache dir (not the
plugin folder) so the environment survives plugin reinstalls and works even if
the plugin directory is read-only.

On **every later launch** the bootstrap detects the ready venv and starts the
server **instantly** (no install, no delay).

## First-connect timeout caveat (read this)

Claude Code has a connection timeout for MCP servers. Because the first-run
setup can take longer than that timeout, **the very first connect may report
that the server failed to connect.** That's expected — the environment is still
finishing in the background.

**Fix: just reconnect once.** Open the MCP panel and reconnect:

```
/mcp
```

Select `rektfree` and reconnect. By now the venv is built, so it connects
immediately and the tools (`analyze_smc`, etc.) appear.

You'll only ever see this on the first install. Subsequent sessions connect
instantly.

## Forex & metals (optional — bring your own OANDA token)

Crypto needs no keys. **Forex/metals** (`EUR_USD`, `GBP_USD`, `XAU_USD`/gold, …)
use OANDA, which requires *your own* API token — the plugin never ships one.

1. Generate a token in OANDA (Account → **Manage API Access**). A free
   **practice** account works.
2. Set these environment variables so the MCP server (which inherits Claude
   Code's environment) can read them — e.g. add to `~/.zshrc` / `~/.bashrc`:

   ```bash
   export RF_OANDA_TOKEN="your-oanda-token"
   export RF_OANDA_ENV="practice"   # or "live" — must match where the token was issued
   ```
3. **Fully restart Claude Code** (so the server picks up the new environment),
   then try `/smc EUR_USD 1h`. If needed, reconnect once via `/mcp`.

The **same OANDA token also unlocks stock indices** (CFDs) — `NAS100_USD`
(Nasdaq 100), `SPX500_USD` (S&P 500), `US30_USD` (Dow), `DE30_EUR` (DAX),
`UK100_GBP` (FTSE), `JP225_USD` (Nikkei) — and CFD metals like `XAU_USD` (gold)
and `XAG_USD` (silver). No extra setup: any underscore symbol routes to OANDA.
Indices follow their exchange's hours (not FX's 24/5), so off-hours reads may be
stale.

Notes: never paste your token into the chat — it belongs only in your
environment. All structural/stat tools work on forex; `get_orderflow` and
`get_derivatives` stay crypto-only (OANDA has no tick/futures data). Forex markets
close on weekends (Fri 21:00 → Sun 21:00 UTC). Just ask Claude "how do I set up
forex?" and the `forex` skill will walk you through it.

## Troubleshooting

- **Tools still missing after a reconnect?** Check the bootstrap's notes — it
  logs progress to stderr with a `[rektfree-bootstrap]` prefix (visible in the
  MCP server logs). It tells you whether it's building the venv, hit a pip
  error, etc.
- **Manual fallback.** If automatic setup fails (e.g. no network during the
  first run), you can install the deps yourself and reconnect:

  ```
  python3 -m pip install -r <plugin>/mcp-server/requirements.txt
  ```

  If your `python3` already has `mcp` and `httpx`, the bootstrap will detect
  that and skip building a venv entirely.
- **Force a clean rebuild.** Delete the cache venv and reconnect via `/mcp`:
  - macOS: `rm -rf ~/Library/Caches/rektfree-plugin`
  - Linux: `rm -rf ~/.cache/rektfree-plugin`
  - Windows: remove `%LOCALAPPDATA%\rektfree-plugin`
