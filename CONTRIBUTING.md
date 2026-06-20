# Contributing

Thanks for helping improve RektFree. This is a Claude Code plugin: an MCP
server plus skills and slash commands. Contributions are welcome.

## Running the tests

Offline tests run without any network or credentials:

```bash
cd mcp-server && python -m pytest tests/ -q -k "not live"
```

Live contract tests hit real data providers and are gated behind an env var,
so they stay off by default:

```bash
RF_LIVE_TESTS=1 python -m pytest tests/ -q
```

## Adding a tool

Tools are auto-discovered. To add one, create a new file in `mcp-server/tools/`
that exposes a `register(mcp)` function — that's it. **Never edit `server.py`**;
it discovers and registers every tool module for you.

## Purity rule

Engines and tools must stay dependency-light. They may import only:

- the Python standard library,
- local packages within this plugin, and
- `mcp`.

Do **not** import `numpy`, `pandas`, `sqlalchemy`, or anything under `app.*`.
This keeps the server portable and fast to bootstrap.

## Secrets

Never commit secrets. In particular, never commit an OANDA token (or any other
credential) — tokens are provided by each user at runtime, not stored in the repo.
