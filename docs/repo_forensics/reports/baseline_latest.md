# Repo Forensics — Repo Map

## Scope Guard

- Static filesystem scan only.
- No TradeBot runtime modules imported.
- No broker calls.
- No live runtime execution.
- No product behavior changed.

## Inventory Summary

| Category | Count |
|---|---:|
| Total files | 1821 |
| Python files | 1346 |
| Test files | 647 |
| Shell scripts | 22 |
| Dashboard files | 30 |
| Doc/text files | 98 |
| Runtime/evidence paths present | 2 |

## Required Entrypoints

| Path | Status | Evidence |
|---|---|---|
| `run_live.sh` | PASS | path_exists |
| `main.py` | PASS | path_exists |
| `dashboard/streamlit_app.py` | PASS | path_exists |

## Optional Entrypoints

| Path | Status | Evidence |
|---|---|---|
| `dashboard/streamlit_app_runtime.py` | PASS | path_exists |
| `premarket.py` | PASS | path_exists |
| `run_all.sh` | FAIL | path_missing |
| `scripts/run_paper_replay.py` | PASS | path_exists |

## Critical Modules

### runtime_startup

| Path | Status | Evidence |
|---|---|---|
| `run_live.sh` | PASS | path_exists |
| `main.py` | PASS | path_exists |
| `core/runtime_safety_boot_guard.py` | PASS | path_exists |
| `core/auth.py` | PASS | path_exists |
| `core/auth_health.py` | PASS | path_exists |
| `core/security_guard.py` | PASS | path_exists |
| `core/readiness_gate.py` | PASS | path_exists |
| `core/startup_recovery.py` | PASS | path_exists |
| `core/instance_lock.py` | PASS | path_exists |
| `core/session_guard.py` | PASS | path_exists |

### orchestration

| Path | Status | Evidence |
|---|---|---|
| `core/orchestrator.py` | PASS | path_exists |
| `core/orchestrator_parts/cycle.py` | PASS | path_exists |
| `core/orchestrator_parts/data.py` | PASS | path_exists |
| `core/orchestrator_parts/decisions.py` | PASS | path_exists |
| `core/orchestrator_parts/finalize.py` | PASS | path_exists |

### market_data

| Path | Status | Evidence |
|---|---|---|
| `core/market_data.py` | PASS | path_exists |
| `core/kite_depth_ws.py` | PASS | path_exists |
| `core/depth_store.py` | PASS | path_exists |
| `core/option_liquidity_cache.py` | PASS | path_exists |
| `core/quote_truth.py` | PASS | path_exists |
| `core/gates/quote_age_gate.py` | PASS | path_exists |

### candidates_and_ranking

| Path | Status | Evidence |
|---|---|---|
| `strategies/trade_builder.py` | PASS | path_exists |
| `core/engine_phase2_adapter.py` | PASS | path_exists |
| `core/v2_pipeline.py` | PASS | path_exists |
| `core/pro_strategy_pipeline.py` | PASS | path_exists |
| `core/opportunity_engine.py` | PASS | path_exists |
| `core/trade_scoring.py` | PASS | path_exists |
| `core/candidate_finalization.py` | PASS | path_exists |
| `core/candidate_soft_reject.py` | PASS | path_exists |
| `core/decision_builder.py` | PASS | path_exists |
| `core/decision_dag.py` | PASS | path_exists |

### risk_and_safety

| Path | Status | Evidence |
|---|---|---|
| `core/risk_engine.py` | PASS | path_exists |
| `core/execution_guard.py` | PASS | path_exists |
| `core/risk_halt.py` | PASS | path_exists |
| `core/risk_state.py` | PASS | path_exists |
| `core/portfolio_risk_allocator.py` | PASS | path_exists |
| `core/circuit_breaker.py` | PASS | path_exists |
| `core/decision_breakers.py` | PASS | path_exists |
| `core/slippage_guard.py` | PASS | path_exists |
| `core/slo_guard.py` | PASS | path_exists |

