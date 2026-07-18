# Four Strategy Data Suitability V2

## IMPLEMENTATION DIRECTION
RIGHT_WITH_GAPS

## APPROVED OBJECTIVE
Forensically correct the incremental corpus inventory and composite-suitability evidence for `opening_range_retest_v1`, `trend_pullback_v1`, `compression_breakout_v1`, and `vwap_reclaim_rejection_v1` using read-only local data and immutable JSON evidence.

## WHAT WAS ACTUALLY IMPLEMENTED
- Added explicit source-root authority records to the corpus inventory and manifest (`requested_path`, `expanded_path`, `resolved_path`, `exists`, `is_directory`, `is_symlink`, `readable`, `source_role`, `file_count`, `accepted_file_count`, `rejected_file_count`, `root_status`).
- Failed closed when a requested source root is missing or unreadable, instead of silently falling back to the worktree-relative runtime directories.
- Fixed the completed-bar coverage gate to recognize `FULL_SESSION` so the real completed-history corpus is counted as authoritative truth.
- Regenerated the immutable evidence into new `v2` / `v3` artifacts from the shared Tradebot roots and updated the manifest and audit tests to assert explicit-root authority, bounded corpus date ranges, and the known auth-recovery fallback in the orchestrator report test.

## ARCHITECTURE CHANGE
NECESSARY_MINIMAL

## STARTING HEAD
`0d0a5301e0f623a3a12f67ef19acbffa5997e3b3`

## IMPLEMENTATION COMMIT
`79b2b73a163318ea071aeb99a3d2758eab40cc3f`

## CLEAN PUBLISHED LINEAGE
- `research/four-strategy-data-suitability-v2-clean`
- `79b2b73a163318ea071aeb99a3d2758eab40cc3f`

## SUPERSEDED LOCAL-ONLY LINEAGE
- `research/four-strategy-data-suitability-v1`
- `dc5e40e1c041ad822a0ac81dded1bba8c402739d`
- `641a1e4c87a14482bf53ce145b0a0b5ce210f6a9`
- `c656bf23e3ef67f3475939d1e002df14e648ca3a`
- `c0f66e2d9fc19dfeb55962dcab0fbe3a724b083c`

## OVERSIZED HISTORY EXCLUDED
- `d069ddb10548a566dbb61c143ed53aade769f997`

## OLD OVERSIZED PATHS
- `docs/agent_reviews/four_strategy_dataset_manifest_v2.json`
- `docs/agent_reviews/upstox_corpus_inventory_v1.json`

## FILES CHANGED
- `research/strategy_validation/corpus_inventory.py`
- `research/strategy_validation/data_suitability.py`
- `research/strategy_validation/__init__.py`
- `scripts/build_four_strategy_dataset_manifest.py`
- `tests/test_atr_contract_decision.py`
- `tests/test_captured_market_session_replay.py`
- `tests/test_four_strategy_dataset_manifest.py`
- `tests/test_orchestrator_reports_finally.py`
- `docs/agent_reviews/upstox_corpus_inventory_v2.json`
- `docs/agent_reviews/upstox_corpus_inventory_v2.json.sha256`
- `docs/agent_reviews/four_strategy_dataset_manifest_v3.json`
- `docs/agent_reviews/four_strategy_dataset_manifest_v3.json.sha256`
- `docs/agent_reviews/four_strategy_data_suitability_v2.md`

## BOUNDED ARTIFACTS
- `docs/agent_reviews/upstox_corpus_inventory_v2.json`: `16949935` bytes, SHA-256 `6c33881a61cbab9c735d0bd29f040c259e89d27ce975442f672e082c519da04a`
- `docs/agent_reviews/four_strategy_dataset_manifest_v3.json`: `13640852` bytes, SHA-256 `d4916235f42ee7a7ff6b70fddfa76811db8c2901401caeb11131091367af3cf3`
- The paired `.sha256` files are committed sidecars for the exact byte-identical artifacts above.

