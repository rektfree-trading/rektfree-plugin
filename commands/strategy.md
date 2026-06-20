---
description: Review a trader's trades or strategy against the RektFree framework — ingest an attached/at-a-path broker export (CSV/XLSX) or pasted trades, parse them, compute win-rate / R / expectancy and by-symbol / session / day-of-week breakdowns, cross-reference representative entries against live SMC / levels / sessions / stats, emit per-rule compliance + alignment-delta tables, run a gap analysis vs the RektFree edge, and deliver a structured critique + concrete improvement plan.
argument-hint: [attach a broker export, paste trades, or describe your strategy]
---

Review the user's trading — an **attached / at-a-path broker export** (CSV/XLSX),
a pasted list of trades, or a free-text description of their strategy — against
the RektFree framework, and return a structured critique with a concrete
improvement plan. **You are the analyst:** you read and parse the trades yourself
(file or pasted) and orchestrate the plugin's analysis tools for objective market
context. Use the **strategy** skill for the full playbook.

Input: `$ARGUMENTS` (plus any attached file / path the user gave)

Steps:

1. **Read what the user gave you.** It is one of:
   - **A broker export file** — attached or at a path (`.csv`, `.xlsx`, `.xls`
     from MT4/MT5, cTrader, TradingView, Binance/Bybit/OANDA, or generic). **Read
     it yourself** (no parser tool exists — don't add one). Auto-detect the broker
     and **map the columns** (time / symbol / side / entry / exit / size / P&L)
     using the header-synonym heuristics in the skill (`Profit`/`PnL`/`Net P/L`;
     `Type`/`Side`/`Direction`; `Open Time`/`Entry Time`…), **skip metadata and
     balance/deposit/withdrawal lines**, and deduce the session from each UTC open
     time. Echo the detected broker + column map + how many non-trade rows you
     skipped. **Privacy: keep the file local to this chat — never upload it or put
     trade rows in a tool argument; tools only get a symbol + a time.** Huge file
     → sample representatively across the full range, never the first N rows.
   - **Pasted trades** — a journal table or free-form list ("long BTC 62k → 64k
     +2R Tue London", "short ETH lost", etc.).
   - **A strategy description** — rules, no trades ("I buy the London open sweep
     of Asia and target the prior-day high").
   - **Any combination.**
   If you have no trades and only a description, skip the stats and review the
   **approach** instead (steps 4–6).

2. **Parse & normalize each trade** into: symbol, side (long/short), entry, exit,
   result (R-multiple or win/loss/breakeven, and PnL if given), and time if
   present. Normalize symbols (BTC/BTCUSD→`BTCUSDT`, ETH→`ETHUSDT`, SOL→`SOLUSDT`;
   EURUSD→`EUR_USD`, etc.). Infer win/loss from PnL, else from entry/exit + side.
   If a field is missing, leave it blank — never invent numbers. State your
   parsing assumptions back to the user.

3. **Compute summary stats** with your own arithmetic (see the skill): total
   trades, win rate, avg win / avg loss, avg R and **expectancy**, profit factor,
   max consecutive losses, and breakdowns **by symbol, by session, and by
   day-of-week**. Use `get_session_clock` (server `rektfree`, no args) for the
   RektFree session definitions (Asia 00–08, London 08–13, NY 13–21 UTC) and do
   the date/DOW math yourself from each trade's timestamp. Flag thin buckets
   (<~8 trades) as noisy.

4. **Cross-reference representative trades** (your best / worst / most-typical few,
   not all of them) against the live tools — **crypto symbols only**; pass only
   the symbol + the trade's time, never the journal:
   - `get_daily_bias` + `analyze_smc` (HTF for bias + entry TF for structure) and
     `get_levels` — was the entry with the daily bias and near an unmitigated OB /
     FVG / key level, or into thin air against it?
   - `get_session_clock` killzones — was the entry inside a killzone or in dead
     hours?
   - `scan_confluence` — did structure + level + profile + flow stack, or was it a
     lone signal?
   - `compute_session_stats` / `compute_smc_stats` — did the trade ride a real
     edge (e.g. the London-sweep / OB-retest tendency) or fight it?
   - `get_derivatives` / `get_volatility` for added context where useful.
   Flag each checked trade aligned vs misaligned with the RektFree read. The live
   tools work on crypto only. **If the user's trades are forex (`_` symbols), do
   the trade-stats + framework review but say live cross-referencing / the
   alignment-delta isn't available for forex in this plugin.** If a tool errors,
   note the gap and continue.

5. **Emit the two scorecards** (see the skill for the method):
   - **RULE COMPLIANCE** — for each rule the trader states or you infer
     (killzone-only, consistent-R, with-HTF-bias, level/OB entry…), show
     violation rate and **win-rate compliant vs violated** (+ net delta, with n).
   - **ALIGNMENT DELTA** (crypto) — win-rate + expectancy of trades **aligned**
     with the RektFree read (bias / levels / killzone / confluence from
     `get_daily_bias` / `get_levels` / `get_session_clock` / `scan_confluence`)
     vs misaligned. Forex → say it can't be computed and skip the delta.

6. **Run a GAP ANALYSIS** — what the strategy is missing vs the RektFree edge:
   session timing (trading dead hours, ignoring killzones), confluence (entries
   with no OB/level/HTF backing), HTF alignment (counter-trend without a CHoCH),
   risk management (no consistent R, oversized losers, revenge clusters), and
   statistical edge (trading symbols/sessions/days where their own data is
   negative). Tie each gap to a number from their data or a RektFree stat.

7. **Deliver** the skill's review format: TRADE SUMMARY (with source + column map)
   → STATS → CROSS-REFERENCE FINDINGS → RULE COMPLIANCE → ALIGNMENT DELTA → GAPS →
   IMPROVEMENT PLAN. If they described a testable edge (and `run_backtest` is
   available in this plugin), offer to backtest it; if that tool isn't present,
   say so and skip — don't fail.

Be direct and honest, not flattering — name what's costing them money with the
numbers. Caveat small samples (noisy), that you only see what they *reported*
(not their real chart/fills), and that there's no macro/news feed here.