### execution_boundary

| Path | Status | Evidence |
|---|---|---|
| `core/execution_engine.py` | PASS | path_exists |
| `core/execution_router.py` | PASS | path_exists |
| `core/live_dry_run_broker_payload_gate.py` | PASS | path_exists |
| `core/broker_reconciliation_dry_run_proof.py` | PASS | path_exists |
| `core/kill_switch_risk_halt_dry_run_proof.py` | PASS | path_exists |
| `core/broker_truth_reconciler.py` | PASS | path_exists |
| `core/kite_client.py` | PASS | path_exists |

### evidence_and_dashboard

| Path | Status | Evidence |
|---|---|---|
| `core/events.py` | PASS | path_exists |
| `core/audit_log.py` | PASS | path_exists |
| `core/decision_logger.py` | PASS | path_exists |
| `core/decision_store.py` | PASS | path_exists |
| `core/runtime_health.py` | PASS | path_exists |
| `core/runtime_snapshot_producer.py` | PASS | path_exists |
| `core/runtime_snapshot_store.py` | PASS | path_exists |
| `core/observability/pipeline.py` | PASS | path_exists |
| `dashboard/streamlit_app.py` | PASS | path_exists |
| `dashboard/streamlit_app_runtime.py` | PASS | path_exists |

## Critical Module Caller Check

### runtime_startup

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `run_live.sh` | UNREFERENCED | 0 | 0 | no_static_references_found |
| `main.py` | PRODUCTION_REFERENCED | 160 | 13 | production_reference_found |
| `core/runtime_safety_boot_guard.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/auth.py` | PRODUCTION_REFERENCED | 15 | 3 | production_reference_found |
| `core/auth_health.py` | PRODUCTION_REFERENCED | 10 | 5 | production_reference_found |
| `core/security_guard.py` | PRODUCTION_REFERENCED | 6 | 1 | production_reference_found |
| `core/readiness_gate.py` | PRODUCTION_REFERENCED | 6 | 6 | production_reference_found |
| `core/startup_recovery.py` | TEST_ONLY | 0 | 1 | test_references_only |
| `core/instance_lock.py` | PRODUCTION_REFERENCED | 3 | 1 | production_reference_found |
| `core/session_guard.py` | PRODUCTION_REFERENCED | 2 | 1 | production_reference_found |

### orchestration

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `core/orchestrator.py` | PRODUCTION_REFERENCED | 3 | 34 | production_reference_found |
| `core/orchestrator_parts/cycle.py` | PRODUCTION_REFERENCED | 2 | 1 | production_reference_found |
| `core/orchestrator_parts/data.py` | PRODUCTION_REFERENCED | 82 | 15 | production_reference_found |
| `core/orchestrator_parts/decisions.py` | PRODUCTION_REFERENCED | 12 | 5 | production_reference_found |
| `core/orchestrator_parts/finalize.py` | PRODUCTION_REFERENCED | 1 | 0 | production_reference_found |

