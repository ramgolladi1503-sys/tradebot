# Whole-repository failure classification

**Verdict: PASS — latest current-tree full offline repository run is green.** The isolated-temp rerun completed with 8,493 passed, 9 skipped, 28 deselected, 1,476 warnings in 866.58 seconds (exit 0). The previous completed runs had two failures and then one failure; both defects are now fixed and the latest run has no failures. The earlier interrupted run remains historical only. Candidate dependency authority and T-1 provenance remain separate blocked gates and are not certified by pytest.
## Classification rules

- `RELATED_TO_PATCH_OR_STALE_FIXTURE`: later targeted run establishes correction/pass, but does not prove clean-base behavior.
- `NOT_REPRODUCED_IN_ISOLATION`: isolated run passed; aggregate cause remains unknown.
- `ENVIRONMENTAL_REPRODUCED_ON_BASE`: failure is reproduced in a clean archive of the exact base SHA and is caused by a missing/unhydrated external artifact.
- `WHOLE_REPO_UNKNOWN`: failure or stall lacks an exact isolated reproduction or correlated process evidence.

## Historical failures from the earlier interrupted run

The following table preserves the 31 nodes seen in the earlier interrupted run. It is historical context; these rows are not the final completed-run failure set.

| Test | Classification | Evidence status |
|---|---|---|
| `tests/option_backtest/test_engine.py::test_backtest_trades_executable_rows_and_hits_target` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_signal_enters_on_first_eligible_later_candle_in_certification_mode` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_certification_mode_rejects_entry_quote_captured_before_signal` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_trade_cannot_exit_using_signal_candle_range` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_timeout_uses_elapsed_time_not_row_count_with_missing_bars` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_same_entry_candle_stop_target_ambiguity_remains_conservative` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_proxy_mode_derives_timing_but_remains_proxy_research` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_strict_mode_missing_book_qty_fails_closed_without_liquidity_fallback` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_gap_through_stop_uses_conservative_exit_bid` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_gross_costs_and_net_pnl_are_reconciled` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_partial_fill_uses_filled_quantity_only` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_proxy_mode_marks_weaker_exit_assumption_explicitly` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_summary_and_journal_reconcile_trade_and_pnl_fields` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_ambiguity_count_reconciles_with_trade_rows` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_engine.py::test_strict_result_label_can_be_certification_candidate` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_wfa.py::test_wfa_final_holdout_pass_requires_all_gates` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/option_backtest/test_wfa.py::test_wfa_repeated_holdout_run_is_blocked` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/test_advisory_level_reconciliation.py::test_apply_level_normalization_promotes_valid_queue_only_candidate` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/test_c1_c2_regime_decoupling.py::test_regime_source_immutability_audit` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Repair settings moved out of pinned config; current combined regression passes. |
| `tests/test_decision_engine.py::test_strong_candidate_executes - Assert...` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/test_executable_truth_firebreak.py::test_clean_fresh_candidate_is_allowed_by_truth_classifier` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Included in current combined regression: pass. |
| `tests/test_executable_truth_firebreak.py::test_low_data_confidence_is_blocked` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Included in current combined regression: pass. |
| `tests/test_execution_quality_helpers.py::test_tight_spread_liquid_candidate_remains_executable` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/test_execution_quality_helpers.py::test_execution_quality_components_favor_liquid_over_illiquid` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/test_execution_simulator.py::test_execution_sim_reprices_or_cancels_when_rr_collapses` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/test_execution_simulator.py::test_execution_sim_can_model_partial_fill` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Explicit historical scope or feed-health evidence added; current regression passes. Clean-base subset also passed. |
| `tests/test_feed_00_canonical_feed_truth.py::test_runtime_store_writes_canonical_truth_to_required_artifacts` | RELATED_TO_PATCH_OR_STALE_FIXTURE | CORRECTED_AND_COVERED_BY_465_PASS |
| `tests/test_feed_recovery_simulation.py::test_ws1006_classification - A...` | NOT_REPRODUCED_IN_ISOLATION | ISOLATED_PASS_REPORTED |
| `tests/test_kite_read_only_observation_runtime.py::test_packet_driven_completed_bars_export_live_source_meg_row` | RELATED_TO_PATCH_OR_STALE_FIXTURE | Corrected cutoff to final synthetic tick +5 sec; focused rerun passes. |
| `tests/test_market_event_graph_constituent_refresh.py::test_process_level_fast_cycle_refreshes_with_no_candidates` | NOT_REPRODUCED_IN_ISOLATION | ISOLATED_PASS_REPORTED |

