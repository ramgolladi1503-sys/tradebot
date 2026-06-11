# Data Vendor Checklist

## Objective

Collect operator-verified local historical data without assuming broker support for expired option history.

## Checklist

1. Confirm whether the source contains expired option intraday contracts, not only current contracts.
2. Confirm whether `expiry`, `strike`, and `option_type` are explicit columns.
3. Confirm whether bid/ask is available or only OHLC.
4. Confirm whether `volume` and `oi` are included.
5. Confirm symbol coverage for `NIFTY`, `BANKNIFTY`, and `SENSEX`.
6. Confirm date coverage spans approximately eight years.
7. Confirm timezone and timestamp resolution.
8. Confirm whether data is contract-level, chain-level, EOD-only, or intraday.
9. Confirm whether local redistribution and storage are allowed under the vendor license.

## Known constraints

- Zerodha/Kite does not provide expired historical options contracts for this purpose.
- NSE derivative archives are useful for EOD and contract validation, but usually not enough for full intraday options scalping proof.

## Ready states

- `READY_FOR_TRUE_INTRADAY_OPTIONS_BACKTEST`
- `READY_FOR_EOD_OR_PROXY_ONLY`
- `NEED_USER_HISTORICAL_DATA`
- `BLOCKED_BY_SCHEMA`
