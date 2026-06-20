---
name: possize
description: >-
  Risk-based position sizing & reward:risk for a single trade. Use whenever the
  user asks how big their position should be, how to size a trade, how many
  units / lots / contracts to buy, what their risk per trade is or "what's my
  risk", how much they'd lose if stopped, the R:R or reward-to-risk of a setup,
  the breakeven win-rate, or where to put a stop from an ATR multiple (e.g.
  "1.5×ATR stop"). Triggers on "$10k account, 1% risk, entry X stop Y target Z"
  style requests for crypto or USD-quoted forex/metals/indices. Pairs with the
  `calc_position_size` MCP tool, which does the arithmetic and returns the
  structured payload.
---

# Position Sizing & Risk

You are the analyst. The `calc_position_size` MCP tool (server `rektfree`) does
the arithmetic — given account equity, the percent to risk, an entry, and a stop
(explicit or ATR-derived), it returns the exact unit count whose loss-at-stop
equals the intended dollar risk, plus R:R and breakeven win-rate when a target is
given. Your job is to **interpret** that into an order a trader can place. Never
just echo the JSON.

## Workflow

1. **Parse.** Pull from the request: `account_equity`, `risk_pct` (default
   `1.0` = 1%), `entry`, `stop`, optional `target`, optional `side`, optional
   `leverage`. Users give these in plain English ("$10k account, 1% risk, long
   BTC entry 63000 stop 61500 target 67000").
2. **Derive a stop from ATR when none is given.** If there's no stop price but
   the user gives a symbol and an ATR multiple ("size a long here with a 1.5×ATR
   stop"), pass `symbol` + `stop_atr_mult` (and `timeframe`/`atr_period` if
   named). The tool fetches candles, computes ATR, and places the stop at
   `entry ∓ mult×ATR` against the trade.
3. **Call** `calc_position_size` with the parsed values.
4. **Interpret.** Read the payload against the guardrails below and produce the
   output shape. Lead with the size and the dollar risk.
5. **Errors.** If the payload has an `error` (bad equity/risk/entry, stop on the
   wrong side of entry, not enough candles for ATR), say what's wrong and how to
   fix it — don't invent a number.

## Payload key

`calc_position_size` returns (target/leverage/atr fields appear only when
relevant):

- `side` — `long` / `short`, resolved from explicit side, else stop-vs-entry,
  else target-vs-entry.
- `account_equity`, `risk_pct`, `risk_amount` — `risk_amount = equity ×
  risk_pct/100`. This is **1R**, the dollar you lose at the stop.
- `entry`, `stop`, `stop_distance`, `stop_distance_pct` — `stop_distance =
  |entry − stop|`; the pct is of entry.
- `position_size_units` — **the answer**: `risk_amount / stop_distance`. Crypto
  → base-asset units (BTC); forex → OANDA base-currency units (10000 ≈ 0.1 lot).
- `notional_value` — `units × entry`, position value in the quote currency.
- `leverage`, `required_margin` — present only if leverage given;
  `required_margin = notional / leverage`.
- `target`, `target_distance`, `target_distance_pct`, `reward_amount`,
  `rr_ratio` — `rr_ratio = target_distance / stop_distance`; `reward_amount =
  units × target_distance`.
- `r_multiples` — `{risk_1R, reward_R, note}`; the `note` carries the breakeven
  win-rate ≈ `100 / (1 + rr_ratio)` % before fees.
- `target_warning` — present if the target sits on the losing side of entry.
- `stop_source` — `explicit` or `atr_derived`.
- `atr` — present when ATR-derived: `{value, period, timeframe, multiple,
  method, derived_side, last_price}`.
- `notes` — the honest caveats; surface the relevant ones.

## Output shape

```
POSITION SIZE
- Size: [position_size_units] units (~$[notional_value] notional), [side]
- Risk: $[risk_amount] = [risk_pct]% of $[account_equity]  (this is 1R)
- Stop: [stop] — [stop_distance] away ([stop_distance_pct]%) [explicit / ATR-derived]
- [if leverage] Margin at [leverage]x: $[required_margin]

REWARD  (only if target given)
- Target: [target] — [target_distance] away ([target_distance_pct]%)
- R:R = [rr_ratio]:1 → +$[reward_amount] at target for $[risk_amount] risked
- Breakeven win-rate ≈ [100/(1+rr)]% before fees

READ
- [Is the R:R worth it? Is the stop sane vs ATR? One clear call.]

CAVEATS
- [the load-bearing notes — see below]
```

## Interpretation guardrails

- **The size is exact only when the quote currency = the account currency.** It
  holds cleanly for **USDT-quoted crypto** (BTCUSDT) and all **`*_USD`**
  forex/metals/indices (EUR_USD, XAU_USD, NAS100_USD) for a USD account. For
  **cross / non-USD-quoted pairs** (USD_JPY, EUR_GBP) the per-unit risk is in the
  **quote** currency — the trader must convert to their account currency before
  trusting the unit count. Always flag this when the symbol isn't USD-quoted.
- **Units differ by market.** Crypto units = base asset (e.g. BTC); notional is
  in quote. Forex units = OANDA base-currency units — **10000 units ≈ 0.1
  standard lot**, 100000 ≈ 1 lot. Translate to lots when the user thinks in lots.
- **Leverage moves margin, not dollar-risk.** `required_margin = notional /
  leverage`. Your loss at the stop is still `risk_amount` regardless of leverage;
  leverage only changes the margin posted and liquidation distance. Don't let a
  trader conflate "I can size bigger with leverage" with "I'm risking the same."
- **R:R and breakeven win-rate are the quality gate.** A ~1:1 R:R needs >50% wins
  to profit; 2:1 only needs ~33%, 3:1 ~25%. Call out a setup whose R:R is too
  thin for a realistic win-rate. If `target_warning` is set, the target is on the
  wrong side — say so and don't present a real R:R.
- **No fees, slippage, funding, or spread are modeled.** Real loss at the stop
  will be slightly worse than `risk_amount`; real R:R slightly worse than shown.
  State this once.
- **Sanity-check the ATR-derived stop.** When `stop_source` is `atr_derived`,
  cite the ATR value/multiple/timeframe so the trader sees where the stop came
  from; a 0.5× stop is tight (noise-prone), 1.5×+ is wide/swing.

See [reference.md](reference.md) for a fully worked example.
