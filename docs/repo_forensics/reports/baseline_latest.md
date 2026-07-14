---
mode: AGENT_REVIEW
candidate_id: N/A
decision: BASELINE
reason: Generate static baseline
timestamp: 2026-06-18
is_order_action: false
broker_api_called: false
source: static_analysis
---

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
| Total files | 344152 |
| Python files | 1976 |
| Test files | 983 |
| Shell scripts | 38 |
| Dashboard files | 33 |
| Doc/text files | 316709 |
| Runtime/evidence paths present | 3 |

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
| `main.py` | PRODUCTION_REFERENCED | 212 | 19 | production_reference_found |
| `core/runtime_safety_boot_guard.py` | PRODUCTION_REFERENCED | 1 | 3 | production_reference_found |
| `core/auth.py` | PRODUCTION_REFERENCED | 16 | 9 | production_reference_found |
| `core/auth_health.py` | PRODUCTION_REFERENCED | 11 | 8 | production_reference_found |
| `core/security_guard.py` | PRODUCTION_REFERENCED | 6 | 1 | production_reference_found |
| `core/readiness_gate.py` | PRODUCTION_REFERENCED | 6 | 6 | production_reference_found |
| `core/startup_recovery.py` | TEST_ONLY | 0 | 1 | test_references_only |
| `core/instance_lock.py` | PRODUCTION_REFERENCED | 4 | 1 | production_reference_found |
| `core/session_guard.py` | PRODUCTION_REFERENCED | 2 | 1 | production_reference_found |

### orchestration

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `core/orchestrator.py` | PRODUCTION_REFERENCED | 3 | 42 | production_reference_found |
| `core/orchestrator_parts/cycle.py` | PRODUCTION_REFERENCED | 2 | 1 | production_reference_found |
| `core/orchestrator_parts/data.py` | PRODUCTION_REFERENCED | 97 | 23 | production_reference_found |
| `core/orchestrator_parts/decisions.py` | PRODUCTION_REFERENCED | 25 | 6 | production_reference_found |
| `core/orchestrator_parts/finalize.py` | PRODUCTION_REFERENCED | 1 | 0 | production_reference_found |