### market_data

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `core/market_data.py` | PRODUCTION_REFERENCED | 59 | 42 | production_reference_found |
| `core/kite_depth_ws.py` | PRODUCTION_REFERENCED | 9 | 15 | production_reference_found |
| `core/depth_store.py` | PRODUCTION_REFERENCED | 10 | 1 | production_reference_found |
| `core/option_liquidity_cache.py` | PRODUCTION_REFERENCED | 4 | 4 | production_reference_found |
| `core/quote_truth.py` | PRODUCTION_REFERENCED | 4 | 1 | production_reference_found |
| `core/gates/quote_age_gate.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |

### candidates_and_ranking

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `strategies/trade_builder.py` | PRODUCTION_REFERENCED | 9 | 42 | production_reference_found |
| `core/engine_phase2_adapter.py` | PRODUCTION_REFERENCED | 1 | 3 | production_reference_found |
| `core/v2_pipeline.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/pro_strategy_pipeline.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/opportunity_engine.py` | PRODUCTION_REFERENCED | 3 | 6 | production_reference_found |
| `core/trade_scoring.py` | PRODUCTION_REFERENCED | 5 | 1 | production_reference_found |
| `core/candidate_finalization.py` | PRODUCTION_REFERENCED | 3 | 2 | production_reference_found |
| `core/candidate_soft_reject.py` | PRODUCTION_REFERENCED | 2 | 4 | production_reference_found |
| `core/decision_builder.py` | PRODUCTION_REFERENCED | 3 | 3 | production_reference_found |
| `core/decision_dag.py` | PRODUCTION_REFERENCED | 2 | 3 | production_reference_found |

### risk_and_safety

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `core/risk_engine.py` | PRODUCTION_REFERENCED | 6 | 6 | production_reference_found |
| `core/execution_guard.py` | PRODUCTION_REFERENCED | 3 | 4 | production_reference_found |
| `core/risk_halt.py` | PRODUCTION_REFERENCED | 14 | 13 | production_reference_found |
| `core/risk_state.py` | PRODUCTION_REFERENCED | 15 | 6 | production_reference_found |
| `core/portfolio_risk_allocator.py` | PRODUCTION_REFERENCED | 1 | 0 | production_reference_found |
| `core/circuit_breaker.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/decision_breakers.py` | PRODUCTION_REFERENCED | 2 | 2 | production_reference_found |
| `core/slippage_guard.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/slo_guard.py` | PRODUCTION_REFERENCED | 4 | 1 | production_reference_found |

### execution_boundary

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `core/execution_engine.py` | PRODUCTION_REFERENCED | 8 | 18 | production_reference_found |
| `core/execution_router.py` | PRODUCTION_REFERENCED | 2 | 6 | production_reference_found |
| `core/live_dry_run_broker_payload_gate.py` | PRODUCTION_REFERENCED | 1 | 3 | production_reference_found |
| `core/broker_reconciliation_dry_run_proof.py` | PRODUCTION_REFERENCED | 1 | 2 | production_reference_found |
| `core/kill_switch_risk_halt_dry_run_proof.py` | TEST_ONLY | 0 | 1 | test_references_only |
| `core/broker_truth_reconciler.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/kite_client.py` | PRODUCTION_REFERENCED | 43 | 23 | production_reference_found |

### evidence_and_dashboard

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `core/events.py` | PRODUCTION_REFERENCED | 62 | 36 | production_reference_found |
| `core/audit_log.py` | PRODUCTION_REFERENCED | 12 | 1 | production_reference_found |
| `core/decision_logger.py` | PRODUCTION_REFERENCED | 3 | 3 | production_reference_found |
| `core/decision_store.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/runtime_health.py` | PRODUCTION_REFERENCED | 5 | 6 | production_reference_found |
| `core/runtime_snapshot_producer.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/runtime_snapshot_store.py` | PRODUCTION_REFERENCED | 6 | 1 | production_reference_found |
| `core/observability/pipeline.py` | PRODUCTION_REFERENCED | 5 | 1 | production_reference_found |
| `dashboard/streamlit_app.py` | TEST_ONLY | 0 | 1 | test_references_only |
| `dashboard/streamlit_app_runtime.py` | TEST_ONLY | 0 | 21 | test_references_only |

## Runtime Wiring

### live_startup

| Step | Status | Evidence |
|---|---|---|
| `run_live.sh` | PASS | file_exists:run_live.sh |
| `main.py` | PASS | file_exists:main.py |
| `core.runtime_safety_boot_guard.enforce_runtime_boot_safety` | FAIL | module_file_missing:core/runtime_safety_boot_guard/enforce_runtime_boot_safety.py |
| `core.auth.validate_kite_startup_credentials` | FAIL | module_file_missing:core/auth/validate_kite_startup_credentials.py |
| `core.readiness_gate.run_readiness_check` | FAIL | module_file_missing:core/readiness_gate/run_readiness_check.py |
| `core.orchestrator.Orchestrator` | FAIL | module_file_missing:core/orchestrator/Orchestrator.py |
| `core.orchestrator_parts.cycle.run_live_monitoring` | FAIL | module_file_missing:core/orchestrator_parts/cycle/run_live_monitoring.py |

### candidate_to_decision

| Step | Status | Evidence |
|---|---|---|
| `market_data` | PASS | reference_found |
| `strategy_signal` | PASS | reference_found |
| `candidate_generation` | PASS | reference_found |
| `data_quality_gate` | UNKNOWN | reference_not_proven |
| `candidate_finalization` | PASS | reference_found |
| `opportunity_scoring` | PASS | reference_found |
| `ranking` | PASS | reference_found |
| `no_trade_or_gatekeeper` | UNKNOWN | reference_not_proven |
| `risk_evaluation` | UNKNOWN | reference_not_proven |
| `execution_boundary` | PASS | reference_found |
| `review_queue_or_evidence` | UNKNOWN | reference_not_proven |

## Test Reality

| Class | Count |
|---|---:|
| EVIDENCE_CONTRACT | 260 |
| FAKE_CONFIDENCE | 130 |
| INTEGRATION_WIRING | 6 |
| RUNTIME_COMMAND | 17 |
| SAFETY_REGRESSION | 61 |
| SHAPE_ONLY | 7 |
| UNIT_BEHAVIOR | 115 |
| UNKNOWN | 11 |

### Flagged Test Files

| File | Class | Strength | Evidence | Risks |
|---|---|---|---|---|
| `testing/tests/generated/test_feature_engineering.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | fallback_adjacent |
| `testing/tests/generated/test_market_data_ingestion.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `testing/tests/generated/test_observability.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `testing/tests/generated/test_order_lifecycle.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `testing/tests/generated/test_performance_and_reliability.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `testing/tests/generated/test_risk_and_position_sizing.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `testing/tests/generated/test_security_and_compliance.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `testing/tests/generated/test_state_and_persistence.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `testing/tests/generated/test_strategy_logic_and_scoring.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | fallback_adjacent |
| `testing/tests/property/test_feature_builder_properties.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/analytics/test_confidence_calibration.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/analytics/test_config_delta.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | live_adjacent |
| `tests/analytics/test_daily_intel.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/analytics/test_feed_context_enrichment.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/analytics/test_store.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/core/test_execution_audit.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | fallback_adjacent |
| `tests/core/test_replay_harness.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/core/test_runtime_snapshot_store.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/golden/test_mvp_pipeline.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | mock_heavy, live_adjacent |
| `tests/option_backtest/test_exporter.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/option_backtest/test_loader.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/strategies/test_candidate_generation_relaxation.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/strategies/test_pro_strategy_engine_elite.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | mock_heavy |
| `tests/strategies/test_regime_specific_paths.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/test_adaptive_limit_pricing.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| truncated | INFO | n/a | remaining=116 | n/a |

## Safety Boundary

| Severity | Count |
|---|---:|
| CRITICAL | 16 |
| HIGH | 38 |
| MEDIUM | 0 |
| UNKNOWN | 0 |

### Flagged Safety Findings

| File | Severity | Boundary | Evidence | Line |
|---|---|---|---|---:|
| `core/broker_reconciliation_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate core.live_dry_run_broker_payload_gate.broker_payload_dry_run_approved | 13 |
| `core/kill_switch_risk_halt_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.broker_reconciliation_dry_run_proof core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_proven | 13 |
| `tests/test_broker_reconciliation_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.broker_reconciliation_dry_run_proof core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_blocked core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_proven core.broker_reconciliation_dry_run_proof.build_broker_reconciliation_dry_run_proof | 3 |
| `tests/test_broker_reconciliation_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report | 8 |
| `tests/test_kill_switch_risk_halt_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.broker_reconciliation_dry_run_proof core.broker_reconciliation_dry_run_proof.build_broker_reconciliation_dry_run_proof | 3 |
| `tests/test_kill_switch_risk_halt_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report | 9 |
| `tests/test_live_dry_run_broker_payload_gate.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate core.live_dry_run_broker_payload_gate.broker_payload_dry_run_approved core.live_dry_run_broker_payload_gate.broker_payload_dry_run_blocked core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report | 3 |
| `tests/test_ranked_pipeline_evidence.py` | CRITICAL | readonly_action_field | is_order_action=true |  |
| `tests/test_repo_forensics_safety_boundary.py` | CRITICAL | readonly_action_field | is_order_action=true |  |
| `tests/test_repo_forensics_safety_boundary.py` | CRITICAL | readonly_action_field | broker_api_called=true |  |
| `tools/repo_forensics/safety_boundary.py` | CRITICAL | forensics_runtime_import | forensics_references_runtime_module:core.kite_client |  |
| `tools/repo_forensics/safety_boundary.py` | CRITICAL | forensics_runtime_import | forensics_references_runtime_module:core.market_data |  |
| `tools/repo_forensics/safety_boundary.py` | CRITICAL | forensics_runtime_import | forensics_references_runtime_module:core.orchestrator |  |
| `tools/repo_forensics/safety_boundary.py` | CRITICAL | forensics_runtime_import | forensics_references_runtime_module:strategies.trade_builder |  |
| `tools/repo_forensics/safety_boundary.py` | CRITICAL | forensics_order_action | forensics_contains_order_action_marker |  |
| `tools/repo_forensics/test_reality.py` | CRITICAL | forensics_order_action | forensics_contains_order_action_marker |  |
| `core/broker_truth_reconciler.py` | HIGH | order_action_call | order_action_call:place_order | 408 |
| `core/execution_engine.py` | HIGH | order_action_call | order_action_call:place_order_fn | 638 |
| `core/health_scenarios.py` | HIGH | order_action_call | order_action_call:place_order | 47 |
| `core/kite_client.py` | HIGH | order_action_call | order_action_call:place_order | 397 |
| `core/kite_client.py` | HIGH | order_action_call | order_action_call:modify_order | 400 |
| `core/kite_client.py` | HIGH | order_action_call | order_action_call:cancel_order | 403 |
| `core/storage/snapshots.py` | HIGH | readonly_execution_import | execution_import_in_readonly_path:core.kite_client core.kite_client.kite_client | 215 |
| `dashboard/streamlit_app_runtime.py` | HIGH | readonly_execution_import | execution_import_in_readonly_path:core.kite_client core.kite_client.kite_client | 5328 |
| `dashboard/streamlit_app_runtime.py` | HIGH | readonly_execution_import | execution_import_in_readonly_path:core.kite_client core.kite_client.kite_client | 5342 |
| `dashboard/streamlit_app_runtime.py` | HIGH | readonly_execution_import | execution_import_in_readonly_path:core.kite_client core.kite_client.kite_client | 9218 |
| `dashboard/streamlit_app_runtime.py` | HIGH | readonly_execution_import | execution_import_in_readonly_path:core.execution_engine core.execution_engine.executionengine | 9655 |
| `dashboard/streamlit_app_runtime.py` | HIGH | readonly_execution_import | execution_import_in_readonly_path:core.kite_client core.kite_client.kite_client | 10317 |
| `tests/core/test_execution_plan_boundary.py` | HIGH | order_action_call | order_action_call:engine.place_order_from_plan | 61 |
| `tests/core/test_execution_plan_boundary.py` | HIGH | order_action_call | order_action_call:engine.place_order_from_plan | 81 |
| truncated | INFO | n/a | remaining=24 |  |

