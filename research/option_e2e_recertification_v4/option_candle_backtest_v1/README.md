# Option Candle Backtest V1

Research-only historical option backtesting using real option OHLCV candles.

## Why this lane exists

Historical bid/ask archives are not generally available from free Indian broker APIs. Retail backtest platforms therefore simulate option trades from one-minute OHLCV/LTP bars and apply brokerage, statutory costs and slippage assumptions. This package implements that practical methodology without presenting candle fills as executable quote truth.

## Frozen flow

```text
completed strategy signal
→ bullish maps to long CE / bearish maps to long PE
→ nearest eligible expiry
→ nearest ATM strike from the signal-time underlying price
→ first option bar strictly after the signal
→ buy at next-bar open plus adverse slippage
→ stop/target evaluated from option OHLC
→ if stop and target both occur in one candle, stop wins
→ gap through stop fills at the worse opening price
→ favourable target gaps receive no price improvement
→ time exit at the last eligible candle close
→ sell with adverse slippage
→ subtract fixed and turnover costs
```

## Input contracts

### Signal ledger

Required columns:

- `signal_ts`
- `direction` (`BULLISH`, `BEARISH`, or `NEUTRAL`)
- `underlying`
- `underlying_price`

Recommended columns:

- `signal_id`
- `strategy_id`
- `selected_for_execution`
- `option_stop_price`
- `option_target_price`
- pre-outcome score, rank and regime fields

### Contract catalogue

Required columns:

- `contract_symbol`
- `underlying`
- `option_type`
- `strike`
- `expiry`

Strongly recommended:

- `session_date`

Without `session_date`, the selection is retained with `STATIC_CATALOG_LIMITATION` and cannot prove that the contract catalogue was historically available at the signal time.

### Option bars

Required columns:

- `contract_symbol`
- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

Duplicate `(contract_symbol, timestamp)` rows fail closed.

## Output meaning

The strongest result label is:

`CANDLE_PROXY_ECONOMICS_ONLY`

It supports historical strategy screening and comparison. It does not prove:

- historical ask-entry or bid-exit;
- market-depth availability;
- latency or broker fills;
- executable CE/PE profitability;
- paper or live readiness.

The next gate remains forward validation on captured bid/ask quotes.

## CLI

```bash
python scripts/run_option_candle_backtest.py \
  --signals /path/to/signals.parquet \
  --catalog /path/to/session_contract_catalog.parquet \
  --option-bars /path/to/option_1minute.parquet \
  --output-dir /tmp/option-candle-backtest-v1 \
  --require-session-catalog \
  --entry-slippage-bps 50 \
  --exit-slippage-bps 50 \
  --fixed-cost-per-order 20
```

Use multiple frozen slippage scenarios. Do not choose the slippage assumption after seeing which one makes the strategy profitable.