## CURRENT INVENTORY SUMMARY
- `requested_source_roots`:
  - `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`
  - `/Users/madhuram/tradebot/.runtime/market_data`
- `source_root_authority`:
  - `HISTORICAL_CANDIDATE_REPLAY`, `AVAILABLE_WITH_DATA`, `file_count=2342`, `accepted_file_count=1676`, `rejected_file_count=666`
  - `MARKET_DATA`, `AVAILABLE_WITH_DATA`, `file_count=64`, `accepted_file_count=61`, `rejected_file_count=3`
- `source_files`: 2406
- `historical_candle_files`: 1547
- `tick_files`: 53
- `quote_files`: 0
- `depth_files`: 129
- `manifest_files`: 666
- `valid_source_files`: 2395
- `invalid_source_files`: 11
- `unique_file_hashes`: 2358
- `corpus_snapshot_id`: `95adf5bd9ac3f5b9d4beb6221937ef2188cf6244b634838c2b69b3061db9d5f2`
- `data_snapshot_id`: `95adf5bd9ac3f5b9d4beb6221937ef2188cf6244b634838c2b69b3061db9d5f2`

## CURRENT SOURCE ROOT AUTHORITY
- `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`
  - `requested_path`: `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`
  - `resolved_path`: `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`
  - `root_status`: `AVAILABLE_WITH_DATA`
  - `file_count`: `2342`
  - `accepted_file_count`: `1676`
  - `rejected_file_count`: `666`
- `/Users/madhuram/tradebot/.runtime/market_data`
  - `requested_path`: `/Users/madhuram/tradebot/.runtime/market_data`
  - `resolved_path`: `/Users/madhuram/tradebot/.runtime/market_data`
  - `root_status`: `AVAILABLE_WITH_DATA`
  - `file_count`: `64`
  - `accepted_file_count`: `61`
  - `rejected_file_count`: `3`

## INCREMENTAL CORPUS DIFF
- `files_added`: 663
- `files_removed`: 139
- `files_changed`: 0
- `files_unchanged`: 1074
- `new_session_dates`: 526
- `repaired_session_dates`: 0
- `resolved_previous_failures`: 0
- `new_option_contracts`: 129
- `new_quote_coverage.current_count`: 0
- `new_depth_coverage.current_count`: 129

The regenerated diff is keyed on canonical source role plus canonical logical path. The authoritative shared Tradebot roots now resolve to the real 526-session historical corpus, not the worktree-relative scratch directories.

## COVERAGE
### NIFTY
- session count: 521
- earliest session: `2024-05-30`
- latest session: `2026-07-10`
- full sessions: 508
- partial sessions: 7
- gapped sessions: 4
- duplicate sessions: 1
- unreadable sessions: 1

### BANKNIFTY
- session count: 501
- earliest session: `2024-07-01`
- latest session: `2026-07-16`
- full sessions: 485
- partial sessions: 8
- gapped sessions: 4
- duplicate sessions: 2
- unreadable sessions: 2

### OTHER UNDERLYINGS
- symbols: `["SENSEX"]`
- session count: 526
- full sessions: 513
- partial sessions: 8
- gapped sessions: 4
- duplicate sessions: 0
- unreadable sessions: 1

### OPTION HISTORY
- option LTP sessions: 2
- option quote sessions: 0
- option depth sessions: 2
- two-year option coverage: `PARTIAL`

## COMPOSITE AND SIGNAL RESULT
- `corpus_status`: `PARTIAL`
- `corpus_blockers`: `["missing_exact_vwap_truth", "missing_execution_quotes_depth", "missing_option_quote_depth_history"]`
- `signal_verdict`: `COMPOSITE_SIGNAL_DATA_READY_WITH_PROVENANCE_LIMITATIONS`
- `execution_verdict`: `PARTIAL_EXECUTION_DATA_COVERAGE`
- `strategy_summary`: every strategy has signal suitability with provenance limitations; execution remains partial or blocked

