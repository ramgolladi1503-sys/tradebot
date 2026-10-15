# Baseline Manifest: Protected PRs and Paper-Shadow Sessions

## 1. Protected PR SHAs & Branch Identities
- **PR #968 (NIFTY Sentinel Sidecar)**:
  - Branch: `feat/sentinel-decoupled-sidecar-live-advisor`
  - Protected Head SHA: `e6d0ae46643ba21767e13e0c40fa8389e51d1acb`
  - Invariants: `read_only = True`, `is_order_action = False`, `broker_api_called = False`
  - Runtime Artifact Sink: `runtime/audit/sentinel_execution_paths_YYYYMMDD.parquet`
  - APM State WAL: `runtime/sentinel_apm_wal.json`
- **PR #980 (SENSEX Asset Profile Engine)**:
  - Branch: `feat/sentinel-sensex-asset-profile-engine`
  - Protected Head SHA: `c87688055c3df2d77a4220eb1c0c4d763db9c5c2`
  - Invariants: `read_only = True`, `is_order_action = False`, `broker_api_called = False`
  - Runtime Artifact Sink: `runtime/audit/sentinel_execution_paths_sensex_YYYYMMDD.parquet`
  - APM State WAL: `runtime/sentinel_apm_wal_sensex.json`

## 2. Seven-Session Data & Artifact Inventory
| Date | Asset | Raw Capture Status | Sentinel Telemetry Bars | APM WAL Executed Trades | Cryptographic Evidence Hash |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **2026-10-07** | NIFTY | 1,369,276 ticks (130 symbols) | Offline Reference | Pre-Sentinel Baseline | `upstox_full_ticks_20261007_stitched.parquet` |
| **2026-10-08** | NIFTY | 3,916,790 ticks (136 symbols) | 129 bars (13:21–15:29) | 0 trades (Standby) | `sentinel_execution_paths_20261008.jsonl` |
| **2026-10-09** | NIFTY | 3,822,717 ticks (132 symbols) | 89 bars (09:45–11:14) | 4 trades (Prototype) | `sentinel_execution_paths_20261009.jsonl` |
| **2026-10-12** | NIFTY | 3,918,465 ticks (130 symbols) | Feed Stitched | Feed Validation Only | `upstox_full_ticks_20261012_stitched.parquet` |
| **2026-10-13** | NIFTY | 3,856,935 ticks (134 symbols) | 342 bars (09:45–15:29) | 6 trades (+18.95 spot, +19.45 prem) | `sentinel_execution_paths_20261013.parquet` |
| **2026-10-14** | NIFTY | 4,032,995 ticks (130 symbols) | 337 bars (09:33–15:29) | 9 trades (-89.45 spot, -62.85 prem) | `sentinel_execution_paths_20261014.parquet` |
| **2026-10-15** | NIFTY | 1,075,132 ticks (129 symbols) | 375 bars (09:15–15:29) | 5 trades (+81.60 spot, +30.75 prem) | `sentinel_execution_paths_20261015.parquet` (`16aab03f...`) |
| **2026-10-15** | SENSEX | 1,075,132 ticks (129 symbols) | 329 bars (10:01–15:29) | 6 trades (+188.11 spot, +70.95 prem) | `sentinel_execution_paths_sensex_20261015.parquet` (`ef528936...`) |

## 3. Clock, Timing & Causality Semantics
- **Bar Close Cutoff Epoch**: Exact completed bar close timestamp (e.g. 09:45:00.000).
- **Quote Selection Window**: Strictly $\le$ bar close cutoff. No intrabar lookahead.
- **Execution Fill Assumption**:
  - Baseline APM: Recorded at observed bar close quote (or next bar open).
  - Challenger Fill Model: Required evaluation at attainable Bid (exits) and Ask (entries) with statutory friction.