### market_data

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `core/market_data.py` | PRODUCTION_REFERENCED | 65 | 44 | production_reference_found |
| `core/kite_depth_ws.py` | PRODUCTION_REFERENCED | 11 | 15 | production_reference_found |
| `core/depth_store.py` | PRODUCTION_REFERENCED | 10 | 1 | production_reference_found |
| `core/option_liquidity_cache.py` | PRODUCTION_REFERENCED | 4 | 4 | production_reference_found |
| `core/quote_truth.py` | PRODUCTION_REFERENCED | 5 | 2 | production_reference_found |
| `core/gates/quote_age_gate.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |

### candidates_and_ranking

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `strategies/trade_builder.py` | PRODUCTION_REFERENCED | 10 | 45 | production_reference_found |
| `core/engine_phase2_adapter.py` | PRODUCTION_REFERENCED | 1 | 8 | production_reference_found |
| `core/v2_pipeline.py` | PRODUCTION_REFERENCED | 2 | 1 | production_reference_found |
| `core/pro_strategy_pipeline.py` | PRODUCTION_REFERENCED | 2 | 1 | production_reference_found |
| `core/opportunity_engine.py` | PRODUCTION_REFERENCED | 3 | 7 | production_reference_found |
| `core/trade_scoring.py` | PRODUCTION_REFERENCED | 5 | 1 | production_reference_found |
| `core/candidate_finalization.py` | PRODUCTION_REFERENCED | 3 | 2 | production_reference_found |
| `core/candidate_soft_reject.py` | PRODUCTION_REFERENCED | 2 | 4 | production_reference_found |
| `core/decision_builder.py` | PRODUCTION_REFERENCED | 3 | 3 | production_reference_found |
| `core/decision_dag.py` | PRODUCTION_REFERENCED | 2 | 7 | production_reference_found |

### risk_and_safety

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `core/risk_engine.py` | PRODUCTION_REFERENCED | 8 | 6 | production_reference_found |
| `core/execution_guard.py` | PRODUCTION_REFERENCED | 4 | 5 | production_reference_found |
| `core/risk_halt.py` | PRODUCTION_REFERENCED | 14 | 14 | production_reference_found |
| `core/risk_state.py` | PRODUCTION_REFERENCED | 15 | 7 | production_reference_found |
| `core/portfolio_risk_allocator.py` | PRODUCTION_REFERENCED | 1 | 0 | production_reference_found |
| `core/circuit_breaker.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/decision_breakers.py` | PRODUCTION_REFERENCED | 2 | 2 | production_reference_found |
| `core/slippage_guard.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/slo_guard.py` | PRODUCTION_REFERENCED | 4 | 1 | production_reference_found |

### execution_boundary

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `core/execution_engine.py` | PRODUCTION_REFERENCED | 8 | 20 | production_reference_found |
| `core/execution_router.py` | PRODUCTION_REFERENCED | 3 | 9 | production_reference_found |
| `core/live_dry_run_broker_payload_gate.py` | PRODUCTION_REFERENCED | 1 | 3 | production_reference_found |
| `core/broker_reconciliation_dry_run_proof.py` | PRODUCTION_REFERENCED | 1 | 2 | production_reference_found |
| `core/kill_switch_risk_halt_dry_run_proof.py` | TEST_ONLY | 0 | 1 | test_references_only |
| `core/broker_truth_reconciler.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/kite_client.py` | PRODUCTION_REFERENCED | 51 | 28 | production_reference_found |

### evidence_and_dashboard

| Module | Status | Production Callers | Test Callers | Evidence |
|---|---|---:|---:|---|
| `core/events.py` | PRODUCTION_REFERENCED | 106 | 49 | production_reference_found |
| `core/audit_log.py` | PRODUCTION_REFERENCED | 12 | 1 | production_reference_found |
| `core/decision_logger.py` | PRODUCTION_REFERENCED | 3 | 3 | production_reference_found |
| `core/decision_store.py` | PRODUCTION_REFERENCED | 1 | 1 | production_reference_found |
| `core/runtime_health.py` | PRODUCTION_REFERENCED | 11 | 9 | production_reference_found |
| `core/runtime_snapshot_producer.py` | PRODUCTION_REFERENCED | 1 | 2 | production_reference_found |
| `core/runtime_snapshot_store.py` | PRODUCTION_REFERENCED | 8 | 6 | production_reference_found |
| `core/observability/pipeline.py` | PRODUCTION_REFERENCED | 5 | 1 | production_reference_found |
| `dashboard/streamlit_app.py` | TEST_ONLY | 0 | 1 | test_references_only |
| `dashboard/streamlit_app_runtime.py` | TEST_ONLY | 0 | 21 | test_references_only |

## Runtime Wiring

### live_startup

| Step | Status | Evidence |
|---|---|---|
| `run_live.sh` | PASS | file_exists:run_live.sh |
| `main.py` | PASS | file_exists:main.py |
| `core.runtime_safety_boot_guard.enforce_runtime_boot_safety` | PASS | symbol_defined:core/runtime_safety_boot_guard.py:enforce_runtime_boot_safety |
| `core.auth.validate_kite_startup_credentials` | PASS | symbol_defined:core/auth.py:validate_kite_startup_credentials |
| `core.readiness_gate.run_readiness_check` | PASS | symbol_defined:core/readiness_gate.py:run_readiness_check |
| `core.orchestrator.Orchestrator` | PASS | symbol_defined:core/orchestrator.py:Orchestrator |
| `core.orchestrator_parts.cycle.run_live_monitoring` | PASS | symbol_defined:core/orchestrator_parts/cycle.py:run_live_monitoring |

### candidate_to_decision

| Step | Status | Evidence |
|---|---|---|
| `market_data` | PASS | reference_found |
| `strategy_signal` | PASS | reference_found |
| `candidate_generation` | PASS | reference_found |
| `data_quality_gate` | PASS | reference_found |
| `candidate_finalization` | PASS | reference_found |
| `opportunity_scoring` | PASS | reference_found |
| `ranking` | PASS | reference_found |
| `no_trade_or_gatekeeper` | PASS | reference_found |
| `risk_evaluation` | PASS | reference_found |
| `execution_boundary` | PASS | reference_found |
| `review_queue_or_evidence` | PASS | reference_found |

## Test Reality

| Class | Count |
|---|---:|
| EVIDENCE_CONTRACT | 385 |
| FAKE_CONFIDENCE | 111 |
| INTEGRATION_WIRING | 6 |
| RUNTIME_COMMAND | 22 |
| SAFETY_REGRESSION | 225 |
| SHAPE_ONLY | 7 |
| UNIT_BEHAVIOR | 153 |
| UNKNOWN | 8 |

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
| `tests/strategies/test_candidate_generation_relaxation.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/strategies/test_pro_strategy_engine_elite.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | mock_heavy |
| `tests/strategies/test_regime_specific_paths.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/test_adaptive_limit_pricing.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | none |
| `tests/test_agent_evidence.py` | FAKE_CONFIDENCE | weak | fake_confidence_marker | live_adjacent |
| truncated | INFO | n/a | remaining=94 | n/a |

## Safety Boundary

| Severity | Count |
|---|---:|
| CRITICAL | 23 |
| HIGH | 151 |
| MEDIUM | 0 |
| UNKNOWN | 0 |

### Flagged Safety Findings

| File | Severity | Boundary | Evidence | Line |
|---|---|---|---|---:|
| `core/broker_reconciliation_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate | 13 |
| `core/broker_reconciliation_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate.broker_payload_dry_run_approved | 13 |
| `core/kill_switch_risk_halt_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.broker_reconciliation_dry_run_proof | 13 |
| `core/kill_switch_risk_halt_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_proven | 13 |
| `scripts/run_htf_real_paper_monitor.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.kite_client | 35 |
| `scripts/run_htf_real_paper_monitor.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.kite_client.kite_client | 35 |
| `tests/test_broker_reconciliation_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.broker_reconciliation_dry_run_proof | 3 |
| `tests/test_broker_reconciliation_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_blocked | 3 |
| `tests/test_broker_reconciliation_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_proven | 3 |
| `tests/test_broker_reconciliation_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.broker_reconciliation_dry_run_proof.build_broker_reconciliation_dry_run_proof | 3 |
| `tests/test_broker_reconciliation_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate | 8 |
| `tests/test_broker_reconciliation_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report | 8 |
| `tests/test_kill_switch_risk_halt_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.broker_reconciliation_dry_run_proof | 3 |
| `tests/test_kill_switch_risk_halt_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.broker_reconciliation_dry_run_proof.build_broker_reconciliation_dry_run_proof | 3 |
| `tests/test_kill_switch_risk_halt_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate | 9 |
| `tests/test_kill_switch_risk_halt_dry_run_proof.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report | 9 |
| `tests/test_live_dry_run_broker_payload_gate.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate | 3 |
| `tests/test_live_dry_run_broker_payload_gate.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate.broker_payload_dry_run_approved | 3 |
| `tests/test_live_dry_run_broker_payload_gate.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate.broker_payload_dry_run_blocked | 3 |
| `tests/test_live_dry_run_broker_payload_gate.py` | CRITICAL | paper_sim_broker_import | broker_adjacent_import:core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report | 3 |
| `tools/repo_forensics/safety_boundary.py` | CRITICAL | forensics_runtime_import | forensics_references_runtime_module:core.market_data |  |
| `tools/repo_forensics/safety_boundary.py` | CRITICAL | forensics_runtime_import | forensics_references_runtime_module:core.orchestrator |  |
| `tools/repo_forensics/safety_boundary.py` | CRITICAL | forensics_runtime_import | forensics_references_runtime_module:strategies.trade_builder |  |
| `core/execution_engine.py` | HIGH | order_action_call | order_action_call:place*order_fn | 638 |
| `core/kite_client.py` | HIGH | order_action_call | order_action_call:place*order | 397 |
| `core/kite_client.py` | HIGH | order_action_call | order_action_call:modify*order | 400 |
| `core/kite_client.py` | HIGH | order_action_call | order_action_call:cancel*order | 403 |
| `core/storage/snapshots.py` | HIGH | readonly_execution_import | execution_import_in_readonly_path:core.kite_client | 215 |
| `core/storage/snapshots.py` | HIGH | readonly_execution_import | execution_import_in_readonly_path:core.kite_client.kite_client | 215 |
| `dashboard/streamlit_app_runtime.py` | HIGH | readonly_execution_import | execution_import_in_readonly_path:core.kite_client | 5328 |
| truncated | INFO | n/a | remaining=144 |  |