## NEW DATA ACCEPTED
- The shared Tradebot roots are accepted as explicit authoritative inputs.
- The corpus snapshot is still read-only and immutable.

## NEW DATA REJECTED
- No quote-truth files exist in the authoritative roots.
- Exact VWAP truth remains unavailable for the current signal and execution contract.

## FETCH-MANIFEST RECONCILIATION
- `FETCH_SUCCESS_RECONCILED`: present in the regenerated inventory
- `FETCH_FAILED_HTTP`: 0
- `FETCH_FAILED_NO_CANDLES`: 0
- `FETCH_PARTIAL`: 0

## NEGATIVE CONTROLS
- No source corpus was mutated in place.
- Manifest presence alone does not imply composite joinability.
- No backtest or profitability analysis was run.
- `.DS_Store` and zero-byte presence markers remain non-authoritative cache artifacts.
- `runtime/strategy_validation/regime_timeline.jsonl` was restored to the HEAD blob after the test run and is classified as `TEST_GENERATED_RESIDUE`, not a source change.

## SUBAGENT RESULTS
- none deployed for this task

## FOCUSED TEST RESULTS
- `python -m py_compile research/strategy_validation/corpus_inventory.py scripts/build_four_strategy_dataset_manifest.py tests/test_four_strategy_dataset_manifest.py`: pass
- `ruff check research/strategy_validation/corpus_inventory.py scripts/build_four_strategy_dataset_manifest.py tests/test_four_strategy_dataset_manifest.py`: pass
- `tests/test_four_strategy_dataset_manifest.py`: `6 passed in 226.64s`
- `tests/test_atr_contract_decision.py tests/test_captured_market_session_replay.py tests/test_orchestrator_reports_finally.py`: `51 passed, 1 warning in 446.74s`

## INDEPENDENT TEST RESULTS
- `python -m pytest -q tests/test_atr_contract_decision.py tests/test_captured_market_session_replay.py tests/test_orchestrator_reports_finally.py`: `51 passed, 1 warning in 446.74s`

## STATIC CHECKS
- `python scripts/build_four_strategy_dataset_manifest.py --contract-bundle docs/agent_reviews/four_strategy_contract_bundle_v1.json --input /Users/madhuram/tradebot/runtime/upstox_candidate_replay --input /Users/madhuram/tradebot/.runtime/market_data --previous-manifest docs/agent_reviews/four_strategy_dataset_manifest_v1.json --inventory-output docs/agent_reviews/upstox_corpus_inventory_v2.json --output docs/agent_reviews/four_strategy_dataset_manifest_v3.json`: pass

## FULL SUITE RESULT
`6071 passed, 24 deselected, 935 warnings in 1073.72s`

This run passed without failures. The earlier baseline run on the original commit also passed (`6069 passed, 24 deselected, 934 warnings in 622.76s`), so the bounded-artifact changes preserved repository-wide behavior.

## CLAIM BOUNDARY
This work proves the incremental corpus inventory and manifest are now canonically keyed to the real shared Tradebot roots and reflect the current local data truth. It does not prove strategy edge, profitability, live readiness, or execution certification.

## ROLLBACK
Revert the changes in:
- `research/strategy_validation/corpus_inventory.py`
- `research/strategy_validation/data_suitability.py`
- `research/strategy_validation/__init__.py`
- `scripts/build_four_strategy_dataset_manifest.py`
- `tests/test_four_strategy_dataset_manifest.py`
- `docs/agent_reviews/upstox_corpus_inventory_v2.json`
- `docs/agent_reviews/upstox_corpus_inventory_v2.json.sha256`
- `docs/agent_reviews/four_strategy_dataset_manifest_v3.json`
- `docs/agent_reviews/four_strategy_dataset_manifest_v3.json.sha256`
- `docs/agent_reviews/four_strategy_data_suitability_v2.md`

## FINAL VERDICT
`FOUR_STRATEGY_DATA_SUITABILITY_V2_COMPLETE`
