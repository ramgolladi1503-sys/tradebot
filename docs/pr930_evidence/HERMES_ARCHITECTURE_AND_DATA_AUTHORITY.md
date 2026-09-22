# Hermes Architecture and Data Authority Spec: PR 930 T-1 Facts & Provenance

## Stage 1: Strategy Consumer Semantics

### 1. INTRADAY_OPENING_DRIVE_V1
- **Instrument**: Authoritative NIFTY Near-Month Futures Contract (e.g. `NIFTY26SEPFUT`, token `17512194`, exchange `NFO`).
- **T-1 Fact**: `opening_drive_prev_close_1529`.
- **Bar/Tick Convention**: Exact regular-session bar timestamped at `15:29:00` (or cutoff `<= 15:29:59.999`).
- **Fail-Closed Rule**: The frozen candidate spec in `docs/research/candidates/INTRADAY_OPENING_DRIVE_V1/FROZEN_SPEC.json` strictly requires authoritative futures contract continuity (`prev_contract_key == curr_contract_key`). It fails closed if the futures contract or 15:29 bar is missing, NaN, null, or a generic placeholder. Under no circumstances may spot LTP be substituted for futures close.
- **2026-09-22 Live Session Status**: The 2026-09-22 live observer was subscribed only to NIFTY spot (Token 256265); Token 17512194 (`NIFTY26SEPFUT`) was not subscribed. Thus, live session recordings contain 0 futures bars.
- **Authoritative Status**: `T1_PREV_CLOSE_STATUS=BLOCKED_SOURCE_AUTHORITY`. In accordance with frozen governance, the generator must not synthesize or fabricate a futures closing price. The strategy shadow adapter gracefully disables `INTRADAY_OPENING_DRIVE_V1` fail-closed with `DISABLED_FAIL_CLOSED: MISSING_T_MINUS_1_FUTURES_PREREQUISITES`.

### 2. S1_MOMENTUM_OVERNIGHT_V1 & S4_MONDAY_OVERNIGHT_V1
- **Instrument**: NIFTY 50 Spot Index (Token 256265, exchange `NSE`).
- **T-1 Fact 1**: `overnight_prev_daily_close`. Authoritative daily close of NIFTY spot on T-1 (2026-09-22: `23329.0`). Available in certified `market_snapshot.json` (SHA-256: `f2feb19fd45aeb5af1fe3aeeac00e2045a13ad9f165e24547ace64abcaec3706`).
- **T-1 Fact 2**: `overnight_prev_sma200`. Simple Moving Average of the last 200 trading day closes of NIFTY spot up to and including T-1 (or up to T-1).
- **Authoritative Daily Series Status**: All existing local repositories and worktrees contain NIFTY historical spot data only up to 2026-07-28 (`NIFTY_SPOT_FUTURES_ALIGNED_V2_repaired.parquet`) or 2026-03-13 (`nifty50.csv`). The intervening daily session closes between 2026-07-29 and 2026-09-21 are not persisted in local offline warehouses.
- **Fail-Closed Rule**: A hardcoded default (`22450.0`) violates frozen research and cryptographic provenance. An SMA-200 cannot be fabricated or imputed without continuous daily bars covering the 200 sessions.
- **Authoritative Status**: `SMA200_STATUS=BLOCKED_SOURCE_AUTHORITY`. In accordance with frozen governance, the generator must not emit a hardcoded default. The strategy shadow adapter gracefully disables `S1_MOMENTUM_OVERNIGHT_V1` and `S4_MONDAY_OVERNIGHT_V1` fail-closed with `DISABLED_FAIL_CLOSED: MISSING_T_MINUS_1_OVERNIGHT_PREREQUISITES`.

## Stage 2: Dual-Mode Generator Architecture
The generator `scripts/generate_t1_prerequisites.py` is refactored to enforce strict provenance:
1. When full authoritative historical series (`--historical-daily-dataset`) and intraday futures (`--futures-dataset`) are supplied:
   - Verifies dataset existence and computes dataset SHA-256.
   - Computes SMA-200 across exactly 200 valid consecutive trading sessions.
   - Extracts exact 15:29 futures bar close for the contract key.
   - Emits full lineage: observation count, window start/end dates, source hashes, and payload SHA.
2. When source authority is absent:
   - Strictly refuses to inject default fallback constants (`sma200_value=22450.0`).
   - Fails closed or emits explicit blocked status markers (`T1_PREV_CLOSE_STATUS=BLOCKED_SOURCE_AUTHORITY`, `SMA200_STATUS=BLOCKED_SOURCE_AUTHORITY`), allowing downstream adapters to disable uncertified strategies fail-closed without crashing the observer runtime.
