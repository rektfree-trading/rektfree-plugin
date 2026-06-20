# Position Sizing — Worked Examples

## 1. Crypto, explicit stop + target (the clean case)

Request: *"$10k account, risk 1%, long BTC entry 63000, stop 61500, target
67000."*

Call: `calc_position_size(account_equity=10000, risk_pct=1, entry=63000,
stop=61500, target=67000)`.

The math:
- `risk_amount` = 10000 × 1% = **$100** (this is 1R).
- `stop_distance` = |63000 − 61500| = **1500** (2.38% of entry).
- `position_size_units` = 100 / 1500 = **0.0667 BTC** (the answer).
- `notional_value` = 0.0667 × 63000 = **~$4200**.
- `target_distance` = 67000 − 63000 = 4000.
- `rr_ratio` = 4000 / 1500 = **2.67:1**.
- `reward_amount` = 0.0667 × 4000 = **~$267**.
- Breakeven win-rate ≈ 100 / (1 + 2.67) = **~27%**.

Read: hold **0.0667 BTC** (~$4.2k notional). Risk $100 to make ~$267 — a 2.67:1
setup that only needs to win ~27% of the time to break even. The size is exact
because BTC is USDT-quoted and the account is in USD. No fees modeled, so the
real loss is a touch over $100.

## 2. Forex, USD-quoted, thinking in lots

Request: *"$25k, 0.5% risk, short EUR_USD entry 1.0850 stop 1.0890."*

- `risk_amount` = 25000 × 0.5% = **$125**.
- `stop_distance` = |1.0850 − 1.0890| = **0.0040** (40 pips).
- `position_size_units` = 125 / 0.0040 = **31250 OANDA units** ≈ **0.31 standard
  lots** (10000 units ≈ 0.1 lot).
- EUR_USD is `*_USD`, so for a USD account the per-unit risk is already in USD —
  the size is exact.

## 3. ATR-derived stop (no stop price given)

Request: *"Size a long on ETH here, 2% risk on $5k, 1.5×ATR stop, 3R target,
entry 3400."*

Call: `calc_position_size(account_equity=5000, risk_pct=2, entry=3400,
symbol="ETHUSDT", stop_atr_mult=1.5, timeframe="1h")`. The tool fetches candles,
computes ATR(14, 1h), places the stop at `entry − 1.5×ATR` (long), and returns an
`atr` block + `stop_source: "atr_derived"`. Cite the ATR value and the resulting
stop so the trader sees the derivation. (A 3R target isn't a price the tool
infers — if the user means "target = 3× the stop distance," compute that target
price yourself and pass it as `target`.)

## 4. The non-USD-quoted trap

Request: *"$10k, 1% risk, long USD_JPY entry 150.00 stop 149.50."*

- `risk_amount` = $100; `stop_distance` = 0.50; `position_size_units` =
  100 / 0.50 = **200 units** — but this 200 is in **JPY terms**, because the
  per-unit risk is in the **quote currency (JPY)**, not USD.
- **Do not hand the trader "200 units" as if it caps their USD loss at $100.**
  Tell them: the size assumes the quote currency is the account currency; for
  USD_JPY they must convert the per-unit risk from JPY to USD (divide by the
  USD/JPY rate) before trusting the count. This is the single most important
  caveat for non-`*_USD` pairs.

## Quick reference

- 1R = `risk_amount` = equity × risk%. Everything is measured in R.
- `position_size_units = risk_amount / stop_distance`.
- Breakeven win-rate ≈ `100 / (1 + R:R)` % (before fees).
- Crypto units = base asset. Forex units = OANDA base-currency units (10000 ≈
  0.1 lot, 100000 ≈ 1 lot).
- Leverage → `required_margin = notional / leverage`; dollar-risk unchanged.
- Exact only for USDT crypto and `*_USD` pairs on a USD account.
