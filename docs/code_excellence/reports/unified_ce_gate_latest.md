# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `366`
- total_findings: `417`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `59` | `0` |  |
| `cerberus` | `PASS` | `0` | `357` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `.gitignore`
- `configs/candidate_strategy_validation_thresholds.json`
- `configs/next_day_option_tick_capture_contract.json`
- `configs/strategy_risk_contracts/MEAN_REVERSION_EXTENSION.json`
- `core/advisory_schema.py`
- `core/blocker_lifecycle.py`
- `core/candidate_finalization.py`
- `core/candidate_pool_orchestrator.py`
- `core/candidate_to_signal_adapter.py`
- `core/decision_dag.py`
- `core/feed/runtime_store.py`
- `core/feed_state_engine.py`
- `core/kite_depth_ws.py`
- `core/movement_contract.py`
- `core/movement_regime.py`
- `core/movement_registry.py`
- `core/opportunity_engine.py`
- `core/opportunity_ranking.py`
- `core/orchestrator.py`
- `core/pipeline_contracts.py`
- `core/ranking_orchestrator.py`
- `core/recovery_state_machine.py`
- `core/runtime_snapshot_producer.py`
- `core/yaml_compat.py`
- `docs/agent_reviews/pr638_audit_pipeline_contracts.md`
- `docs/code_excellence/reports/changed_paths.txt`
- `docs/data_contracts/next_day_option_tick_capture_contract.md`
- `docs/data_contracts/one_strategy_replay_after_clean_capture.md`
- `docs/runbooks/upstox_instrument_master_access.md`
- `docs/runbooks/upstox_token_safety.md`
- `docs/statistical_validation/01_data_inventory.md`
- `docs/strategy_design/MEAN_REVERSION_EXTENSION_V2_DESIGN.md`
- `docs/strategy_module_taxonomy.md`
- `docs/strategy_pipeline/SIMPLE_ORB/01_pipeline_summary.md`
- `docs/strategy_pipeline/SIMPLE_ORB/02_registry.md`
- `docs/strategy_pipeline/SIMPLE_ORB/03_truth.md`
- `docs/strategy_pipeline/SIMPLE_ORB/04_outcomes.md`
- `docs/strategy_pipeline/SIMPLE_ORB/05_statistics.md`
- `docs/strategy_pipeline/SIMPLE_ORB/06_certification.md`
- `docs/strategy_pipeline/SIMPLE_ORB/07_live_drift.md`
- `docs/strategy_pipeline/SIMPLE_ORB/08_blockers.md`
- `docs/strategy_pipeline/SIMPLE_ORB/09_limitations.md`
- `docs/strategy_pipeline/SIMPLE_ORB/10_final_decision.md`
- `docs/strategy_truth/01_loaded_registry.md`
- `docs/strategy_truth/02_parameter_inventory.md`
- `docs/strategy_truth/03_heuristic_audit.md`
- `docs/strategy_truth/04_indicator_inventory.md`
- `docs/strategy_truth/05_dependency_graph.md`
- `docs/strategy_truth/06_strategy_truth_summary.md`
- `docs/strategy_truth/08_control_flow_graphs.md`
- `docs/strategy_truth/09_semantic_comparison.md`
- `docs/strategy_truth/10_mathematical_audit.md`
- `docs/strategy_truth/11_hardened_strategy_truth_summary.md`
- `docs/strategy_validation/MEAN_REVERSION_EXTENSION_V1_FAILED_BASELINE.md`
- `docs/strategy_validation/MEAN_REVERSION_EXTENSION_V2_FAILED_BASELINE.md`
- `fix_all.py`
- `fix_indent.py`
- `live_soak.out`
- `patch.py`
- `patch2.py`
- `patch_base_execution_truth.py`
- `patch_context.py`
- `patch_context2.py`
- `patch_opp_engine.py`
- `patch_opportunity_engine.py`
- `patch_recovery.py`
- `patch_report.py`
- `patch_unsubscribe.py`
- `patch_watchdog.py`
- `print_registry.py`
- `requirements.txt`
- `rewrite_watchdog.py`
- `run_dbg.py`
- `runtime/strategy_validation/COMPRESSION_BREAKOUT/audit_report.json`
- `runtime/strategy_validation/COMPRESSION_BREAKOUT/candidate_replay_report.json`
- `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_1_report.json`
- `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_2_report.json`
- `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_3_5_report.json`
- `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_3_report.json`
- `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_4_report.json`
- `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_5_wfa_report.json`
- `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/audit_report.json`
- `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/candidate_replay_report.json`
- `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_1_report.json`
- `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_2_report.json`
- `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_3_5_report.json`
- `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_3_report.json`
- `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_4_report.json`
- `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_5_wfa_report.json`
- `runtime/strategy_validation/EXHAUSTION_REVERSAL/audit_report.json`
- `runtime/strategy_validation/EXHAUSTION_REVERSAL/candidate_replay_report.json`
- `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_1_report.json`
- `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_2_report.json`
- `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_3_5_report.json`
- `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_3_report.json`
- `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_4_report.json`
- `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_5_wfa_report.json`
- `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/audit_report.json`
- `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/candidate_replay_report.json`
- `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_1_report.json`
- `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_2_report.json`
- `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_3_5_report.json`
- `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_3_report.json`
- `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_4_report.json`
- `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_5_wfa_report.json`
- `runtime/strategy_validation/LATE_DAY_MOMENTUM/audit_report.json`
- `runtime/strategy_validation/LATE_DAY_MOMENTUM/candidate_replay_report.json`
- `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_1_report.json`
- `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_2_report.json`
- `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_3_5_report.json`
- `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_3_report.json`
- `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_4_report.json`
- `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_5_wfa_report.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/blocker_outcome_replay.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/blocker_outcome_replay.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/historical_data_catalog.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/historical_data_catalog.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/lineage_audit.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/lineage_audit.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/missing_option_paths_report.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase6_shadow_candidate_report.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_10_accounting_audit.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_11_parameter_discovery.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_11b_full_grid_report.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_11b_nested_parameter_discovery.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_11b_v2_full_grid_report.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_5_truth_audit.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_5_truth_audit.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_7_integrity_audit.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_7_integrity_audit.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_8_selection_quality_audit.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_9_cohort_edge.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_candidates.jsonl`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_pipeline_telemetry.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_report.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger.jsonl`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger_audit.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger_audit.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger_summary.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger_summary.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_v2_structural_audit.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_5_wfa_report.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/pipeline_contract_audit.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/pipeline_contract_audit.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/pipeline_health_report.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/pipeline_health_report.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/ranking_safety_audit.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/ranking_safety_audit.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/simulation_metadata.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_availability_probe.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_availability_probe.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_candle_file_audit.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_candle_file_audit.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_access_report.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_access_report.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_import.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_import.md`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_resolution.json`
- `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_resolution.md`
- `runtime/strategy_validation/NO_TRADE_CHOP/audit_report.json`
- `runtime/strategy_validation/NO_TRADE_CHOP/candidate_replay_report.json`
- `runtime/strategy_validation/NO_TRADE_CHOP/phase_1_report.json`
- `runtime/strategy_validation/NO_TRADE_CHOP/phase_2_report.json`
- `runtime/strategy_validation/NO_TRADE_CHOP/phase_3_5_report.json`
- `runtime/strategy_validation/NO_TRADE_CHOP/phase_3_report.json`
- `runtime/strategy_validation/NO_TRADE_CHOP/phase_4_report.json`
- `runtime/strategy_validation/NO_TRADE_CHOP/phase_5_wfa_report.json`
- `runtime/strategy_validation/OPENING_DRIVE/audit_report.json`
- `runtime/strategy_validation/OPENING_DRIVE/candidate_replay_report.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_1_report.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_2_report.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_3_5_report.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_3_report.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_10_accounting_audit.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_11b_v2_full_grid_report.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_5_truth_audit.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_5_truth_audit.md`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_7_integrity_audit.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_7_integrity_audit.md`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_candidates.jsonl`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_opening_drive_structural_audit.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_report.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_trade_ledger.jsonl`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_trade_ledger_summary.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_4_v2_structural_audit.json`
- `runtime/strategy_validation/OPENING_DRIVE/phase_5_wfa_report.json`
- `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/audit_report.json`
- `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/candidate_replay_report.json`
- `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_1_report.json`
- `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_2_report.json`
- `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_3_5_report.json`
- `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_3_report.json`
- `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_4_report.json`
- `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_5_wfa_report.json`
- `runtime/strategy_validation/OPTION_PRESSURE/audit_report.json`
- `runtime/strategy_validation/OPTION_PRESSURE/candidate_replay_report.json`
- `runtime/strategy_validation/OPTION_PRESSURE/phase_1_report.json`
- `runtime/strategy_validation/OPTION_PRESSURE/phase_2_report.json`
- `runtime/strategy_validation/OPTION_PRESSURE/phase_3_5_report.json`
- `runtime/strategy_validation/OPTION_PRESSURE/phase_3_report.json`
- `runtime/strategy_validation/OPTION_PRESSURE/phase_4_report.json`
- `runtime/strategy_validation/OPTION_PRESSURE/phase_5_wfa_report.json`
- `runtime/strategy_validation/SIMPLE_ORB/phase_1_report.json`
- `runtime/strategy_validation/SIMPLE_ORB/phase_2_report.json`
- `runtime/strategy_validation/SIMPLE_ORB/phase_3_5_report.json`
- `runtime/strategy_validation/SIMPLE_ORB/phase_3_report.json`
- `runtime/strategy_validation/SIMPLE_ORB/phase_4_report.json`
- `runtime/strategy_validation/SIMPLE_ORB/phase_5_wfa_report.json`
- `runtime/strategy_validation/SIMPLE_ORB/simple_orb_phase_evidence_inventory.json`
- `runtime/strategy_validation/SIMPLE_ORB/simple_orb_phase_evidence_inventory.md`
- `runtime/strategy_validation/TREND_PULLBACK/audit_report.json`
- `runtime/strategy_validation/TREND_PULLBACK/candidate_replay_report.json`
- `runtime/strategy_validation/TREND_PULLBACK/phase_1_report.json`
- `runtime/strategy_validation/TREND_PULLBACK/phase_2_report.json`
- `runtime/strategy_validation/TREND_PULLBACK/phase_3_5_report.json`
- `runtime/strategy_validation/TREND_PULLBACK/phase_3_report.json`
- `runtime/strategy_validation/TREND_PULLBACK/phase_4_report.json`
- `runtime/strategy_validation/TREND_PULLBACK/phase_5_wfa_report.json`
- `runtime/strategy_validation/VWAP_RECLAIM/audit_report.json`
- `runtime/strategy_validation/VWAP_RECLAIM/candidate_replay_report.json`
- `runtime/strategy_validation/VWAP_RECLAIM/phase_1_report.json`
- `runtime/strategy_validation/VWAP_RECLAIM/phase_2_report.json`
- `runtime/strategy_validation/VWAP_RECLAIM/phase_3_5_report.json`
- `runtime/strategy_validation/VWAP_RECLAIM/phase_3_report.json`
- `runtime/strategy_validation/VWAP_RECLAIM/phase_4_report.json`
- `runtime/strategy_validation/VWAP_RECLAIM/phase_5_wfa_report.json`
- `runtime/strategy_validation/batch_certification_report.json`
- `runtime/strategy_validation/batch_certification_report.md`
- `runtime/strategy_validation/blocked_datasets.json`
- `runtime/strategy_validation/blocked_datasets.md`
- `runtime/strategy_validation/candidate_replay_batch_summary.json`
- `runtime/strategy_validation/candidate_replay_batch_summary.md`
- `runtime/strategy_validation/candidate_replay_data_source_decision_report.json`
- `runtime/strategy_validation/candidate_replay_data_source_decision_report.md`
- `runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json`
- `runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.md`
- `runtime/strategy_validation/next_day_capture_contract_readiness.json`
- `runtime/strategy_validation/next_day_capture_contract_readiness.md`
- `runtime/strategy_validation/resolved_option_ticks_20260702.parquet`
- `runtime/strategy_validation/stress_replay_data_inventory_report.json`
- `runtime/strategy_validation/stress_replay_data_inventory_report.md`
- `runtime/strategy_validation/stress_replay_resolved_option_token_index.json`
- `runtime/upstox_instruments/complete.json`
- `scripts/analyze_mean_reversion_failure.py`
- `scripts/analyze_phase4_9_cohort_edge.py`
- `scripts/analyze_strategy_live_shadow.py`
- `scripts/audit_candidate_generator_contract.py`
- `scripts/audit_candidate_strategy_data_coverage.py`
- `scripts/audit_feed_negative_controls.py`
- `scripts/audit_historical_data_capability.py`
- `scripts/audit_mean_reversion_trade_ledger.py`
- `scripts/audit_opening_drive_structural.py`
- `scripts/audit_phase4_10_accounting.py`
- `scripts/audit_phase4_7_integrity.py`
- `scripts/audit_phase4_8_selection_quality.py`
- `scripts/audit_phase4_truth.py`
- `scripts/audit_phase4_v2_structural.py`
- `scripts/audit_phase6_eligibility.py`
- `scripts/audit_pipeline_contract.py`
- `scripts/audit_upstox_candle_files.py`
- `scripts/catalog_historical_data.py`
- `scripts/catalog_mean_reversion_historical_data.py`
- `scripts/diagnose_upstox_historical_access.py`
- `scripts/discover_simple_orb_phase_evidence.py`
- `scripts/fetch_missing_strategy_data_upstox.py`
- `scripts/fetch_upstox_historical_data.py`
- `scripts/generate_mean_reversion_trade_ledger.py`
- `scripts/generate_opening_drive_trade_ledger.py`
- `scripts/generate_pipeline_health_report.py`
- `scripts/import_upstox_instrument_master.py`
- `scripts/live_soak.py`
- `scripts/live_soak_advanced.py`
- `scripts/mark_blocked_certification_dataset.py`
- `scripts/plan_historical_data_fetch.py`
- `scripts/plan_mean_reversion_historical_coverage.py`
- `scripts/preflight_upstox_candidate_replay_data.py`
- `scripts/probe_upstox_historical_availability.py`
- `scripts/replay_blocker_outcomes.py`
- `scripts/replay_candidate_generator_strategy.py`
- `scripts/report_candidate_replay_data_sources.py`
- `scripts/report_phase6_shadow_candidates.py`
- `scripts/report_stress_replay_data_inventory.py`
- `scripts/report_upstox_candidate_replay_data_capability.py`
- `scripts/resolve_upstox_instrument_keys.py`
- `scripts/run_batch_strategy_certification.py`
- `scripts/run_candidate_generator_historical_audit.py`
- `scripts/run_candidate_ranking_proof_pack.py`
- `scripts/run_candidate_strategy_backtest.py`
- `scripts/run_candidate_strategy_wfa.py`
- `scripts/run_live_supervised.sh`
- `scripts/run_mean_reversion_parameter_discovery.py`
- `scripts/run_mean_reversion_parameter_discovery.py.orig`
- `scripts/run_offline_feed_candidate_truth_proof_pack.py`
- `scripts/run_opening_drive_parameter_discovery.py`
- `scripts/run_option_data_quality_proof_pack.py`
- `scripts/run_strategy_certification.py`
- `scripts/run_strategy_certification_pipeline.py`
- `scripts/tick_data_collector.py`
- `scripts/validate_filtered_stress_replay_dataset.py`
- `scripts/validate_mean_reversion_vertical_slice.py`
- `scripts/validate_next_day_capture_contract.py`
- `sitecustomize.py`
- `soak.pid`
- `strategies/simple_orb.py`
- `strategies/strategy_registry.py`
- `tests/auth/test_auth_safety.py`
- `tests/config/test_mode_safety.py`
- `tests/core/test_candidate_scoring_hypothesis.py`
- `tests/core/test_feed_runtime_hypothesis.py`
- `tests/core/test_risk_engine_hypothesis.py`
- `tests/execution/test_feed_fallback_safety.py`
- `tests/test_batch_strategy_certification.py`
- `tests/test_blocked_certification_dataset_marker.py`
- `tests/test_candidate_generator_contract.py`
- `tests/test_candidate_generator_historical_audit.py`
- `tests/test_candidate_generator_replay_harness.py`
- `tests/test_candidate_replay_data_source_decision_report.py`
- `tests/test_candidate_safety.py`
- `tests/test_candidate_strategy_backtest.py`
- `tests/test_candidate_strategy_data_coverage.py`
- `tests/test_candidate_strategy_wfa.py`
- `tests/test_candidate_to_signal_adapter.py`
- `tests/test_decision_dag.py`
- `tests/test_diagnose_upstox_historical_access.py`
- `tests/test_feed_state_engine.py`
- `tests/test_filtered_stress_replay_dataset_quality.py`
- `tests/test_historical_data_capability.py`
- `tests/test_historical_data_catalog.py`
- `tests/test_historical_data_fetch_plan.py`
- `tests/test_hygiene.py`
- `tests/test_import_upstox_instrument_master.py`
- `tests/test_kite_depth_ws_stability.py`
- `tests/test_live_indicator_readiness.py`
- `tests/test_market_data_index_quote_cache.py`
- `tests/test_market_feed_race_conditions.py`
- `tests/test_mean_reversion_failure_analysis.py`
- `tests/test_mean_reversion_historical_coverage_plan.py`
- `tests/test_mean_reversion_historical_data_catalog.py`
- `tests/test_mean_reversion_trade_ledger.py`
- `tests/test_mean_reversion_trade_ledger_audit.py`
- `tests/test_mean_reversion_vertical_slice.py`
- `tests/test_next_day_capture_contract.py`
- `tests/test_no_hardcoded_paths_repo_wide.py`
- `tests/test_opportunity_ranking.py`
- `tests/test_orchestrator_decision_event.py`
- `tests/test_orchestrator_depth_ws_startup.py`
- `tests/test_orchestrator_reports_finally.py`
- `tests/test_orchestrator_strategy_gate_once.py`
- `tests/test_phase2_strict_live_data_contract.py`
- `tests/test_phase6_eligibility_audit.py`
- `tests/test_phase6_shadow_candidates.py`
- `tests/test_pipeline_contracts.py`
- `tests/test_resolve_upstox_instrument_keys.py`
- `tests/test_simple_orb_phase_evidence_discovery.py`
- `tests/test_strategy_certification_pipeline.py`
- `tests/test_strategy_module_taxonomy_sync.py`
- `tests/test_strategy_registry.py`
- `tests/test_stress_replay_data_inventory_report.py`
- `tests/test_tick_data_collector.py`
- `tests/test_time_sanity_staleness.py`
- `tests/test_upstox_candidate_replay_data_preflight.py`
- `tests/test_upstox_candle_files_audit.py`
- `tests/test_upstox_data_recovery_pipeline.py`
- `tests/test_upstox_historical_availability_probe.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/auth/test_auth_safety.py` | `PASS` | `test_reality_accepted` |
| `tests/config/test_mode_safety.py` | `PASS` | `test_reality_accepted` |
| `tests/core/test_candidate_scoring_hypothesis.py` | `PASS` | `test_reality_accepted` |
| `tests/core/test_feed_runtime_hypothesis.py` | `PASS` | `test_reality_accepted` |
| `tests/core/test_risk_engine_hypothesis.py` | `PASS` | `test_reality_accepted` |
| `tests/execution/test_feed_fallback_safety.py` | `PASS` | `test_reality_accepted` |
| `tests/test_batch_strategy_certification.py` | `PASS` | `test_reality_accepted` |
| `tests/test_blocked_certification_dataset_marker.py` | `PASS` | `test_reality_accepted` |
| `tests/test_candidate_generator_contract.py` | `PASS` | `test_reality_accepted` |
| `tests/test_candidate_generator_historical_audit.py` | `PASS` | `test_reality_accepted` |
| `tests/test_candidate_generator_replay_harness.py` | `PASS` | `test_reality_accepted` |
| `tests/test_candidate_replay_data_source_decision_report.py` | `PASS` | `test_reality_accepted` |
| `tests/test_candidate_safety.py` | `PASS` | `test_reality_accepted` |
| `tests/test_candidate_strategy_backtest.py` | `PASS` | `test_reality_accepted` |
| `tests/test_candidate_strategy_data_coverage.py` | `PASS` | `test_reality_accepted` |
| `tests/test_candidate_strategy_wfa.py` | `PASS` | `test_reality_accepted` |
| `tests/test_candidate_to_signal_adapter.py` | `PASS` | `test_reality_accepted` |
| `tests/test_decision_dag.py` | `PASS` | `test_reality_accepted` |
| `tests/test_diagnose_upstox_historical_access.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_state_engine.py` | `PASS` | `test_reality_accepted` |
| `tests/test_filtered_stress_replay_dataset_quality.py` | `PASS` | `test_reality_accepted` |
| `tests/test_historical_data_capability.py` | `PASS` | `test_reality_accepted` |
| `tests/test_historical_data_catalog.py` | `PASS` | `test_reality_accepted` |
| `tests/test_historical_data_fetch_plan.py` | `PASS` | `test_reality_accepted` |
| `tests/test_hygiene.py` | `PASS` | `test_reality_accepted` |
| `tests/test_import_upstox_instrument_master.py` | `PASS` | `test_reality_accepted` |
| `tests/test_kite_depth_ws_stability.py` | `PASS` | `test_reality_accepted` |
| `tests/test_live_indicator_readiness.py` | `PASS` | `test_reality_accepted` |
| `tests/test_market_data_index_quote_cache.py` | `PASS` | `test_reality_accepted` |
| `tests/test_market_feed_race_conditions.py` | `PASS` | `test_reality_accepted` |
| `tests/test_mean_reversion_failure_analysis.py` | `PASS` | `test_reality_accepted` |
| `tests/test_mean_reversion_historical_coverage_plan.py` | `PASS` | `test_reality_accepted` |
| `tests/test_mean_reversion_historical_data_catalog.py` | `PASS` | `test_reality_accepted` |
| `tests/test_mean_reversion_trade_ledger.py` | `PASS` | `test_reality_accepted` |
| `tests/test_mean_reversion_trade_ledger_audit.py` | `PASS` | `test_reality_accepted` |
| `tests/test_mean_reversion_vertical_slice.py` | `PASS` | `test_reality_accepted` |
| `tests/test_next_day_capture_contract.py` | `PASS` | `test_reality_accepted` |
| `tests/test_no_hardcoded_paths_repo_wide.py` | `PASS` | `test_reality_accepted` |
| `tests/test_opportunity_ranking.py` | `PASS` | `test_reality_accepted` |
| `tests/test_orchestrator_decision_event.py` | `PASS` | `test_reality_accepted` |
| `tests/test_orchestrator_depth_ws_startup.py` | `PASS` | `test_reality_accepted` |
| `tests/test_orchestrator_reports_finally.py` | `PASS` | `test_reality_accepted` |
| `tests/test_orchestrator_strategy_gate_once.py` | `PASS` | `test_reality_accepted` |
| `tests/test_phase2_strict_live_data_contract.py` | `PASS` | `test_reality_accepted` |
| `tests/test_phase6_eligibility_audit.py` | `PASS` | `test_reality_accepted` |
| `tests/test_phase6_shadow_candidates.py` | `PASS` | `test_reality_accepted` |
| `tests/test_pipeline_contracts.py` | `PASS` | `test_reality_accepted` |
| `tests/test_resolve_upstox_instrument_keys.py` | `PASS` | `test_reality_accepted` |
| `tests/test_simple_orb_phase_evidence_discovery.py` | `PASS` | `test_reality_accepted` |
| `tests/test_strategy_certification_pipeline.py` | `PASS` | `test_reality_accepted` |
| `tests/test_strategy_module_taxonomy_sync.py` | `PASS` | `test_reality_accepted` |
| `tests/test_strategy_registry.py` | `PASS` | `test_reality_accepted` |
| `tests/test_stress_replay_data_inventory_report.py` | `PASS` | `test_reality_accepted` |
| `tests/test_tick_data_collector.py` | `PASS` | `test_reality_accepted` |
| `tests/test_time_sanity_staleness.py` | `PASS` | `test_reality_accepted` |
| `tests/test_upstox_candidate_replay_data_preflight.py` | `PASS` | `test_reality_accepted` |
| `tests/test_upstox_candle_files_audit.py` | `PASS` | `test_reality_accepted` |
| `tests/test_upstox_data_recovery_pipeline.py` | `PASS` | `test_reality_accepted` |
| `tests/test_upstox_historical_availability_probe.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `configs/candidate_strategy_validation_thresholds.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `configs/next_day_option_tick_capture_contract.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `configs/strategy_risk_contracts/MEAN_REVERSION_EXTENSION.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/advisory_schema.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/blocker_lifecycle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_finalization.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_pool_orchestrator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_to_signal_adapter.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/decision_dag.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed/runtime_store.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed_state_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/kite_depth_ws.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/movement_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/movement_regime.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/movement_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/opportunity_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/opportunity_ranking.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/pipeline_contracts.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/ranking_orchestrator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/recovery_state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/runtime_snapshot_producer.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/yaml_compat.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr638_audit_pipeline_contracts.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/data_contracts/next_day_option_tick_capture_contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/data_contracts/one_strategy_replay_after_clean_capture.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/runbooks/upstox_instrument_master_access.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/runbooks/upstox_token_safety.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/statistical_validation/01_data_inventory.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_design/MEAN_REVERSION_EXTENSION_V2_DESIGN.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_module_taxonomy.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/SIMPLE_ORB/01_pipeline_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/SIMPLE_ORB/02_registry.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/SIMPLE_ORB/03_truth.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/SIMPLE_ORB/04_outcomes.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/SIMPLE_ORB/05_statistics.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/SIMPLE_ORB/06_certification.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/SIMPLE_ORB/07_live_drift.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/SIMPLE_ORB/08_blockers.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/SIMPLE_ORB/09_limitations.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/SIMPLE_ORB/10_final_decision.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/01_loaded_registry.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/02_parameter_inventory.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/03_heuristic_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/04_indicator_inventory.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/05_dependency_graph.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/06_strategy_truth_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/08_control_flow_graphs.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/09_semantic_comparison.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/10_mathematical_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/11_hardened_strategy_truth_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_validation/MEAN_REVERSION_EXTENSION_V1_FAILED_BASELINE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_validation/MEAN_REVERSION_EXTENSION_V2_FAILED_BASELINE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `fix_all.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `fix_indent.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch2.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_base_execution_truth.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_context.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_context2.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_opp_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_opportunity_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_recovery.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_report.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_unsubscribe.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_watchdog.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `print_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `requirements.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `rewrite_watchdog.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `run_dbg.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/COMPRESSION_BREAKOUT/audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/COMPRESSION_BREAKOUT/candidate_replay_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/COMPRESSION_BREAKOUT/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/candidate_replay_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EVENT_VOLATILITY_EXPANSION/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EXHAUSTION_REVERSAL/audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EXHAUSTION_REVERSAL/candidate_replay_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/EXHAUSTION_REVERSAL/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/candidate_replay_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/FAILED_BREAKOUT_TRAP/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/LATE_DAY_MOMENTUM/audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/LATE_DAY_MOMENTUM/candidate_replay_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/LATE_DAY_MOMENTUM/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/blocker_outcome_replay.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/blocker_outcome_replay.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/historical_data_catalog.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/historical_data_catalog.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/lineage_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/lineage_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/missing_option_paths_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase6_shadow_candidate_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_10_accounting_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_11_parameter_discovery.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_11b_full_grid_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_11b_nested_parameter_discovery.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_11b_v2_full_grid_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_5_truth_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_5_truth_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_7_integrity_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_7_integrity_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_8_selection_quality_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_9_cohort_edge.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_pipeline_telemetry.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_v2_structural_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/pipeline_contract_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/pipeline_contract_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/pipeline_health_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/pipeline_health_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/ranking_safety_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/ranking_safety_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/simulation_metadata.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_availability_probe.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_availability_probe.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_candle_file_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_candle_file_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_access_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_access_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_import.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_master_import.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_resolution.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_resolution.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/NO_TRADE_CHOP/audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/NO_TRADE_CHOP/candidate_replay_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/NO_TRADE_CHOP/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/NO_TRADE_CHOP/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/NO_TRADE_CHOP/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/NO_TRADE_CHOP/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/NO_TRADE_CHOP/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/NO_TRADE_CHOP/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/candidate_replay_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_4_10_accounting_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_4_11b_v2_full_grid_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_4_5_truth_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_4_5_truth_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_4_7_integrity_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_4_7_integrity_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_4_opening_drive_structural_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_4_trade_ledger_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_4_v2_structural_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_DRIVE/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/candidate_replay_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPENING_RANGE_BREAKOUT/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPTION_PRESSURE/audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPTION_PRESSURE/candidate_replay_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPTION_PRESSURE/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPTION_PRESSURE/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPTION_PRESSURE/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPTION_PRESSURE/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPTION_PRESSURE/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/OPTION_PRESSURE/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/SIMPLE_ORB/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/SIMPLE_ORB/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/SIMPLE_ORB/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/SIMPLE_ORB/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/SIMPLE_ORB/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/SIMPLE_ORB/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/SIMPLE_ORB/simple_orb_phase_evidence_inventory.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/SIMPLE_ORB/simple_orb_phase_evidence_inventory.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/TREND_PULLBACK/audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/TREND_PULLBACK/candidate_replay_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/TREND_PULLBACK/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/TREND_PULLBACK/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/TREND_PULLBACK/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/TREND_PULLBACK/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/TREND_PULLBACK/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/TREND_PULLBACK/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/VWAP_RECLAIM/audit_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/VWAP_RECLAIM/candidate_replay_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/VWAP_RECLAIM/phase_1_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/VWAP_RECLAIM/phase_2_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/VWAP_RECLAIM/phase_3_5_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/VWAP_RECLAIM/phase_3_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/VWAP_RECLAIM/phase_4_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/VWAP_RECLAIM/phase_5_wfa_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/batch_certification_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/batch_certification_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/blocked_datasets.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/blocked_datasets.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/candidate_replay_batch_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/candidate_replay_batch_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/candidate_replay_data_source_decision_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/candidate_replay_data_source_decision_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/next_day_capture_contract_readiness.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/next_day_capture_contract_readiness.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/stress_replay_data_inventory_report.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/stress_replay_data_inventory_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_validation/stress_replay_resolved_option_token_index.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/upstox_instruments/complete.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/analyze_mean_reversion_failure.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/analyze_phase4_9_cohort_edge.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/analyze_strategy_live_shadow.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_candidate_generator_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_candidate_strategy_data_coverage.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_feed_negative_controls.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_historical_data_capability.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_mean_reversion_trade_ledger.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_opening_drive_structural.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_phase4_10_accounting.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_phase4_7_integrity.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_phase4_8_selection_quality.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_phase4_truth.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_phase4_v2_structural.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_phase6_eligibility.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_pipeline_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/audit_upstox_candle_files.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/catalog_historical_data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/catalog_mean_reversion_historical_data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/diagnose_upstox_historical_access.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/discover_simple_orb_phase_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/fetch_missing_strategy_data_upstox.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/fetch_upstox_historical_data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/generate_mean_reversion_trade_ledger.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/generate_opening_drive_trade_ledger.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/generate_pipeline_health_report.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/import_upstox_instrument_master.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/live_soak.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/live_soak_advanced.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/mark_blocked_certification_dataset.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/plan_historical_data_fetch.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/plan_mean_reversion_historical_coverage.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/preflight_upstox_candidate_replay_data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/probe_upstox_historical_availability.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/replay_blocker_outcomes.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/replay_candidate_generator_strategy.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/report_candidate_replay_data_sources.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/report_phase6_shadow_candidates.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/report_stress_replay_data_inventory.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/report_upstox_candidate_replay_data_capability.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/resolve_upstox_instrument_keys.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_batch_strategy_certification.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_candidate_generator_historical_audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_candidate_ranking_proof_pack.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_candidate_strategy_backtest.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_candidate_strategy_wfa.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_live_supervised.sh` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_mean_reversion_parameter_discovery.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_offline_feed_candidate_truth_proof_pack.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_opening_drive_parameter_discovery.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_option_data_quality_proof_pack.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_strategy_certification.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_strategy_certification_pipeline.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/tick_data_collector.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/validate_filtered_stress_replay_dataset.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/validate_mean_reversion_vertical_slice.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/validate_next_day_capture_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `sitecustomize.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/simple_orb.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/strategy_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/auth/test_auth_safety.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/config/test_mode_safety.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/core/test_candidate_scoring_hypothesis.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/core/test_feed_runtime_hypothesis.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/core/test_risk_engine_hypothesis.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/execution/test_feed_fallback_safety.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_batch_strategy_certification.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_blocked_certification_dataset_marker.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_generator_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_generator_historical_audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_generator_replay_harness.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_replay_data_source_decision_report.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_safety.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_strategy_backtest.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_strategy_data_coverage.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_strategy_wfa.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_to_signal_adapter.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_decision_dag.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_diagnose_upstox_historical_access.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_state_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_filtered_stress_replay_dataset_quality.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_historical_data_capability.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_historical_data_catalog.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_historical_data_fetch_plan.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_hygiene.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_import_upstox_instrument_master.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_kite_depth_ws_stability.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_live_indicator_readiness.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_market_data_index_quote_cache.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_market_feed_race_conditions.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_mean_reversion_failure_analysis.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_mean_reversion_historical_coverage_plan.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_mean_reversion_historical_data_catalog.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_mean_reversion_trade_ledger.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_mean_reversion_trade_ledger_audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_mean_reversion_vertical_slice.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_next_day_capture_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_no_hardcoded_paths_repo_wide.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_opportunity_ranking.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_orchestrator_decision_event.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_orchestrator_depth_ws_startup.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_orchestrator_reports_finally.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_orchestrator_strategy_gate_once.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_phase2_strict_live_data_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_phase6_eligibility_audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_phase6_shadow_candidates.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_pipeline_contracts.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_resolve_upstox_instrument_keys.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_simple_orb_phase_evidence_discovery.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_certification_pipeline.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_module_taxonomy_sync.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_stress_replay_data_inventory_report.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_tick_data_collector.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_time_sanity_staleness.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_upstox_candidate_replay_data_preflight.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_upstox_candle_files_audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_upstox_data_recovery_pipeline.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_upstox_historical_availability_probe.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/pr638_audit_pipeline_contracts.md` | `PASS` | `evidence_contract_satisfied` |
