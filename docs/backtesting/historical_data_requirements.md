# Historical Data Requirements

## Required operator outcome

Before Phase 2, the operator must be able to point Tradebot at real local historical datasets and answer:

- which symbols are covered
- which dates are covered
- whether expired option intraday history actually exists
- whether only EOD, proxy, or runtime replay modes are supportable

## Canonical data sources

### Index candles

Required columns:

`timestamp,symbol,open,high,low,close,volume`

Purpose:

- minimum requirement for underlying-only or proxy studies

### Futures candles

Required columns:

`timestamp,symbol,expiry,open,high,low,close,volume,oi`

Purpose:

- alternative or supplemental underlying signal source

### Options intraday candles

Hard-required columns:

`timestamp,underlying,expiry,strike,option_type,open,high,low,close`

Recommended columns:

`volume,oi,bid,ask`

Rules:

- missing `expiry`, `strike`, or `option_type` blocks validity
- missing `bid` or `ask` reduces readiness score and fill realism
- missing `volume` or `oi` creates warnings and lowers research confidence

### Options EOD

Hard-required columns:

`date,underlying,expiry,strike,option_type,open,high,low,close`

Recommended columns:

`volume,oi,settlement`

### Option chain snapshots

Hard-required columns:

`timestamp,underlying,expiry,strike`

Recommended columns:

`ce_ltp,ce_bid,ce_ask,ce_volume,ce_oi,pe_ltp,pe_bid,pe_ask,pe_volume,pe_oi`

## Eight-year completeness expectations

To unlock `TRUE_OPTIONS_INTRADAY`, the operator should provide:

- approximately eight years of underlying or futures coverage
- approximately eight years of expired option intraday coverage for the target underlyings
- enough strikes and expiries to evaluate real historical setups

If true intraday options are missing, the system must remain fail-closed and report `INCONCLUSIVE_FOR_REAL_INTRADAY_OPTIONS` or `NEED_USER_HISTORICAL_DATA`.

## Readiness verdict interpretation

- `READY_FOR_TRUE_INTRADAY_OPTIONS_BACKTEST`: real intraday options plus required underlying support are feasible
- `READY_FOR_EOD_OR_PROXY_ONLY`: either `OPTIONS_EOD` or `UNDERLYING_SIGNAL_WITH_OPTION_PROXY` is feasible
- `READY_FOR_RUNTIME_REPLAY_ONLY`: only `LIVE_CAPTURE_REPLAY` is feasible
- `BLOCKED_BY_SCHEMA`: sources exist, but required fields are missing or invalid
- `NEED_USER_HISTORICAL_DATA`: no qualifying sources are available

## Folder layout

- `data/historical/index/`
- `data/historical/futures/`
- `data/historical/options_intraday/`
- `data/historical/options_eod/`
- `data/historical/option_chain/`
- `data/historical/nse_reports/`

## Validation commands

```bash
python scripts/backtest_data_diagnostics.py --config configs/backtest_8y.example.json
python scripts/import_historical_data.py --config configs/backtest_8y.example.json --dry-run
```