## Superseded residual failures from the preceding completed run

| Test | Classification | Evidence status |
|---|---|---|
| `tests/test_four_strategy_dataset_manifest.py::test_real_candle_and_tick_truth_prove_current_field_classification` | RESOLVED_POINTER_SAFE_LOCAL_FALLBACK | The tracked LFS pointer is recognized and skipped; the test selects the byte-identical local canonical copy if available, otherwise skips explicitly. Helper tests cover pointer-followed-by-copy and pointer-only cases. The tracked worktree file remains the original 132-byte pointer. |
| `tests/test_trade_truth_prospective_repair.py::test_broker_write_guards_active` | FIXED_AND_FULL_SUITE_VERIFIED | Guard installation now resolves the active module through `importlib.import_module`; a stale package-attribute regression case passes. |

## Pre-hydration implicated-module rerun (historical)

The 23 feed-scope-dependent failures from the first rerun were resolved by explicitly marking historical option replay as `HISTORICAL_REPLAY` (so current websocket state is not substituted for historical quote authority) and supplying explicit symbol-scoped feed observations in execution decision/simulation fixtures. The safety classifier remains fail-closed when required runtime evidence is absent; tests do not stub out the classifier.

Command: `/opt/anaconda3/bin/pytest -q --tb=short` over the 13 modules listed in `CONTINUATION_FAILURE_ISOLATION.log`. Initial result: 24 failed, 88 passed, 1 skipped, 3 warnings, 7.45 sec. Latest rerun after fixes: 112 passed, 1 skipped, 1 failed (the LFS pointer test), 3 warnings, 7.23 sec. The four-strategy real-data test fails because the selected parquet path is an unhydrated Git LFS pointer (132-byte pointer, expected object size 7,604,505); the object was not fetched or changed. C1/C2 config hash failure was removed by moving repair-only settings into `config/feed_runtime_reliability.py`; pinned `config/config.py` hash is restored.

## Latest full-suite completion

The latest current-tree run completed with `8,493 passed, 9 skipped, 28 deselected, 1,476 warnings` in 866.58 seconds and exit 0. The archived output is `WHOLE_REPO_REGRESSION_ISOLATED_TMP_20261001.log`. It used a fresh, dedicated pytest temp root and ran after the candidate registry/opaque-ID changes.

An intervening default-temp-root run ended with 8,439 passed, 54 setup errors, 9 skipped, 28 deselected, 1,477 warnings in 1,074.70 seconds. Error summaries report numbered pytest temp-directory allocation failures. The six affected research modules passed 61/61 with a fresh root; the current whole-suite fresh-root rerun also passed. Classify the intermediate run as `ENVIRONMENTAL / TEMP_ROOT_ALLOCATION_NOT_REPRODUCED`; do not count it as a pass. The current full run supersedes it. The exact tick dataset test selects the byte-identical local canonical copy without modifying the tracked LFS pointer, and explicitly skips when only a pointer is available. The broker guard regression passed after binding installation to the active imported module object. Earlier completed runs, including the 8,482-pass hydrated-file run, remain preserved as historical evidence. The previous suite stall was not reproduced.

## Conclusion

The current whole-repository offline suite is green. Candidate dependency authority is still partial, authoritative T-1 provenance remains blocked, stress evidence remains offline-only, and production behavior remains unverified. A green suite does not grant runtime or execution readiness.
