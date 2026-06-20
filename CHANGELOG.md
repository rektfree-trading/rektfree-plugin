# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-06-20

### Added
- Peak-points stats (`compute_peak_points_stats`): which session prints the day's high vs low, as marginals and a joint HOD×LOD probability matrix.
- Session-potential cards (`get_session_card`): per-session direction split, HOD/LOD odds, the clock-window extremes form in, and breakout tendency vs the prior session.
- Opening-range breakout stats (`compute_orb_stats`): first-break side, two-sided-break rate, outcome categories, and extension distribution — best on forex/indices.
- ETH value-area stats (`compute_eth_profile_stats`): how often the next day touches the prior day's POC/VAH/VAL, with average touch times.
- `/strategy` now ingests a broker CSV/XLSX trade export (auto broker-detection + column mapping) and emits per-rule compliance and signal-alignment tables; trade data stays local to the conversation.
- `SETUP.md` recipe for scheduling a pre-session `/brief` to recover the old auto-brief cadence without a server.
- Slash commands for the previously command-less tools — `/possize`, `/candles`, `/backtestrr` — so every tool is reachable by command, plus `/peakpoints`, `/sessioncard`, `/orb`, `/ethprofile` for the new stats.

### Changed
- `/brief` now folds in volatility/ATR sizing, cross-asset correlations, and (crypto) order flow — tools the brief already had but wasn't calling.

## [0.4.0] - 2026-06-20

### Added
- Position-sizing / risk tool: turn account size, risk percentage, and stop distance into a concrete position size.
- Raw `get_candles` tool: fetch OHLCV candles directly for any supported symbol and timeframe.
- R-multiple backtest with equity-curve output, so strategy results are expressed in R and a running balance.
- Stock-indices support (`NAS100_USD`, `SPX500_USD`, `US30_USD`, and friends) via OANDA, with forex and index scan presets.

### Changed
- Documented indices alongside crypto and forex/metals across the manifest and skills.

## [0.3.0] - 2026

### Added
- Forex and metals analysis via OANDA, using a bring-your-own (your own) OANDA token.
- Self-bootstrapping MCP setup so the server provisions its own dependencies on first run.

## [0.2.0] - 2026

### Added
- `run_backtest` tool for testing a strategy over historical data.
- `discover_edges` tool for surfacing statistical edges in market structure.
- Strategy skill to guide Claude through building and evaluating a setup.

## [0.1.0] - 2026

### Added
- Initial release: keyless Binance Smart Money Concepts analysis — order blocks, fair value gaps (FVGs), BOS/CHoCH, and liquidity sweeps.
- Statistical tooling for session and SMC stats.

[0.4.0]: https://github.com/rektfree-trading/rektfree-plugin/releases/tag/v0.4.0
[0.3.0]: https://github.com/rektfree-trading/rektfree-plugin/releases/tag/v0.3.0
[0.2.0]: https://github.com/rektfree-trading/rektfree-plugin/releases/tag/v0.2.0
[0.1.0]: https://github.com/rektfree-trading/rektfree-plugin/releases/tag/v0.1.0
