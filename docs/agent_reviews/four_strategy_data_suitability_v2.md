# Four Strategy Data Suitability V2

## IMPLEMENTATION DIRECTION
RIGHT_WITH_GAPS

## APPROVED OBJECTIVE
Integrate the approved four-strategy data-suitability dependency closure onto current `main` using read-only local data and immutable JSON evidence, without widening the runtime surface.

## WHAT WAS ACTUALLY IMPLEMENTED
- Added explicit source-root authority records to the corpus inventory and manifest.
- Added the four-strategy inventory contract at `config/strategy_inventory.yml` so the frozen-contract test can hash the real runtime-facing inventory.
- Transplanted the exact source versions of `core/movement_contract.py`, `core/orb_ohlcv_validation.py`, `core/session_bar_history.py`, `core/strategy_parameter_profiles.py`, `core/strategy_temporal_harness.py`, `strategies/movement/_utils.py`, `strategies/movement/compression_breakout.py`, `strategies/movement/opening_range_breakout.py`, `strategies/movement/option_pressure.py`, `strategies/movement/trend_pullback.py`, `strategies/movement/vwap_reclaim.py`, `tests/test_movement_contract.py`, `tests/test_opening_movement_strategies.py`, `tests/test_compression_trend_movement_strategies.py`, `tests/test_vwap_trap_movement_strategies.py`, `tests/test_exhaustion_mean_reversion_strategies.py`, `tests/test_event_late_day_movement_strategies.py`, `tests/test_option_confirmation.py`, `tests/test_orb_ohlcv_validation.py`, `tests/test_strategy_generators_lineage.py`, `tests/test_strategy_parameter_profiles.py`, `tests/test_opening_range_retest_temporal_fixture_contract.py`, and `tests/vwap_reclaim_test_support.py` so the source contract, helper, and validation tests match the current-main integration.
- Failed closed when a requested source root is missing or unreadable, instead of falling back to worktree-relative scratch directories.
- Fixed the completed-bar coverage gate to recognize `FULL_SESSION` so the real completed-history corpus is counted as authoritative truth.
- Regenerated the immutable evidence into `v2` / `v3` artifacts from the shared Tradebot roots.
- Kept the current-main orchestrator integrity test unchanged; the source-branch auth-fallback variant was excluded from this integration.

## ARCHITECTURE CHANGE
NECESSARY_MINIMAL

## STARTING HEAD
`fa3b35e8007ab3b439523c2fcf465a9669a34d2a`

## IMPLEMENTATION COMMIT
pending commit

## INTEGRATION TARGET
- `integration/four-strategy-data-suitability-main`

## SOURCE BACKUP BRANCH
- `fix/four-strategy-data-suitability-integrity`
- `835ff79150c3f55b3bc1b873390e9dffd5ba19fc`

## SOURCE PUBLISHED LINEAGE
- `research/four-strategy-data-suitability-v2-clean`
- `0fd5e0a81d182e0ca5848b9ab7ba3b5d7b19c01a`

## FILES CHANGED
- `config/strategy_inventory.yml`
- `core/movement_contract.py`
- `core/orb_ohlcv_validation.py`
- `core/session_bar_history.py`
- `core/strategy_temporal_harness.py`
- `core/strategy_parameter_profiles.py`
- `strategies/movement/compression_breakout.py`
- `strategies/movement/opening_range_breakout.py`
- `strategies/movement/_utils.py`
- `strategies/movement/option_pressure.py`
- `strategies/movement/trend_pullback.py`
- `strategies/movement/vwap_reclaim.py`
- `research/strategy_validation/__init__.py`
- `research/strategy_validation/corpus_inventory.py`
- `research/strategy_validation/data_suitability.py`
- `scripts/build_four_strategy_dataset_manifest.py`
- `tests/test_four_strategy_contract_freeze.py`
- `tests/test_four_strategy_dataset_manifest.py`
- `tests/test_compression_trend_movement_strategies.py`
- `tests/test_event_late_day_movement_strategies.py`
- `tests/test_exhaustion_mean_reversion_strategies.py`
- `tests/test_movement_contract.py`
- `tests/test_opening_movement_strategies.py`
- `tests/test_option_confirmation.py`
- `tests/test_orb_ohlcv_validation.py`
- `tests/test_opening_range_retest_temporal_fixture_contract.py`
- `tests/test_strategy_generators_lineage.py`
- `tests/test_strategy_parameter_profiles.py`
- `tests/test_vwap_trap_movement_strategies.py`
- `tests/vwap_reclaim_test_support.py`
- `docs/agent_reviews/four_strategy_data_suitability_v2.md`
- `docs/agent_reviews/four_strategy_contract_bundle_v1.json`
- `docs/agent_reviews/four_strategy_contract_bundle_v1.json.sha256`
- `docs/agent_reviews/four_strategy_dataset_manifest_v1.json`
- `docs/agent_reviews/four_strategy_dataset_manifest_v1.json.sha256`
- `docs/agent_reviews/four_strategy_dataset_manifest_v3.json`
- `docs/agent_reviews/four_strategy_dataset_manifest_v3.json.sha256`
- `docs/agent_reviews/upstox_corpus_inventory_v2.json`
- `docs/agent_reviews/upstox_corpus_inventory_v2.json.sha256`

