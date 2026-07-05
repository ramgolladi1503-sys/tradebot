# Next-Day Option Tick Capture Contract

This contract defines the strict requirements for capturing a clean dataset suitable for certification strategy replay on the next market day.

## Purpose

The current token-filtered option tick dataset is `BLOCKED_FOR_CERTIFICATION` because it lacks a date-aligned instrument master and contains high levels of spread outliers. To proceed with certification strategy replay, a fresh, verifiably clean dataset must be captured.

## Required Artifacts

All captures must be stored under `runtime/live_capture/<YYYYMMDD>/`. The following artifacts are required for a valid capture:

1. **Instrument Master**: `runtime/live_capture/<YYYYMMDD>/instrument_master/kite_instruments_<YYYYMMDD>.json`
2. **Option Ticks**: `runtime/live_capture/<YYYYMMDD>/ticks/option_ticks_<YYYYMMDD>.parquet`
3. **Capture Manifest**: `runtime/live_capture/<YYYYMMDD>/manifests/capture_manifest_<YYYYMMDD>.json`
4. **Quality Report**: `runtime/live_capture/<YYYYMMDD>/quality/capture_quality_report_<YYYYMMDD>.json`

## Requirements

### Synchronization
The instrument master and the option tick data must be captured on the **exact same market day**. The date of the instrument master must exactly match the trading date of the tick data. 

### Data Completeness
- **Instrument Master** must contain: `instrument_token`, `tradingsymbol`, `name`, `expiry`, `strike`, `instrument_type`, `segment`, `exchange`, and `lot_size`.
- **Option Ticks** must contain: `local_ts`, `instrument_token`, `last_price`, `best_bid`, `best_ask`, and `depth_json`.

### Quality Gates
- **Lineage Verification**: The dataset must pass full lineage verification.
- **Spread Outliers**: The spread-to-LTP outlier rate must fall below the maximum acceptable threshold.
- **Unresolved Tokens**: Any ticks with tokens that cannot be resolved using the same-day instrument master must be excluded.

## Safety
- `paper_live_allowed`: false
- `live_allowed`: false
- `broker_order_allowed`: false
- `execution_allowed`: false

Only after this contract is fulfilled (`NEXT_DAY_CAPTURE_CONTRACT_VALID`), can a single strategy replay proceed.
