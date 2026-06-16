# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `38`
- total_findings: `51`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `11` | `0` |  |
| `cerberus` | `PASS` | `0` | `38` | `0` |  |
| `evidence` | `PASS` | `0` | `2` | `0` |  |

## Changed Paths

- `AGENTS.md`
- `core/_engine_phase2_adapter_base.py`
- `core/auto_retrain.py`
- `core/events.py`
- `core/execution/entry_pricer.py`
- `core/execution/execution_guard.py`
- `core/feed_debug.py`
- `core/feed_runtime.py`
- `core/feed_supervisor.py`
- `core/feed_truth_state.py`
- `core/greeks.py`
- `core/kite_depth_ws.py`
- `core/market_data.py`
- `core/market_snapshot_store.py`
- `core/orchestrator.py`
- `core/orchestrator_parts/cycle.py`
- `core/recovery_state_machine.py`
- `core/runtime_candidate_handoff.py`
- `core/runtime_health.py`
- `core/runtime_strategy_no_qualified_reasons.py`
- `core/tick_store.py`
- `docs/agent_reviews/fix-pr-562.md`
- `docs/agent_reviews/pr-591-feed-stability.md`
- `run_live.sh`
- `scripts/qa/audit_elite_e2e_coverage.py`
- `scripts/qa/score_qa_confidence.py`
- `strategies/trade_builder.py`
- `tests/behavior/execution/test_execution_guard_no_room_for_error.py`
- `tests/behavior/feed/test_feed_runtime_recovery_truth.py`
- `tests/behavior/feed/test_feed_truth_no_room_for_error_matrix.py`
- `tests/integration/test_feed_truth_to_candidate_pipeline.py`
- `tests/regression/test_execution_guard_truth_no_regression.py`
- `tests/test_auto_retrain_gates.py`
- `tests/test_execution_guard.py`
- `tests/test_feed_debug_runtime_store.py`
- `tests/test_feed_runtime_state_machine.py`
- `tests/test_recovery_state_machine.py`
- `tests/test_top_opportunities_row_classification_fields.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/behavior/execution/test_execution_guard_no_room_for_error.py` | `PASS` | `test_reality_accepted` |
| `tests/behavior/feed/test_feed_runtime_recovery_truth.py` | `PASS` | `test_reality_accepted` |
| `tests/behavior/feed/test_feed_truth_no_room_for_error_matrix.py` | `PASS` | `test_reality_accepted` |
| `tests/integration/test_feed_truth_to_candidate_pipeline.py` | `PASS` | `test_reality_accepted` |
| `tests/regression/test_execution_guard_truth_no_regression.py` | `PASS` | `test_reality_accepted` |
| `tests/test_auto_retrain_gates.py` | `PASS` | `test_reality_accepted` |
| `tests/test_execution_guard.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_debug_runtime_store.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_runtime_state_machine.py` | `PASS` | `test_reality_accepted` |
| `tests/test_recovery_state_machine.py` | `PASS` | `test_reality_accepted` |
| `tests/test_top_opportunities_row_classification_fields.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `AGENTS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/_engine_phase2_adapter_base.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/auto_retrain.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/events.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/execution/entry_pricer.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/execution/execution_guard.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed_debug.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed_runtime.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed_supervisor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed_truth_state.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/greeks.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/kite_depth_ws.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/market_data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/market_snapshot_store.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator_parts/cycle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/recovery_state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/runtime_candidate_handoff.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/runtime_health.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/runtime_strategy_no_qualified_reasons.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/tick_store.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/fix-pr-562.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr-591-feed-stability.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `run_live.sh` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/qa/audit_elite_e2e_coverage.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/qa/score_qa_confidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/trade_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/behavior/execution/test_execution_guard_no_room_for_error.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/behavior/feed/test_feed_runtime_recovery_truth.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/behavior/feed/test_feed_truth_no_room_for_error_matrix.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/integration/test_feed_truth_to_candidate_pipeline.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/regression/test_execution_guard_truth_no_regression.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_auto_retrain_gates.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_execution_guard.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_debug_runtime_store.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_runtime_state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_recovery_state_machine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_top_opportunities_row_classification_fields.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/fix-pr-562.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr-591-feed-stability.md` | `PASS` | `evidence_contract_satisfied` |
