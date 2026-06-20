# Strategy Review — Reference Playbook

The review playbook for grading a trader's own trades/strategy against the
RektFree framework. Adapted from the backend strategy analyzer (file parsing →
normalization → summary stats → cross-reference → gap analysis → report). Here
**you** do every step that the backend's AI + CSV parser did; the MCP tools only
supply objective market context.

---

## 0. Ingesting a broker export (CSV / XLSX) — detection & column mapping

If the user **attached a file or gave a path** (`.csv`, `.xlsx`, `.xls`), read it
yourself (you read attached files natively — there is **no parser MCP tool**, and
you must not add one). Then auto-detect the layout and map columns. Pasted/typed
trades still work without any of this — the file is an extra on-ramp.

**Privacy:** the export is the user's private trade ledger. Keep it inside this
conversation — never upload it, never put trade rows into a tool argument. The
only thing that leaves to the MCP tools is `(symbol, time)` for a handful of
representative trades.

### a. Skip the junk first

Real exports are messy. Before mapping, drop:
- **Title / metadata rows** above the real header (account name, broker, "Closed
  Transactions:", report date, currency, leverage).
- **Balance / non-trade ledger lines** — rows whose type is `balance`, `deposit`,
  `withdrawal`, `credit`, `transfer`, `commission`-only, `rollover`/`swap`-only,
  or that have no symbol + no entry/exit price. These inflate counts and have no
  side — exclude them and report how many you skipped.
- **Summary / totals footer** ("Total:", "Closed P/L:", "Balance:").

### b. Detect the broker / layout (fingerprints)

| layout | tells |
|--------|-------|
| **MT4 / MT5 statement** | header block then a "Closed Transactions" / "Positions" table; cols like `Ticket, Open Time, Type, Size/Volume, Item/Symbol, Price, S/L, T/P, Close Time, Price, Commission, Swap, Profit`; `Type` is `buy`/`sell`; HTML or tab/`;`-delimited; balance rows interleaved |
| **cTrader** | `Closing Time, Symbol, Direction, Volume, Entry price, Closing price, Net USD, Pips`; `Direction` = `Buy`/`Sell` |
| **TradingView** (Strategy Tester / paper) | `Symbol, Side, Type, Qty, Price, Date/Time, Net P&L`; or list-of-trades export with `Trade #, Entry/Exit, Signal` |
| **Binance** (spot/futures history) | `Date(UTC), Pair, Side, Price, Executed, Realized Profit, Fee`; `Side` = `BUY`/`SELL`; pair like `BTCUSDT` |
| **Bybit** | `Contracts, Order Time, Side, Order Price, Exec Value, Closed P&L`; `Side` = `Buy`/`Sell` |
| **OANDA** (history) | `Transaction ID, Time, Instrument, Units, Price, P/L, Balance`; instrument like `EUR/USD`; sign of `Units` gives side |
| **generic CSV** | none of the above — fall back to header-synonym matching (below) |

Don't over-trust the fingerprint — confirm with the actual headers, and if the
file doesn't match any, go straight to synonym matching.

### c. Header-name synonyms (map columns → record fields)

Match case-insensitively, ignore surrounding spaces/units. Pick the best column
per field; if two compete (e.g. an open price and a close price), use position
and labels (Open/Entry vs Close/Exit) to disambiguate.

| field | header synonyms |
|-------|-----------------|
| `open_time` | Open Time, Entry Time, Opening Time, Date(UTC), Order Time, Time, Opened, Date/Time |
| `close_time` | Close Time, Exit Time, Closing Time, Closed |
| `symbol` | Symbol, Item, Instrument, Pair, Contracts, Market, Ticker |
| `side` | Type, Side, Direction, B/S, Action, Order Type |
| `entry` | Open Price, Entry Price, Price (the open one), Avg Entry |
| `exit` | Close Price, Exit Price, Closing Price, Price (the close one) |
| `size` | Size, Volume, Qty, Quantity, Units, Lots, Executed, Amount, Contracts |
| `pnl` | Profit, PnL, P/L, Net P/L, Net P&L, Realized Profit, Closed P&L, Net USD, Gain |
| `stop` | S/L, SL, Stop, Stop Loss |

**Side decoding:** `buy/long/b/1/+/units>0 → long`; `sell/short/s/-1/0/−/units<0
→ short`. **P&L cleaning:** strip `$ € £`, thousands commas, parentheses-as-
negative `(12.34) → −12.34`; combine `Profit + Swap + Commission` into net if the
broker splits them. Then hand the cleaned rows to §1 normalization.

### d. Deduce the session from the open time

If `open_time` is present, derive the RektFree session yourself (in **UTC** —
convert first if the export is in broker/local time, and say which tz you assumed):
**Asia 00:00–08:00, London 08:00–13:00, NY 13:00–21:00, off-hours 21:00–24:00**
(confirm boundaries with `get_session_clock`). Killzones per §1. This powers the
by-session stats even when the broker didn't label a session.

### e. Big files

If the export is very large, keep all rows for the headline stats where feasible;
for the **cross-reference** step only ever sample (best / worst / most-typical and
a spread across symbols, sessions, dates). If you must sample for stats too,
sample across the **whole** date range and all symbols/sessions — never just the
first N rows — and state the sample size and method.

---

## 1. Parsing & normalization (you are the parser)

The user's input has no fixed schema. Map whatever they paste onto this record:

| field        | meaning                                  | how to read it |
|--------------|------------------------------------------|----------------|
| `symbol`     | instrument                               | normalize (below) |
| `side`       | long / short                             | buy/long/1/b → long; sell/short/-1/s/0 → short |
| `entry`      | entry / open price                       | strip `$ € £` and thousands commas |
| `exit`       | exit / close price                       | same |
| `result`     | R-multiple **or** win/loss/breakeven     | derive if not stated (below) |
| `pnl`        | currency P&L if given                    | optional |
| `open_time`  | when opened (for session / DOW)          | optional but valuable |

**Symbol normalization** (so cross-reference tools match):
`BTC, BTCUSD, BTC/USDT, XBTUSD → BTCUSDT` · `ETH… → ETHUSDT` · `SOL… → SOLUSDT` ·
`EURUSD/EUR/USD → EUR_USD` · `GBPUSD → GBP_USD` · `USDJPY → USD_JPY` ·
`XAUUSD/GOLD → XAU_USD`. Crypto has no separator; forex/metals use `_`.

**Outcome inference** (in priority order):
1. If `pnl` given → win if `pnl>0`, loss if `<0`, else breakeven.
2. Else if entry, exit and side given → long wins when `exit>entry`; short wins
   when `exit<entry`.
3. Else use whatever the user labelled (+2R, "won", "SL hit", etc.).

**R-multiple**: prefer what the user states. If they give entry, stop, and exit,
R = (exit−entry)/(entry−stop) for longs (sign-flip for shorts). If there's no
stop, you can't compute R — report PnL/percent instead and say R is unavailable.

**Timestamps → session / day-of-week** (do this yourself, in UTC):
- Session by open hour: **Asia 00:00–08:00, London 08:00–13:00, NY 13:00–21:00,
  off-hours 21:00–24:00** (confirm with `get_session_clock`).
- Killzones: **Asia 00–05, London Open 07–10, NY AM 12–15, NY PM 15–18** (UTC).
- Day-of-week from the date. Watch the user's stated timezone — if they give
  local times, convert to UTC before bucketing or the session split is wrong.

Skip nothing silently: if a row can't be parsed, say so. Never invent prices.

---

## 2. Summary stats (your arithmetic)

Compute over the parsed trades:

- **Win rate** = wins / total.
- **Avg win**, **avg loss** (mean PnL or R of winners / losers).
- **Profit factor** = gross profit / gross loss (abs).
- **Expectancy** = winrate·avg_win + (1−winrate)·avg_loss. The single most
  honest number — a 70% win rate with huge losers can still be negative.
- **Largest win / largest loss**, **max consecutive losses** (drawdown clusters
  reveal revenge trading / tilt).
- **Breakdowns** — for each of *by symbol*, *by session*, *by day-of-week* (and
  *by side*): count, win rate, net PnL/R. This is where the real edge or leak
  hides (e.g. "London longs 68%, NY shorts 31%").

Sample-size discipline: under ~20–30 total trades, treat conclusions as weak; any
single bucket under ~8 trades is anecdote, not signal. **Always state n.**

---

## 3. Cross-reference with live RektFree data (crypto only)

Pick **representative** trades (best, worst, most typical) — don't hammer the
tools for every row. For each, build context and judge alignment with the
framework. This mirrors the backend's per-trade context + alignment score.

What to fetch and what it answers:

| tool | question it answers |
|------|---------------------|
| `analyze_smc` (HTF + entry TF) | HTF bias direction; was there a BOS/CHoCH; unmitigated OB/FVG near the entry? |
| `get_levels` | was the entry at a D/W/M or session level, or in open space? |
| `get_session_clock` | was the entry inside a killzone, or in dead hours? |
| `compute_session_stats` | does the trade ride a real tendency (London sweeps Asia, NY continuation, DOW edge)? |
| `compute_smc_stats` | OB retest/hold rate, FVG fill, BOS continuation — did the entry type have a historical edge? |
| `get_derivatives` | crowded positioning / funding around the entry (squeeze context) |
| `get_volatility` | was the regime expansion or chop (affects whether targets were realistic)? |

**Alignment scoring (0–5)** — adapted from the backend `_compute_alignment`. Add
a point for each that holds:
1. **HTF bias aligned** — trade direction matches `analyze_smc` HTF `trend_bias`.
2. **Level / OB entry** — entry near an unmitigated OB/FVG or a key level.
3. **Killzone timing** — opened inside a killzone, not dead hours.
4. **Stat-backed** — entry type / session has a positive `compute_*_stats` edge.
5. **Confluence** — `scan_confluence`-style stacking, or premium/discount agrees
   with the side.

Then, if the sample allows, compare **aligned (score ≥3) vs misaligned (≤1)**
win rates. The classic, useful finding: "your framework-aligned trades win 64%;
your impulsive off-framework ones win 29% and are dragging expectancy negative."

**Forex caveat:** the live tools are crypto-only (forex `_` symbols error). For
forex trades, do the stats + the framework gap review, and explicitly say live
cross-referencing isn't available — don't call the tools and don't guess.

---

## 3a. The two scorecards (per-rule compliance + alignment delta)

The old web product surfaced two tables on top of the stats. Reproduce both.

### Per-rule compliance

Collect the **rules** to score:
1. Rules the trader **states** ("I only trade London/NY killzones", "always risk
   1R", "only with the daily bias", "no trades after 21:00 UTC", "minimum 2R
   target").
2. If they state none, **infer** 2–4 from their obvious pattern / from the
   RektFree framework (killzone-only, consistent-R, HTF-aligned, level/OB entry).

For each rule, classify every trade as **compliant** or **violation**:
- Rules judged purely from the parsed data (time-of-day, R consistency, target,
  size) → classify **all** trades, free.
- Rules needing market context (with-bias, at-a-level, in-a-killzone) → judge from
  the step-3 cross-reference on a **representative sample** and label it a sample
  (extrapolate, don't pretend you checked every row).

Then per rule report: **violations (k/n)**, **violation rate**, **win-rate when
compliant vs when violated**, and the **net/expectancy delta**. The money line is
usually a rule where violated-WR ≪ compliant-WR — that's a leak with a fix.

| rule | violations | viol-rate | WR compliant | WR violated | net delta |
|------|-----------|-----------|--------------|-------------|-----------|
| only in killzones | 7/30 | 23% | 61% (n=23) | 29% (n=7) | −0.6R |

State n on both sides; if either side is under ~8 trades, flag it as anecdotal.

### Alignment delta (crypto only)

This is the "did trades that agreed with the platform read win more" table. From
the cross-referenced trades, mark each **aligned** vs **misaligned** with the
RektFree read, then compare win-rate + expectancy. Use the 0–5 alignment score
from §3 (aligned = score ≥3, misaligned = ≤1) so it's reproducible. The four
pillars and the tool that decides each:

- **Bias** — side matches `get_daily_bias` (and `analyze_smc` HTF `trend_bias`).
- **Levels** — entry at an unmitigated OB/FVG or a key level from `get_levels`.
- **Killzone** — opened in a killzone per `get_session_clock`, not dead hours.
- **Confluence** — `scan_confluence` shows structure+level+profile+flow stacking
  for the side, not a lone signal.

| group | n | win rate | expectancy |
|-------|---|----------|------------|
| aligned (score ≥3)    | 18 | 64% | +0.5R |
| misaligned (score ≤1) | 12 | 29% | −0.4R |

The classic finding: framework-aligned trades carry the account; impulsive
off-framework ones drag expectancy negative. **Forex:** the live tools are
crypto-only, so the alignment delta can't be computed — say so and skip this
table (the compliance table still works for data-judged rules).

---

## 4. What a good RektFree-aligned trade looks like

Use this as the yardstick for the gap analysis:

- **Confluence, not a single signal** — entry where structure + a level/OB +
  profile (POC/VAH/VAL) + (crypto) order flow agree. One OB alone isn't a trade.
- **HTF alignment** — direction set by the higher timeframe; lower timeframe only
  times the entry. Counter-trend only after a clean LTF CHoCH at an HTF level.
- **Level / OB entries** — entries at unmitigated OBs/FVGs or D/W/M & session
  levels, in the correct premium/discount half of the swing range.
- **Killzone timing** — entries clustered in London Open / NY AM / NY PM killzones
  and aligned with the session's real tendency (sweep → reverse, or continuation).
- **Risk management** — consistent R per trade, losers near 1R (not blown out),
  no revenge clusters after a loss, position size steady.
- **Stat edge** — trading the symbols / sessions / days where their *own* data
  and RektFree's stats are positive; avoiding the negative buckets.

---

## 5. Gap analysis (vs the framework)

Score the strategy against each axis and tie every gap to a number:

- **Session timing** — trading dead hours (off-hours/Asia chop), ignoring
  killzones, or fighting the session's tendency.
- **Confluence** — entries with no OB/level/HTF backing ("into open space").
- **HTF alignment** — counter-trend entries without a CHoCH trigger.
- **Risk management** — no consistent R, oversized losers, averaging down,
  consecutive-loss revenge clusters, win rate good but expectancy negative.
- **Statistical edge** — concentrated losses in a symbol/session/day their own
  data shows is negative; cutting winners early / holding losers (duration skew:
  if avg-loss duration ≫ avg-win duration, they're hoping on losers).

Then write the **improvement plan**: 3–5 specific, measurable changes, each with
the projected impact computed from *their* data (e.g. "drop the 21:00–24:00
bucket — it's 22% over 18 trades and turns expectancy from −0.1R to +0.3R").

---

## 6. Backtest (optional)

If the user states a testable, rule-based edge **and** `run_backtest` exists in
this plugin (a sibling tool may add it), offer to backtest the cleaned rule and
fold the result into the plan. If the tool isn't present at runtime, say so and
skip — never fail the review over a missing optional tool.

---

## 7. Honest caveats (always include the relevant ones)

- **Small samples are noisy.** Under ~20–30 trades nothing is conclusive; a bucket
  under ~8 is anecdote. State n everywhere.
- **You only see what they reported** — not their actual chart, fills, slippage,
  spread, or psychology. The review is only as good as the pasted data.
- **No macro/news context.** This plugin has no economic-calendar feed, so a loss
  may have been a news spike you can't see. Caveat accordingly.
- **Crypto-only live data.** Cross-referencing is crypto-only; forex gets the
  stats + framework review with that limitation flagged.
- **Past performance ≠ future.** A positive bucket in a small window can be luck;
  recommend confirming an edge forward (or via `run_backtest`) before sizing up.
