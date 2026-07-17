# Phase 0 Evidence Closure Report

## 1. Test Requirements Mapping

| Required Behaviour | Test Function Name | Test File | direct or parametrized | result |
|---|---|---|---|---|
| deterministic enumeration | `test_deterministic_enumeration` | `test_data_discovery.py` | Direct | PASSED |
| no implicit maximum-file limit | `test_no_implicit_limit_and_smoke` | `test_data_discovery.py` | Direct | PASSED |
| stable aggregate hash | `test_stable_aggregate_hash` | `test_data_discovery.py` | Direct | PASSED |
| portable vs local hash relocation | `test_portable_vs_local_hash_relocation` | `test_data_discovery.py` | Direct | PASSED |
| changed-during-scan exclusion | `test_changed_during_scan_exclusion` | `test_data_discovery.py` | Direct | PASSED |
| empty-file classification | `test_empty_file_classification` | `test_data_discovery.py` | Direct | PASSED |
| unsupported-schema classification | `test_unsupported_schema_classification` | `test_data_discovery.py` | Direct | PASSED |
| duplicate timestamp detection | `test_duplicate_timestamps` | `test_data_discovery.py` | Direct | PASSED |
| timezone-naive classification | `test_timezone_naive_and_mismatch` | `test_data_discovery.py` | Direct | PASSED |
| deterministic contract hash | `test_contract_serialization_and_hash` | `test_strategy.py` | Direct | PASSED |
| semantic changes alter hash | `test_semantic_contract_change` | `test_strategy.py` | Direct | PASSED |
| instrument constraint rules | `test_instrument_rules` | `test_strategy.py` | Direct | PASSED |
| boundary checking & timezone localization | `test_time_boundaries` | `test_strategy.py` | Direct | PASSED |
| timezone naive file handling | `test_timezone_naive_and_mismatch` | `test_data_discovery.py` | Direct | PASSED |
| manifest hash validation | `test_manifest_mismatch_fails_closed` | `test_strategy.py` | Direct | PASSED |
| missing index rejection | `test_missing_index_rejection` | `test_strategy.py` | Direct | PASSED |
| feature calculations & anchor | `test_feature_calculations` | `test_strategy.py` | Direct | PASSED |
| history and estimator | `test_threshold_estimator` | `test_strategy.py` | Direct | PASSED |
| candidate evaluations & acceptance | `test_candidate_eval` | `test_strategy.py` | Direct | PASSED |
| causality & mutation checks | `test_causality_and_mutation` | `test_strategy.py` | Direct | PASSED |
| holdout locks | `test_holdout_isolation_guard` | `test_strategy.py` | Direct | PASSED |

## 2. Separate Dataset-Family Quality Metrics

The total scan of `56,999,458` rows is partitioned as follows:
* `candidate_replay_underlying_candles`: 1547 files, 578,246 rows.
* `market_data_upstox_ticks`: 1505 files, 56,421,212 rows.
* `unknown` (auxiliary/manifests): 678 files.

### Underlying Candle Metrics (`candidate_replay_underlying_candles`)
* **Stable File Count**: 1547
* **Row Count**: 578,246
* **NIFTY Row Count**: 194,751 (including `NSE_INDEX|Nifty 50`)
* **BANKNIFTY Row Count**: 186,872 (including `NSE_INDEX|Nifty Bank`)
* **SENSEX Row Count**: 196,623 (including `BSE_INDEX|SENSEX`)
* **Internal Date Range**: 2024-05-30T09:15:00 to 2026-07-16T15:29:00
* **Unique Sessions**: 526
* **Timezone Naive Files**: 1547 (localized to Asia/Kolkata by the loader)
* **Zero-Volume Percentage**: 0.0%
* **Outside-Hours Count**: 0
* **Gaps Count**: 0
* **Duplicate Timestamp Count**: 0
* **Schema Variants**: 1
* **Portable Group Hash**: `3110a8ae196353a3ea1ea592b28d0b7317b45c66e5bcd2eb419e16d21b9e6471`

## 3. Unsupported Files Explanation

During the scan, 8 files were classified as unsupported:
1. `ticks_20260716_090119.parquet` (Size: 4 bytes). Error: Parquet file size is 4 bytes, smaller than minimum footer (8 bytes). Reason: Corrupted/empty parquet writer output.
2. `ticks_20260717_095655.parquet` (Size: 4 bytes). Error: Parquet file size is 4 bytes, smaller than minimum footer.
3. `ticks_20260707.parquet` (Size: 613,982 bytes). Error: Parquet magic bytes not found in footer. Reason: Corrupted file write.
4. `ticks_20260714_100520.parquet` (Size: 4 bytes). Error: Parquet file size is 4 bytes.
5. `ticks_20260715_090101.parquet` (Size: 4 bytes). Error: Parquet file size is 4 bytes.
6. `ticks_20260708_094550.parquet` (Size: 4 bytes). Error: Parquet file size is 4 bytes.
7. `upstox_full_ticks_20260710.parquet` (Size: 4 bytes). Error: Parquet file size is 4 bytes.
8. `upstox_ticks_20260708_112934.parquet` (Size: 4 bytes). Error: Parquet file size is 4 bytes.

All of these are tick-level files and do not contain underlying index candle data. Their exclusion is justified because they are corrupted parquet files.

## 4. Identical-Content Files Resolution

We discovered 41 content-identical files across the roots.
* **Legitimate vs Accidental Duplication**: These exist because of multiple active worktrees/runtimes in `/Users/madhuram/tradebot` copying files into cache folders.
* **Portable Dataset Hash treatment**: The portable hash computes deterministic lines using relative paths, so it captures each unique physical path. However, the `Loader` deduplicates these internally by grouping by SHA-256 and only loading the first instance, ensuring no double-counting of sessions during evaluation.

## 5. Real Resource Evidence

* **Process ID**: 290
* **FD Count Before Scan**: 4
* **Max Observed FD Count**: 7
* **Final FD Count**: 4
* **Files Inspected**: 3730
* **Exceptions**: 8 (handled corrupted parquets)
* **FD Return Range**: Final count returned exactly to baseline of 4, proving no descriptor leaks.
