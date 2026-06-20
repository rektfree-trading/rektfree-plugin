---
description: Review a trader's pasted trades or strategy against the RektFree framework — parse the trades, compute win-rate / R / expectancy and by-symbol / session / day-of-week breakdowns, cross-reference representative entries against live SMC / levels / sessions / stats, run a gap analysis vs the RektFree edge, and deliver a structured critique + concrete improvement plan.
argument-hint: [paste trades or describe your strategy]
---

Review the user's trading — either a list/CSV of their trades or a free-text
description of their strategy — against the RektFree framework, and return a
structured critique with a concrete improvement plan. **You are the analyst:**
you parse the pasted trades yourself and orchestrate the plugin's analysis tools
for objective market context. Use the **strategy** skill for the full playbook.

Input: `$ARGUMENTS`

Steps:

1. **Read what the user gave you.** It is one of:
   - **Trades** — a CSV, a pasted broker/journal table, or a free-form list
     ("long BTC 62k → 64k +2R Tue London", "short ETH lost", etc.).
   - **A strategy description** — rules, no trades ("I buy the London open sweep
     of Asia and target the prior-day high").
   - **Both.**
   If you have no trades and only a description, skip the stats and review the
   **approach** instead (steps 4–5).

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
   not all of them) against the live tools — **crypto symbols only**:
   - `analyze_smc` (HTF for bias + entry TF for structure) and `get_levels` — was
     the entry near an unmitigated OB / FVG / key level, or into thin air?
   - `get_session_clock` killzones — was the entry inside a killzone or in dead
     hours?
   - `compute_session_stats` / `compute_smc_stats` — did the trade ride a real
     edge (e.g. the London-sweep / OB-retest tendency) or fight it?
   - `get_derivatives` / `get_volatility` for added context where useful.
   The live tools work on crypto only. **If the user's trades are forex (`_`
   symbols), do the trade-stats + framework review but say live cross-referencing
   isn't available for forex in this plugin.** If a tool errors, note the gap and
   continue.

5. **Run a GAP ANALYSIS** — what the strategy is missing vs the RektFree edge:
   session timing (trading dead hours, ignoring killzones), confluence (entries
   with no OB/level/HTF backing), HTF alignment (counter-trend without a CHoCH),
   risk management (no consistent R, oversized losers, revenge clusters), and
   statistical edge (trading symbols/sessions/days where their own data is
   negative). Tie each gap to a number from their data or a RektFree stat.

6. **Deliver** the skill's review format: TRADE SUMMARY → STATS → CROSS-REFERENCE
   FINDINGS → GAPS → IMPROVEMENT PLAN. If they described a testable edge (and
   `run_backtest` is available in this plugin), offer to backtest it; if that tool
   isn't present, say so and skip — don't fail.

Be direct and honest, not flattering — name what's costing them money with the
numbers. Caveat small samples (noisy), that you only see what they *reported*
(not their real chart/fills), and that there's no macro/news feed here.