## Evidence Audit

Reviewed files: 30

| Severity | Count |
|---|---:|
| HIGH | 88 |
| MEDIUM | 4 |
| UNKNOWN | 0 |

### Flagged Evidence Findings

| File | Severity | Type | Evidence | Missing Fields |
|---|---|---|---|---|
| `runtime/analytics/2026-03-09/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:1 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-09/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:2 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:1 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:2 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:3 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:4 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:5 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:6 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:1 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:2 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:3 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:4 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:5 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:6 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:7 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:8 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:9 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:10 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:11 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:12 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:13 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:14 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:15 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:16 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:17 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:18 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:19 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:20 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:21 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | missing_required_fields:jsonl_line:22 | candidate_id, decision, reason, timestamp, is_order_action, broker_api_called, source |
| truncated | INFO | n/a | remaining=62 | n/a |

## Architecture Drift

| Severity | Count |
|---|---:|
| HIGH | 0 |
| MEDIUM | 1 |
| UNKNOWN | 5 |

### Flagged Architecture Drift

| Path | Severity | Type | Evidence |
|---|---|---|---|
| `core/risk_manager.py, strategies/risk_manager.py` | MEDIUM | duplicate_module_stem | stem=risk_manager count=2 |
| `dashboard/utils.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |
| `dashboard/ui/table_model.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |
| `dashboard/readers/__init__.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |
| `dashboard/readers/advisory_reader.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |
| `dashboard/readers/snapshot_reader.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |

## Runtime / Evidence Paths Present

- `runtime/analytics`
- `docs/agent_reviews`

## Top Manual Inspection Files

1. `run_live.sh`
2. `main.py`
3. `dashboard/streamlit_app.py`
4. `core/orchestrator.py`
5. `core/orchestrator_parts/cycle.py`
6. `core/orchestrator_parts/data.py`
7. `core/orchestrator_parts/decisions.py`
8. `core/orchestrator_parts/finalize.py`
9. `strategies/trade_builder.py`
10. `core/engine_phase2_adapter.py`

## Findings Summary

- Missing required entrypoints: 0
- Missing critical modules: 0
- Runtime flow failures: 5
- Runtime flow unknowns: 4
- Critical modules missing caller proof: 5
- Fake-confidence tests: 130
- Unknown test files: 11
- Safety critical findings: 16
- Safety high findings: 38
- Safety unknown findings: 0
- Evidence high findings: 88
- Evidence medium findings: 4
- Evidence unknown findings: 0
- Drift high findings: 0
- Drift medium findings: 1
- Drift unknown findings: 5

## Findings

- HIGH: runtime flow step failed `live_startup:core.runtime_safety_boot_guard.enforce_runtime_boot_safety` evidence=module_file_missing:core/runtime_safety_boot_guard/enforce_runtime_boot_safety.py
- HIGH: runtime flow step failed `live_startup:core.auth.validate_kite_startup_credentials` evidence=module_file_missing:core/auth/validate_kite_startup_credentials.py
- HIGH: runtime flow step failed `live_startup:core.readiness_gate.run_readiness_check` evidence=module_file_missing:core/readiness_gate/run_readiness_check.py
- HIGH: runtime flow step failed `live_startup:core.orchestrator.Orchestrator` evidence=module_file_missing:core/orchestrator/Orchestrator.py
- HIGH: runtime flow step failed `live_startup:core.orchestrator_parts.cycle.run_live_monitoring` evidence=module_file_missing:core/orchestrator_parts/cycle/run_live_monitoring.py
- UNKNOWN: runtime flow step unproven `candidate_to_decision:data_quality_gate` evidence=reference_not_proven
- UNKNOWN: runtime flow step unproven `candidate_to_decision:no_trade_or_gatekeeper` evidence=reference_not_proven
- UNKNOWN: runtime flow step unproven `candidate_to_decision:risk_evaluation` evidence=reference_not_proven
- UNKNOWN: runtime flow step unproven `candidate_to_decision:review_queue_or_evidence` evidence=reference_not_proven
- HIGH: critical module has test-only caller proof `core/startup_recovery.py` group=runtime_startup
- HIGH: critical module has test-only caller proof `core/kill_switch_risk_halt_dry_run_proof.py` group=execution_boundary
- HIGH: critical module has test-only caller proof `dashboard/streamlit_app.py` group=evidence_and_dashboard
- HIGH: critical module has test-only caller proof `dashboard/streamlit_app_runtime.py` group=evidence_and_dashboard
- UNKNOWN: critical module has no static caller proof `run_live.sh` group=runtime_startup
- MEDIUM: fake-confidence test signal `testing/tests/generated/test_feature_engineering.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `testing/tests/generated/test_market_data_ingestion.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `testing/tests/generated/test_observability.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `testing/tests/generated/test_order_lifecycle.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `testing/tests/generated/test_performance_and_reliability.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `testing/tests/generated/test_risk_and_position_sizing.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `testing/tests/generated/test_security_and_compliance.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `testing/tests/generated/test_state_and_persistence.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `testing/tests/generated/test_strategy_logic_and_scoring.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `testing/tests/property/test_feature_builder_properties.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `tests/analytics/test_confidence_calibration.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `tests/analytics/test_config_delta.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `tests/analytics/test_daily_intel.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `tests/analytics/test_feed_context_enrichment.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `tests/analytics/test_store.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `tests/core/test_execution_audit.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `tests/core/test_replay_harness.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `tests/core/test_runtime_snapshot_store.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `tests/golden/test_mvp_pipeline.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal `tests/option_backtest/test_exporter.py` evidence=fake_confidence_marker
- MEDIUM: fake-confidence test signal truncated count=110
- CRITICAL: safety boundary `core/broker_reconciliation_dry_run_proof.py:13` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate core.live_dry_run_broker_payload_gate.broker_payload_dry_run_approved
- CRITICAL: safety boundary `core/kill_switch_risk_halt_dry_run_proof.py:13` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.broker_reconciliation_dry_run_proof core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_proven
- CRITICAL: safety boundary `tests/test_broker_reconciliation_dry_run_proof.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.broker_reconciliation_dry_run_proof core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_blocked core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_proven core.broker_reconciliation_dry_run_proof.build_broker_reconciliation_dry_run_proof
- CRITICAL: safety boundary `tests/test_broker_reconciliation_dry_run_proof.py:8` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report
- CRITICAL: safety boundary `tests/test_kill_switch_risk_halt_dry_run_proof.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.broker_reconciliation_dry_run_proof core.broker_reconciliation_dry_run_proof.build_broker_reconciliation_dry_run_proof
- CRITICAL: safety boundary `tests/test_kill_switch_risk_halt_dry_run_proof.py:9` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report
- CRITICAL: safety boundary `tests/test_live_dry_run_broker_payload_gate.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate core.live_dry_run_broker_payload_gate.broker_payload_dry_run_approved core.live_dry_run_broker_payload_gate.broker_payload_dry_run_blocked core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report
- CRITICAL: safety boundary `tests/test_ranked_pipeline_evidence.py` boundary=readonly_action_field evidence=is_order_action=true
- CRITICAL: safety boundary `tests/test_repo_forensics_safety_boundary.py` boundary=readonly_action_field evidence=is_order_action=true
- CRITICAL: safety boundary `tests/test_repo_forensics_safety_boundary.py` boundary=readonly_action_field evidence=broker_api_called=true
- CRITICAL: safety boundary `tools/repo_forensics/safety_boundary.py` boundary=forensics_runtime_import evidence=forensics_references_runtime_module:core.kite_client
- CRITICAL: safety boundary `tools/repo_forensics/safety_boundary.py` boundary=forensics_runtime_import evidence=forensics_references_runtime_module:core.market_data
- CRITICAL: safety boundary `tools/repo_forensics/safety_boundary.py` boundary=forensics_runtime_import evidence=forensics_references_runtime_module:core.orchestrator
- CRITICAL: safety boundary `tools/repo_forensics/safety_boundary.py` boundary=forensics_runtime_import evidence=forensics_references_runtime_module:strategies.trade_builder
- CRITICAL: safety boundary `tools/repo_forensics/safety_boundary.py` boundary=forensics_order_action evidence=forensics_contains_order_action_marker
- CRITICAL: safety boundary `tools/repo_forensics/test_reality.py` boundary=forensics_order_action evidence=forensics_contains_order_action_marker
- HIGH: safety boundary `core/broker_truth_reconciler.py:408` boundary=order_action_call evidence=order_action_call:place_order
- HIGH: safety boundary `core/execution_engine.py:638` boundary=order_action_call evidence=order_action_call:place_order_fn
- HIGH: safety boundary `core/health_scenarios.py:47` boundary=order_action_call evidence=order_action_call:place_order
- HIGH: safety boundary `core/kite_client.py:397` boundary=order_action_call evidence=order_action_call:place_order
- HIGH: safety boundary `core/kite_client.py:400` boundary=order_action_call evidence=order_action_call:modify_order
- HIGH: safety boundary `core/kite_client.py:403` boundary=order_action_call evidence=order_action_call:cancel_order
- HIGH: safety boundary `core/storage/snapshots.py:215` boundary=readonly_execution_import evidence=execution_import_in_readonly_path:core.kite_client core.kite_client.kite_client
- HIGH: safety boundary `dashboard/streamlit_app_runtime.py:5328` boundary=readonly_execution_import evidence=execution_import_in_readonly_path:core.kite_client core.kite_client.kite_client
- HIGH: safety boundary `dashboard/streamlit_app_runtime.py:5342` boundary=readonly_execution_import evidence=execution_import_in_readonly_path:core.kite_client core.kite_client.kite_client
- HIGH: safety boundary `dashboard/streamlit_app_runtime.py:9218` boundary=readonly_execution_import evidence=execution_import_in_readonly_path:core.kite_client core.kite_client.kite_client
- HIGH: safety boundary `dashboard/streamlit_app_runtime.py:9655` boundary=readonly_execution_import evidence=execution_import_in_readonly_path:core.execution_engine core.execution_engine.executionengine
- HIGH: safety boundary `dashboard/streamlit_app_runtime.py:10317` boundary=readonly_execution_import evidence=execution_import_in_readonly_path:core.kite_client core.kite_client.kite_client
- HIGH: safety boundary `tests/core/test_execution_plan_boundary.py:61` boundary=order_action_call evidence=order_action_call:engine.place_order_from_plan
- HIGH: safety boundary `tests/core/test_execution_plan_boundary.py:81` boundary=order_action_call evidence=order_action_call:engine.place_order_from_plan
- HIGH: safety findings truncated count=24
- HIGH: evidence `runtime/analytics/2026-03-09/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:1 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-09/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:2 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:1 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:2 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:3 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:4 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:5 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:6 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:1 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:2 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:3 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:4 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:5 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:6 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:7 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:8 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:9 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:10 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:11 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:12 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:13 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:14 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:15 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:16 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:17 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:18 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:19 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:20 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:21 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=missing_required_fields:jsonl_line:22 missing=candidate_id,decision,reason,timestamp,is_order_action,broker_api_called,source
- MEDIUM: evidence findings truncated count=62
- MEDIUM: architecture drift `core/risk_manager.py, strategies/risk_manager.py` type=duplicate_module_stem evidence=stem=risk_manager count=2
- UNKNOWN: architecture drift `dashboard/utils.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference
- UNKNOWN: architecture drift `dashboard/ui/table_model.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference
- UNKNOWN: architecture drift `dashboard/readers/__init__.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference
- UNKNOWN: architecture drift `dashboard/readers/advisory_reader.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference
- UNKNOWN: architecture drift `dashboard/readers/snapshot_reader.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference

## Verdict

FAIL — configured paths, runtime flow, caller proof, safety, evidence, or architecture drift failed.
