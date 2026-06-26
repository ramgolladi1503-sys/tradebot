# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `85`
- total_findings: `103`
- total_blocks: `1`
- exit_code: `1`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `BLOCK` | `1` | `19` | `1` |  |
| `cerberus` | `PASS` | `0` | `83` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `.pr_message`
- `candidate_decisions.jsonl`
- `changed.txt`
- `changed_paths.txt`
- `check_chain.py`
- `check_tokens.py`
- `code-excellence-gate-reports/changed_paths.txt`
- `code-excellence-gate-reports/unified_agent_elite_latest.md`
- `code-excellence-gate-reports/unified_ce_gate_latest.md`
- `config/config.py`
- `core/adaptive_risk.py`
- `core/candidate_ranking.py`
- `core/candidate_scoring.py`
- `core/data_quality.py`
- `core/decision_dag.py`
- `core/engine_phase2_adapter.py`
- `core/entropy_contract.py`
- `core/eod_no_trade_evidence.py`
- `core/feed/runtime_store.py`
- `core/feed_restart_policy.py`
- `core/feed_snapshot_reader.py`
- `core/feed_snapshot_writer.py`
- `core/feed_state_engine.py`
- `core/feed_state_model.py`
- `core/gate_status_log.py`
- `core/market_data.py`
- `core/orchestrator.py`
- `core/orchestrator_parts/decisions.py`
- `core/regime_entropy_gate.py`
- `core/regime_prob_model.py`
- `core/risk_state.py`
- `core/strategy_requirements.py`
- `dashboard/streamlit_app_runtime.py`
- `docs/agent_reviews/regime_entropy_truth_contract.md`
- `docs/code_excellence/reports/changed_paths.txt`
- `docs/code_excellence/reports/unified_ce_gate_latest.md`
- `eod_evidence_pack_20260625.md`
- `local_ce_report.md`
- `parse.py`
- `patch_auth.py`
- `patch_auth_state.py`
- `patch_kite_depth.py`
- `patch_telemetry.py`
- `patch_tests.py`
- `print_all.py`
- `reports/regime_entropy_truth_contract_integration_audit.md`
- `reports/regime_entropy_truth_contract_report.md`
- `run_live_loop.sh`
- `runtime/candidate_audits/daemon_health.json`
- `scripts/analyze_blocked_candidates.py`
- `scripts/analyze_past.py`
- `scripts/analyze_today.py`
- `scripts/build_eod_no_trade_evidence.py`
- `scripts/check_morning.py`
- `scripts/check_quote.py`
- `scripts/check_today_candidates.py`
- `scripts/convert_ticks_to_parquet.py`
- `scripts/convert_ticks_to_replay.py`
- `scripts/get_candidate_details.py`
- `scripts/monitor_live.py`
- `scripts/show_candidates.py`
- `scripts/test_cache_keys.py`
- `scripts/test_instruments.py`
- `scripts/test_market_data.py`
- `start_soak.sh`
- `strategies/trade_builder.py`
- `tests/test_candidate_scoring.py`
- `tests/test_entropy_contract.py`
- `tests/test_eod_no_trade_evidence.py`
- `tests/test_feed_00_canonical_feed_truth.py`
- `tests/test_feed_restart_policy.py`
- `tests/test_feed_runtime_states.py`
- `tests/test_feed_safety_gates.py`
- `tests/test_feed_snapshot_reader.py`
- `tests/test_feed_snapshot_writer.py`
- `tests/test_feed_state_engine.py`
- `tests/test_gate_status_log.py`
- `tests/test_live_ranking_blocks.py`
- `tests/test_live_scoring_blocks.py`
- `tests/test_market_data_unstable_reasons.py`
- `tests/test_no_hardcoded_paths_repo_wide.py`
- `tests/test_runtime_status_overlay.py`
- `tests/test_runtime_truth_consistency_pr103.py`
- `tests/test_stale_indicator_blocker_strategy_gate.py`
- `tests/test_strategy_gatekeeper_mode_thresholds.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/test_candidate_scoring.py` | `PASS` | `test_reality_accepted` |
| `tests/test_entropy_contract.py` | `PASS` | `test_reality_accepted` |
| `tests/test_eod_no_trade_evidence.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_00_canonical_feed_truth.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_restart_policy.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_runtime_states.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_safety_gates.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_snapshot_reader.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_snapshot_writer.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_state_engine.py` | `PASS` | `test_reality_accepted` |
| `tests/test_gate_status_log.py` | `BLOCK` | `fake_confidence_test_not_valid_proof` |
| `tests/test_live_ranking_blocks.py` | `PASS` | `test_reality_accepted` |
| `tests/test_live_scoring_blocks.py` | `PASS` | `test_reality_accepted` |
| `tests/test_market_data_unstable_reasons.py` | `PASS` | `test_reality_accepted` |
| `tests/test_no_hardcoded_paths_repo_wide.py` | `PASS` | `test_reality_accepted` |
| `tests/test_runtime_status_overlay.py` | `PASS` | `test_reality_accepted` |
| `tests/test_runtime_truth_consistency_pr103.py` | `PASS` | `test_reality_accepted` |
| `tests/test_stale_indicator_blocker_strategy_gate.py` | `PASS` | `test_reality_accepted` |
| `tests/test_strategy_gatekeeper_mode_thresholds.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `changed.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `check_chain.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `check_tokens.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `code-excellence-gate-reports/changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `code-excellence-gate-reports/unified_agent_elite_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `code-excellence-gate-reports/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `config/config.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/adaptive_risk.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_ranking.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_scoring.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/data_quality.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/decision_dag.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/engine_phase2_adapter.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/entropy_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/eod_no_trade_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed/runtime_store.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed_restart_policy.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed_snapshot_reader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed_snapshot_writer.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed_state_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed_state_model.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/gate_status_log.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/market_data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator_parts/decisions.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/regime_entropy_gate.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/regime_prob_model.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/risk_state.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_requirements.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `dashboard/streamlit_app_runtime.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/regime_entropy_truth_contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `eod_evidence_pack_20260625.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `local_ce_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `parse.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_auth.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_auth_state.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_kite_depth.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_telemetry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `patch_tests.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `print_all.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `reports/regime_entropy_truth_contract_integration_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `reports/regime_entropy_truth_contract_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `run_live_loop.sh` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/daemon_health.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/analyze_blocked_candidates.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/analyze_past.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/analyze_today.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/build_eod_no_trade_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/check_morning.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/check_quote.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/check_today_candidates.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/convert_ticks_to_parquet.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/convert_ticks_to_replay.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/get_candidate_details.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/monitor_live.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/show_candidates.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/test_cache_keys.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/test_instruments.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/test_market_data.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `start_soak.sh` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/trade_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_scoring.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_entropy_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_eod_no_trade_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_00_canonical_feed_truth.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_restart_policy.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_runtime_states.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_safety_gates.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_snapshot_reader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_snapshot_writer.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_state_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_gate_status_log.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_live_ranking_blocks.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_live_scoring_blocks.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_market_data_unstable_reasons.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_no_hardcoded_paths_repo_wide.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_runtime_status_overlay.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_runtime_truth_consistency_pr103.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_stale_indicator_blocker_strategy_gate.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_gatekeeper_mode_thresholds.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/regime_entropy_truth_contract.md` | `PASS` | `evidence_contract_satisfied` |

## Failed Gates

- `minerva` failed with exit_code `1`: blocked findings present
