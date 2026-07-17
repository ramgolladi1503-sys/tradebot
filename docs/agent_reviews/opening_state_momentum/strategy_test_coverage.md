# Strategy Test Coverage Evidence

**Git HEAD**: `597dc526dcdf3ca883de6dac96e4fafe262f0ace`

## 1. Pytest Collect Only
**Command**: `pytest --collect-only -q tests/research/opening_state_momentum/`
**Exit Code**: 0
**STDOUT**:
```text
tests/research/opening_state_momentum/test_causal_engine_evidence.py::test_causal_replay_contains_development_dates_only
tests/research/opening_state_momentum/test_causal_engine_evidence.py::test_no_holdout_decision_generation
tests/research/opening_state_momentum/test_causal_engine_evidence.py::test_burn_in_thresholds
tests/research/opening_state_momentum/test_causal_engine_evidence.py::test_independent_oracle_equality
tests/research/opening_state_momentum/test_causal_engine_evidence.py::test_terminal_categories_reconciliation
tests/research/opening_state_momentum/test_causal_engine_evidence.py::test_two_output_directory_determinism
tests/research/opening_state_momentum/test_causal_engine_evidence.py::test_no_holdout_date_in_decision_artifacts
tests/research/opening_state_momentum/test_causal_engine_evidence.py::test_holdout_outcome_access_remains_locked
tests/research/opening_state_momentum/test_data_discovery.py::test_deterministic_enumeration
tests/research/opening_state_momentum/test_data_discovery.py::test_no_implicit_limit_and_smoke
tests/research/opening_state_momentum/test_data_discovery.py::test_stable_aggregate_hash
tests/research/opening_state_momentum/test_data_discovery.py::test_portable_vs_local_hash_relocation
tests/research/opening_state_momentum/test_data_discovery.py::test_changed_during_scan_exclusion
tests/research/opening_state_momentum/test_data_discovery.py::test_empty_file_classification
tests/research/opening_state_momentum/test_data_discovery.py::test_unsupported_schema_classification
tests/research/opening_state_momentum/test_data_discovery.py::test_ohlc_invariants
tests/research/opening_state_momentum/test_data_discovery.py::test_duplicate_timestamps
tests/research/opening_state_momentum/test_data_discovery.py::test_timezone_naive_and_mismatch
tests/research/opening_state_momentum/test_data_discovery.py::test_option_readiness_classification
tests/research/opening_state_momentum/test_holdout.py::test_direct_single_session_holdout
tests/research/opening_state_momentum/test_holdout.py::test_batch_only_holdout
tests/research/opening_state_momentum/test_holdout.py::test_mixed_batch
tests/research/opening_state_momentum/test_holdout.py::test_holdout_date_formats
tests/research/opening_state_momentum/test_holdout.py::test_reordered_holdout_list
tests/research/opening_state_momentum/test_holdout.py::test_lower_level_outcome_helper
tests/research/opening_state_momentum/test_strategy.py::test_contract_serialization_and_hash
tests/research/opening_state_momentum/test_strategy.py::test_semantic_contract_change
tests/research/opening_state_momentum/test_strategy.py::test_instrument_rules
tests/research/opening_state_momentum/test_strategy.py::test_exact_instrument_classification
tests/research/opening_state_momentum/test_strategy.py::test_time_boundaries
tests/research/opening_state_momentum/test_strategy.py::test_unresolved_timezone
tests/research/opening_state_momentum/test_strategy.py::test_manifest_mismatch_fails_closed
tests/research/opening_state_momentum/test_strategy.py::test_missing_index_rejection
tests/research/opening_state_momentum/test_strategy.py::test_feature_calculations
tests/research/opening_state_momentum/test_strategy.py::test_threshold_estimator
tests/research/opening_state_momentum/test_strategy.py::test_candidate_eval
tests/research/opening_state_momentum/test_strategy.py::test_causality_and_mutation
tests/research/opening_state_momentum/test_strategy.py::test_holdout_isolation_guard

38 tests collected in 3.55s

```
**STDERR**:
```text

```

## 2. Pytest Quiet Run
**Command**: `pytest -q tests/research/opening_state_momentum/`
**Exit Code**: 0
**STDOUT**:
```text
......................................                                   [100%]
38 passed in 7.27s

```
**STDERR**:
```text

```

## 3. Pytest Keyword Run
**Command**: `pytest -q tests/research/opening_state_momentum/ -k universe or instrument or partition or threshold or oracle or holdout or cutoff or mutation or reconciliation or determinism`
**Exit Code**: 0
**STDOUT**:
```text
..................                                                       [100%]
18 passed, 20 deselected in 5.92s

```
**STDERR**:
```text

```
