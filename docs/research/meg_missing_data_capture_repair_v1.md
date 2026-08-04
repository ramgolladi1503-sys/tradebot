# Upstox MEG Multi-Asset Capture Offline Contract Repair V1

This document summarizes the offline contract repairs implemented on branch `data/meg-missing-futures-options-capture-v1`.

---

## 1. Summary of Repaired Bounded Defects

1. **Dynamic Session Identity**:
   - Removed hardcoded defaults (`session_date=20260804`, `spot_price=24500`).
   - Implemented strict precedence: Explicit CLI args (`--session-date`, `--nifty-spot`) -> Approved premarket quote source (`fetch_approved_nifty_spot()`) -> Fail closed.
   - Premarket preparation generates `premarket_manifest.json` containing SHA-256 hashes of the instrument master and universe plan.

2. **Weekly/Monthly Expiry Resolution**:
   - Switched from weak `(expiry + 7d).month != expiry.month` heuristic to using master `weekly` boolean attribute and deterministic calendar Thursday rules.
   - Nearest weekly expiry = earliest future expiry with `weekly=True`.
   - Nearest monthly expiry = earliest future expiry with `weekly=False` (ensuring distinct expiries to prevent collapse).
   - Validated: CE/PE symmetry (21 weekly, 11 monthly), ATM strike presence, distinct expiries.

3. **Restricted Validation Universe**:
   - Restricted universe to 126 critical instruments: NIFTY 50 spot, India VIX, 50 NIFTY constituents, 8 Sector Indices, 2 NIFTY futures, 42 weekly options, 22 monthly options.
   - Excluded BANKNIFTY futures/options, SENSEX options, and broad F&O LTPC equity universe. All exclusions logged to `exclusions.csv`.

4. **Strict Subscription Budget**:
   - Implemented fail-closed budget object: `full_limit=2000`, `ltpc_limit=5000`.
   - Exceeding limit produces `FAIL_SUBSCRIPTION_BUDGET <reason>` and exits with error code.
   - Verification verdict: `PASS_SUBSCRIPTION_BUDGET`.

5. **Multi-Lane Subscriptions & Lifecycle Logging**:
   - Subscribes both FULL and LTPC lanes on WebSocket connect.
   - Logs lifecycle events (`CONNECT`, `SUBSCRIBE_SENT`, `FIRST_EVENT_OBSERVED`, `NEVER_OBSERVED`) to `subscription_events.jsonl`.
   - Shutdown reconciliation checks that all mandatory instruments were observed.

6. **Normalization & Null Preservation**:
   - Mapped all canonical Upstox V3 fields: `option_type`, `close_price`, `open`, `high`, `low`, `volume`, `average_traded_price`, `open_interest`, `previous_open_interest`, `total_buy_quantity`, `total_sell_quantity`, Greeks (`delta`, `gamma`, `theta`, `vega`, `rho`), `market_status`.
   - Removed `fillna(0)` integer conversions to preserve true missing `null` values using pandas `Int64`.

7. **Immutable Parquet Chunks & Durability**:
   - `NormalizedWriter` writes immutable chunks (`ticks_<run_id>_<sequence>.parquet`) using temporary files, fsync, and atomic `os.replace`.
   - Appends manifest records to `normalized_chunk_manifest.jsonl`.
   - Performs shutdown reconciliation ensuring `accepted_rows == durable_rows + pending_rows`.

8. **Production Mock Fallback Removed**:
   - `generate_offline_datasets.py` fails closed with exit code 1 and error messages `NO_REAL_NORMALIZED_DATA` / `OFFLINE_DATASET_GENERATION_SKIPPED` when real tick data is missing.

9. **Precursor and Response Datasets**:
   - Generates 1-minute interval precursor tables, futures outcomes (+5s, +15s, +30s, +60s horizons), option outcomes, and join maps.
   - Included future-data leakage test asserting zero outcome columns in precursors.

10. **Official Weights Reference Handling**:
    - Accepts `--weights-file`. If unavailable, emits `OFFICIAL_WEIGHT_REFERENCE_UNAVAILABLE` and generates equal-weight model (`2.0%` each) without mislabeling estimates as official weights.

---

## 2. Verification Summary

- **Forward Unit Tests**: 9/9 PASSED (`pytest -v tests/upstox_capture/`)
- **Reverse Unit Tests**: 9/9 PASSED
- **Compilation Check**: `python3 -m py_compile` PASSED (0 errors)
- **Git Diff Check**: `git diff --check` PASSED (0 trailing whitespace or format errors)
- **Secret Scan**: Clean (0 credentials committed)
- **Protected Runtime Drift**: 0 modifications to immutable historical corpus `2026-08-03`.