## MAINLINE COLLISION
- `tests/test_orchestrator_reports_finally.py` was inspected against `origin/main` and left unchanged.
- The stricter current-main assertion remains in force; the source-branch auth-fallback variant was not transplanted.

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
- `valid_source_files`: 2395
- `invalid_source_files`: 11
- `unique_file_hashes`: 2358
- `corpus_snapshot_id`: `95adf5bd9ac3f5b9d4beb6221937ef2188cf6244b634838c2b69b3061db9d5f2`
- `data_snapshot_id`: `95adf5bd9ac3f5b9d4beb6221937ef2188cf6244b634838c2b69b3061db9d5f2`

## ACCEPTED DATA / INVALID SOURCE RECONCILIATION
- Accepted snapshot data files:
  - `CANDLE_OHLCV`, `DATASET`, `ACCEPTED`: 1512
  - `TICK_WITH_DEPTH`, `DATASET`, `ACCEPTED`: 130
  - `TICK_QUOTE`, `DATASET`, `PARTIAL`: 50
  - `CANDLE_OHLCV`, `DATASET`, `PARTIAL`: 35
  - `TICK_WITH_DEPTH`, `DATASET`, `PARTIAL`: 2
  - `INVALID_OR_UNVERIFIABLE`, `DATASET`, `UNVERIFIABLE`: 8
  - total accepted_for_snapshot=true data files: 1737
- Non-snapshot metadata and cache files:
  - `MANIFEST`, `FETCH_MANIFEST`: 665
  - `MANIFEST`, `CAPTURE_MANIFEST`: 1
  - `UNKNOWN`, `CACHE_ARTIFACT`: 3
  - total accepted_for_snapshot=false files: 669
- Invalid source files:
  - 8 unreadable parquet data files under `.runtime/market_data`
  - 3 cache artifacts
  - total invalid_source_files: 11

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

## CANDLE AND SESSION RECONCILIATION
- Candle dataset files counted in the inventory:
  - `CANDLE_OHLCV`, `DATASET`: 1547
- Coverage session counts by underlying:
  - `nifty.session_count`: 521
  - `banknifty.session_count`: 501
  - `other_underlyings.session_count`: 526
- The apparent `1547` vs `1548` mismatch is a unit mismatch:
  - `1547` is the unique candle dataset file count.
  - `1548` is the sum of per-underlying coverage session counters.
  - These values are not directly comparable.

## FETCH-MANIFEST RECONCILIATION
- Total fetch manifests reconciled: 666
- By status:
  - `FETCH_SUCCESS_RECONCILED`: 526
  - `FETCH_FAILED_HTTP`: 108
  - `FETCH_FAILED_NO_CANDLES`: 31
  - `FETCH_PARTIAL`: 1
- One partial capture manifest records `UPSTOX_CAPTURE_AUTH_FAILED` at `/Users/madhuram/tradebot/.runtime/market_data/manifests/upstox_capture_manifest_20260710.json`.

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
- Strategy summary: every strategy has signal suitability with provenance limitations; execution remains partial or blocked.

## TEST INTEGRITY
- `tests/test_orchestrator_reports_finally.py` remains on the current-main version and still surfaces the pre-existing `[AUTH] missing_kite_access_token` failure.
- The four-strategy contract, helper, and dataset-manifest tests were brought over as standalone evidence.
- The orb validation harness was updated to the source contract and now blocks when completed-bar history is absent.

## NEGATIVE CONTROLS
- No source corpus was mutated in place.
- Manifest presence alone does not imply composite joinability.
- No backtest or profitability analysis was run.
- `.DS_Store` and zero-byte presence markers remain non-authoritative cache artifacts.
- `runtime/strategy_validation/regime_timeline.jsonl` is treated as generated test residue, not a source change.

## SUBAGENT RESULTS
- dependency closure and main-collision audits were performed by read-only subagents; the current-main collision was limited to `tests/test_orchestrator_reports_finally.py`

## FOCUSED TEST RESULTS
- `python -m py_compile research/strategy_validation/__init__.py research/strategy_validation/corpus_inventory.py research/strategy_validation/data_suitability.py scripts/build_four_strategy_dataset_manifest.py tests/test_four_strategy_contract_freeze.py tests/test_four_strategy_dataset_manifest.py`: pass
- `python -m pytest -q tests/test_orb_ohlcv_validation.py tests/test_orchestrator_reports_finally.py`: `7 passed, 1 failed`

## STATIC CHECKS
- `git diff --check`: pass

## FULL SUITE RESULT
- `5822 passed, 24 deselected, 935 warnings, 1 failed in 756.58s`

## CLAIM BOUNDARY
This work proves the incremental corpus inventory and manifest are keyed to the real shared Tradebot roots and that the evidence note now matches the actual manifest and coverage counts. It does not prove strategy edge, profitability, live readiness, or execution certification.

## ROLLBACK
Revert the changes in:
- `docs/agent_reviews/four_strategy_data_suitability_v2.md`
- the four-strategy research package, CLI, tests, and JSON evidence files added by this integration

## FINAL VERDICT
`FOUR_STRATEGY_DATA_SUITABILITY_V2_COMPLETE`
