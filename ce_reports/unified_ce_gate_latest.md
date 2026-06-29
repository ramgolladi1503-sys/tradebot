# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/home/runner/work/tradebot/tradebot`
- config_path: `/home/runner/work/tradebot/tradebot/.gsd-forensics.yaml`
- changed_paths: `72`
- total_findings: `90`
- total_blocks: `11`
- exit_code: `1`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `BLOCK` | `1` | `10` | `3` |  |
| `cerberus` | `PASS` | `0` | `72` | `0` |  |
| `evidence` | `BLOCK` | `1` | `8` | `8` |  |

## Changed Paths

- `config/config.py`
- `core/kite_depth_ws.py`
- `core/live_drift/report_generator.py`
- `core/paths.py`
- `core/statistical_validation/report_generator.py`
- `core/strategy_certification/certification_loader.py`
- `core/strategy_certification/report_generator.py`
- `core/strategy_pipeline/artifact_locator.py`
- `core/strategy_pipeline/pipeline_engine.py`
- `core/strategy_registry/registry_loader.py`
- `core/strategy_truth/atomic_json.py`
- `core/strategy_truth/report_generator.py`
- `data/live_drift/baselines/nifty_intraday.json`
- `data/live_drift/snapshots/nifty_intraday.json`
- `docs/agent_reviews/feed_reconnect_20260629.md`
- `docs/live_drift/nifty_intraday/01_baseline.md`
- `docs/live_drift/nifty_intraday/02_current_snapshot.md`
- `docs/live_drift/nifty_intraday/03_drift_analysis.md`
- `docs/live_drift/nifty_intraday/04_regime_drift.md`
- `docs/live_drift/nifty_intraday/05_execution_drift.md`
- `docs/live_drift/nifty_intraday/06_certification_status.md`
- `docs/live_drift/nifty_intraday/07_notifications.md`
- `docs/live_drift/nifty_intraday/08_audit_log.md`
- `docs/live_drift/nifty_intraday/09_limitations.md`
- `docs/live_drift/nifty_intraday/10_summary.md`
- `docs/observability/feed_reconnect_rca_20260629.md`
- `docs/observability/feed_reconnect_soak_evidence_20260629.md`
- `docs/outcome_evidence/03_replay_run_report.md`
- `docs/outcome_evidence/04_outcome_quality_report.md`
- `docs/outcome_evidence/05_rejected_candidate_report.md`
- `docs/outcome_evidence/07_regime_context_report.md`
- `docs/research_registry/01_hypothesis_inventory.md`
- `docs/research_registry/02_experiment_inventory.md`
- `docs/research_registry/03_lineage_graph.md`
- `docs/research_registry/04_parameter_history.md`
- `docs/research_registry/06_successful_experiments.md`
- `docs/research_registry/07_promotion_candidates.md`
- `docs/research_registry/09_limitations.md`
- `docs/strategy_certification/09_audit_log.md`
- `docs/strategy_certification/nifty_intraday/01_registry_gate.md`
- `docs/strategy_certification/nifty_intraday/02_truth_gate.md`
- `docs/strategy_certification/nifty_intraday/03_evidence_gate.md`
- `docs/strategy_certification/nifty_intraday/04_statistics_gate.md`
- `docs/strategy_certification/nifty_intraday/05_risk_gate.md`
- `docs/strategy_certification/nifty_intraday/06_certification_matrix.md`
- `docs/strategy_certification/nifty_intraday/07_blockers.md`
- `docs/strategy_certification/nifty_intraday/08_limitations.md`
- `docs/strategy_certification/nifty_intraday/10_certification_summary.md`
- `docs/strategy_pipeline/banknifty_intraday/08_blockers.md`
- `docs/strategy_pipeline/banknifty_intraday/10_final_decision.md`
- `docs/strategy_pipeline/nifty_intraday/01_pipeline_summary.md`
- `docs/strategy_pipeline/nifty_intraday/08_blockers.md`
- `docs/strategy_pipeline/nifty_intraday/09_limitations.md`
- `docs/strategy_pipeline/nifty_intraday/10_final_decision.md`
- `research/experiments/nifty_intraday.json`
- `research/hypotheses/nifty_intraday.json`
- `scripts/run_live_drift.py`
- `scripts/run_outcome_evidence_replay.py`
- `scripts/run_research_registry.py`
- `scripts/run_statistical_validation.py`
- `scripts/run_strategy_certification.py`
- `scripts/run_strategy_truth_audit.py`
- `tests/statistical_validation/test_statistics_persistence.py`
- `tests/strategy_certification/test_certification_loader.py`
- `tests/strategy_certification/test_certification_loader_validation.py`
- `tests/strategy_pipeline/test_end_to_end_acceptance.py`
- `tests/strategy_pipeline/test_pipeline_engine.py`
- `tests/strategy_truth/test_htf_strategy_truth.py`
- `tests/strategy_truth/test_semantic_audit.py`
- `tests/strategy_truth/test_truth_persistence.py`
- `tests/test_feed_reconnect_safety.py`
- `tests/test_kite_depth_restart.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/statistical_validation/test_statistics_persistence.py` | `BLOCK` | `fake_confidence_test_not_valid_proof` |
| `tests/strategy_certification/test_certification_loader.py` | `PASS` | `test_reality_accepted` |
| `tests/strategy_certification/test_certification_loader_validation.py` | `BLOCK` | `unknown_test_reality_not_valid_proof` |
| `tests/strategy_pipeline/test_end_to_end_acceptance.py` | `PASS` | `test_reality_accepted` |
| `tests/strategy_pipeline/test_pipeline_engine.py` | `PASS` | `test_reality_accepted` |
| `tests/strategy_truth/test_htf_strategy_truth.py` | `PASS` | `test_reality_accepted` |
| `tests/strategy_truth/test_semantic_audit.py` | `PASS` | `test_reality_accepted` |
| `tests/strategy_truth/test_truth_persistence.py` | `BLOCK` | `fake_confidence_test_not_valid_proof` |
| `tests/test_feed_reconnect_safety.py` | `PASS` | `test_reality_accepted` |
| `tests/test_kite_depth_restart.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `config/config.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/kite_depth_ws.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/report_generator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/paths.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/statistical_validation/report_generator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/certification_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/report_generator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_pipeline/artifact_locator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_pipeline/pipeline_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_registry/registry_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/atomic_json.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/report_generator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `data/live_drift/baselines/nifty_intraday.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `data/live_drift/snapshots/nifty_intraday.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed_reconnect_20260629.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/nifty_intraday/01_baseline.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/nifty_intraday/02_current_snapshot.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/nifty_intraday/03_drift_analysis.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/nifty_intraday/04_regime_drift.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/nifty_intraday/05_execution_drift.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/nifty_intraday/06_certification_status.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/nifty_intraday/07_notifications.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/nifty_intraday/08_audit_log.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/nifty_intraday/09_limitations.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/nifty_intraday/10_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/observability/feed_reconnect_rca_20260629.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/observability/feed_reconnect_soak_evidence_20260629.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/outcome_evidence/03_replay_run_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/outcome_evidence/04_outcome_quality_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/outcome_evidence/05_rejected_candidate_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/outcome_evidence/07_regime_context_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/01_hypothesis_inventory.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/02_experiment_inventory.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/03_lineage_graph.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/04_parameter_history.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/06_successful_experiments.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/07_promotion_candidates.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/09_limitations.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/09_audit_log.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/nifty_intraday/01_registry_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/nifty_intraday/02_truth_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/nifty_intraday/03_evidence_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/nifty_intraday/04_statistics_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/nifty_intraday/05_risk_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/nifty_intraday/06_certification_matrix.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/nifty_intraday/07_blockers.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/nifty_intraday/08_limitations.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/nifty_intraday/10_certification_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/banknifty_intraday/08_blockers.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/banknifty_intraday/10_final_decision.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/nifty_intraday/01_pipeline_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/nifty_intraday/08_blockers.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/nifty_intraday/09_limitations.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_pipeline/nifty_intraday/10_final_decision.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/experiments/nifty_intraday.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/hypotheses/nifty_intraday.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_live_drift.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_outcome_evidence_replay.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_research_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_statistical_validation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_strategy_certification.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_strategy_truth_audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/statistical_validation/test_statistics_persistence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_certification/test_certification_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_certification/test_certification_loader_validation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_pipeline/test_end_to_end_acceptance.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_pipeline/test_pipeline_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_htf_strategy_truth.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_semantic_audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_truth_persistence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_reconnect_safety.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_kite_depth_restart.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/feed_reconnect_20260629.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/feed_reconnect_20260629.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/feed_reconnect_20260629.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/feed_reconnect_20260629.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/feed_reconnect_20260629.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/feed_reconnect_20260629.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/feed_reconnect_20260629.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/feed_reconnect_20260629.md` | `BLOCK` | `required_evidence_field_missing` |

## Failed Gates

- `minerva` failed with exit_code `1`: blocked findings present
- `evidence` failed with exit_code `1`: blocked findings present