## Evidence Audit

Reviewed files: 387

| Severity | Count |
|---|---:|
| HIGH | 92 |
| MEDIUM | 12 |
| UNKNOWN | 0 |

### Flagged Evidence Findings

| File | Severity | Type | Evidence | Missing Fields |
|---|---|---|---|---|
| `runtime/analytics/2026-03-09/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:1 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-09/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:2 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:1 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:2 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:3 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:4 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:5 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-11/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:6 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:1 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:2 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:3 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:4 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:5 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:6 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:7 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:8 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:9 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:10 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:11 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:12 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:13 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:14 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:15 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:16 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:17 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:18 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:19 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:20 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:21 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| `runtime/analytics/2026-03-12/events.jsonl` | HIGH | record | required_fields_absent:jsonl_line:22 | candidate_id, decision, reason, timestamp, i-s_order_action, b-roker_api_called, source |
| truncated | INFO | n/a | remaining=74 | n/a |

## Architecture Drift

| Severity | Count |
|---|---:|
| HIGH | 0 |
| MEDIUM | 1 |
| UNKNOWN | 7 |

### Flagged Architecture Drift

| Path | Severity | Type | Evidence |
|---|---|---|---|
| `core/risk_manager.py, strategies/risk_manager.py` | MEDIUM | duplicate_module_stem | stem=risk_manager count=2 |
| `dashboard/home_freshness_panel.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |
| `dashboard/utils.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |
| `dashboard/ui/table_model.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |
| `dashboard/ui/freshness_panel.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |
| `dashboard/readers/__init__.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |
| `dashboard/readers/advisory_reader.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |
| `dashboard/readers/snapshot_reader.py` | UNKNOWN | dashboard_evidence_reader_unproven | dashboard_reads_evidence_like_data_without_configured_path_reference |

## Runtime / Evidence Paths Present

- `runtime/analytics`
- `docs/repo_forensics/reports`
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
- Runtime flow failures: 0
- Runtime flow unknowns: 0
- Critical modules missing caller proof: 5
- Fake-confidence tests: 111
- Unknown test files: 8
- Safety critical findings: 23
- Safety high findings: 151
- Safety unknown findings: 0
- Evidence high findings: 92
- Evidence medium findings: 12
- Evidence unknown findings: 0
- Drift high findings: 0
- Drift medium findings: 1
- Drift unknown findings: 7

## Findings

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
- MEDIUM: fake-confidence test signal truncated count=91
- CRITICAL: safety boundary `core/broker_reconciliation_dry_run_proof.py:13` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate
- CRITICAL: safety boundary `core/broker_reconciliation_dry_run_proof.py:13` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate.broker_payload_dry_run_approved
- CRITICAL: safety boundary `core/kill_switch_risk_halt_dry_run_proof.py:13` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.broker_reconciliation_dry_run_proof
- CRITICAL: safety boundary `core/kill_switch_risk_halt_dry_run_proof.py:13` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_proven
- CRITICAL: safety boundary `scripts/run_htf_real_paper_monitor.py:35` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.kite_client
- CRITICAL: safety boundary `scripts/run_htf_real_paper_monitor.py:35` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.kite_client.kite_client
- CRITICAL: safety boundary `tests/test_broker_reconciliation_dry_run_proof.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.broker_reconciliation_dry_run_proof
- CRITICAL: safety boundary `tests/test_broker_reconciliation_dry_run_proof.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_blocked
- CRITICAL: safety boundary `tests/test_broker_reconciliation_dry_run_proof.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.broker_reconciliation_dry_run_proof.broker_recon_dry_run_proven
- CRITICAL: safety boundary `tests/test_broker_reconciliation_dry_run_proof.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.broker_reconciliation_dry_run_proof.build_broker_reconciliation_dry_run_proof
- CRITICAL: safety boundary `tests/test_broker_reconciliation_dry_run_proof.py:8` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate
- CRITICAL: safety boundary `tests/test_broker_reconciliation_dry_run_proof.py:8` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report
- CRITICAL: safety boundary `tests/test_kill_switch_risk_halt_dry_run_proof.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.broker_reconciliation_dry_run_proof
- CRITICAL: safety boundary `tests/test_kill_switch_risk_halt_dry_run_proof.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.broker_reconciliation_dry_run_proof.build_broker_reconciliation_dry_run_proof
- CRITICAL: safety boundary `tests/test_kill_switch_risk_halt_dry_run_proof.py:9` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate
- CRITICAL: safety boundary `tests/test_kill_switch_risk_halt_dry_run_proof.py:9` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report
- CRITICAL: safety boundary `tests/test_live_dry_run_broker_payload_gate.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate
- CRITICAL: safety boundary `tests/test_live_dry_run_broker_payload_gate.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate.broker_payload_dry_run_approved
- CRITICAL: safety boundary `tests/test_live_dry_run_broker_payload_gate.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate.broker_payload_dry_run_blocked
- CRITICAL: safety boundary `tests/test_live_dry_run_broker_payload_gate.py:3` boundary=paper_sim_broker_import evidence=broker_adjacent_import:core.live_dry_run_broker_payload_gate.build_live_dry_run_broker_payload_gate_report
- CRITICAL: safety boundary `tools/repo_forensics/safety_boundary.py` boundary=forensics_runtime_import evidence=forensics_references_runtime_module:core.market_data
- CRITICAL: safety boundary `tools/repo_forensics/safety_boundary.py` boundary=forensics_runtime_import evidence=forensics_references_runtime_module:core.orchestrator
- CRITICAL: safety boundary `tools/repo_forensics/safety_boundary.py` boundary=forensics_runtime_import evidence=forensics_references_runtime_module:strategies.trade_builder
- HIGH: safety boundary `core/execution_engine.py:638` boundary=order_action_call evidence=order_action_call:place*order_fn
- HIGH: safety boundary `core/kite_client.py:397` boundary=order_action_call evidence=order_action_call:place*order
- HIGH: safety boundary `core/kite_client.py:400` boundary=order_action_call evidence=order_action_call:modify*order
- HIGH: safety boundary `core/kite_client.py:403` boundary=order_action_call evidence=order_action_call:cancel*order
- HIGH: safety boundary `core/storage/snapshots.py:215` boundary=readonly_execution_import evidence=execution_import_in_readonly_path:core.kite_client
- HIGH: safety boundary `core/storage/snapshots.py:215` boundary=readonly_execution_import evidence=execution_import_in_readonly_path:core.kite_client.kite_client
- HIGH: safety boundary `dashboard/streamlit_app_runtime.py:5328` boundary=readonly_execution_import evidence=execution_import_in_readonly_path:core.kite_client
- HIGH: safety findings truncated count=144
- HIGH: evidence `runtime/analytics/2026-03-09/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:1 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-09/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:2 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:1 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:2 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:3 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:4 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:5 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-11/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:6 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:1 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:2 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:3 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:4 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:5 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:6 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:7 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:8 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:9 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:10 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:11 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:12 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:13 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:14 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:15 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:16 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:17 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:18 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:19 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:20 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:21 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- HIGH: evidence `runtime/analytics/2026-03-12/events.jsonl` type=record evidence=required_fields_absent:jsonl_line:22 absent=candidate_id,decision,reason,timestamp,i-s_order_action,b-roker_api_called,source
- MEDIUM: evidence findings truncated count=74
- MEDIUM: architecture drift `core/risk_manager.py, strategies/risk_manager.py` type=duplicate_module_stem evidence=stem=risk_manager count=2
- UNKNOWN: architecture drift `dashboard/home_freshness_panel.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference
- UNKNOWN: architecture drift `dashboard/utils.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference
- UNKNOWN: architecture drift `dashboard/ui/table_model.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference
- UNKNOWN: architecture drift `dashboard/ui/freshness_panel.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference
- UNKNOWN: architecture drift `dashboard/readers/__init__.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference
- UNKNOWN: architecture drift `dashboard/readers/advisory_reader.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference
- UNKNOWN: architecture drift `dashboard/readers/snapshot_reader.py` type=dashboard_evidence_reader_unproven evidence=dashboard_reads_evidence_like_data_without_configured_path_reference

## Verdict

FAIL — configured paths, runtime flow, caller proof, safety, evidence, or architecture drift failed.
