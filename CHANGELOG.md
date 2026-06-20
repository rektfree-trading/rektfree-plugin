# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
