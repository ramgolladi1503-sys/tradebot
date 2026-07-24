# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot-authority-closure-reconcile-v1`
- config_path: `/Users/madhuram/tradebot-authority-closure-reconcile-v1/.gsd-forensics.yaml`
- changed_paths: `279`
- total_findings: `252`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `23` | `0` |  |
| `cerberus` | `PASS` | `0` | `215` | `0` |  |
| `evidence` | `PASS` | `0` | `14` | `0` |  |

## Changed Paths

- `core/option_backtest/engine.py`
- `docs/agent_reviews/ALL_STRATEGY_AUTHORITY_CLOSURE_V1.md`
- `docs/agent_reviews/ALL_STRATEGY_SOURCE_CENSUS_V1.md`
- `docs/agent_reviews/option_e2e_authority_oracle_v4_1.md`
- `docs/agent_reviews/option_e2e_ci_forensics_v4_1.md`
- `docs/agent_reviews/option_e2e_contract_reconstruction_v4_1.md`
- `docs/agent_reviews/option_e2e_historical_inventory_v4.md`
- `docs/agent_reviews/option_e2e_historical_inventory_v4_1.md`
- `docs/agent_reviews/option_e2e_pipeline_audit_v4.md`
- `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md`
- `docs/agent_reviews/option_e2e_v4_10_1_option_replay_blocker_invalidation.md`
- `docs/agent_reviews/option_e2e_v4_1_authority_verdict_invalidation.md`
- `docs/agent_reviews/option_e2e_v4_2_evidence_implementation_invalidation.md`
- `docs/agent_reviews/option_e2e_v4_6_dormant_source_confusion_invalidation.md`
- `docs/agent_reviews/option_e2e_v4_8_unexecuted_no_signals_invalidation.md`
- `docs/code_excellence/reports/changed_paths.txt`
- `docs/code_excellence/reports/unified_ce_gate_latest.md`
- `docs/research/all_strategy_option_e2e_recertification_v4.json`
- `docs/research/all_strategy_option_e2e_recertification_v4.json.sha256`
- `docs/research/all_strategy_option_e2e_recertification_v4.md`
- `docs/research/all_strategy_option_e2e_recertification_v4.md.sha256`
- `research/option_e2e_recertification_v4/__init__.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/__init__.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/aeron7_nifty_f1_authority_review.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/aeron7_nifty_f1_authority_review.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/all_strategy_authority_matrix.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/all_strategy_authority_matrix.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/authority_blocker_ledger.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/authority_blocker_ledger.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/authority_closure_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/authority_closure_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/blocker_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/blocker_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/blockers_priority.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/build_external_closure.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/closure.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/compact_publication.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_family_authority_reviews.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_family_authority_reviews.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_family_authority_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_family_authority_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_version_authority_decisions.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_version_authority_decisions.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_version_authority_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_version_authority_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/external_evidence_manifest.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/external_evidence_manifest.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/input_census_integrity.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/input_census_integrity.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/priority_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/priority_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/schema.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/schema.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_authority.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_ledger_authority_review.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_ledger_authority_review.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_ledger_authority_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_ledger_authority_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_authority_prioritization.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_authority_prioritization.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_authority_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_authority_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_matrix.py`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/unresolved_source_authority_review.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/unresolved_source_authority_review.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/unresolved_source_authority_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/unresolved_source_authority_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/unresolved_sources.py`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/__init__.py`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/census.py`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/census_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/census_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/dataset_family_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/dataset_family_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/dataset_version_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/dataset_version_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/execution_readiness_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/execution_readiness_summary.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/external_evidence_manifest.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/external_evidence_manifest.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/schema.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/schema.json.sha256`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/signal_ledger_summary.json`
- `research/option_e2e_recertification_v4/all_strategy_source_census_v1/signal_ledger_summary.json.sha256`
- `research/option_e2e_recertification_v4/authority_oracle_v4_1/__init__.py`
- `research/option_e2e_recertification_v4/authority_oracle_v4_1/oracle.py`
- `research/option_e2e_recertification_v4/ci_forensics_v4_1/agent_review_evidence_gate.exit`
- `research/option_e2e_recertification_v4/ci_forensics_v4_1/agent_review_evidence_gate.stderr`
- `research/option_e2e_recertification_v4/ci_forensics_v4_1/agent_review_evidence_gate.stdout`
- `research/option_e2e_recertification_v4/ci_forensics_v4_1/changed_paths.txt`
- `research/option_e2e_recertification_v4/ci_forensics_v4_1/unified_ce_gate.exit`
- `research/option_e2e_recertification_v4/ci_forensics_v4_1/unified_ce_gate.stderr`
- `research/option_e2e_recertification_v4/ci_forensics_v4_1/unified_ce_gate.stdout`
- `research/option_e2e_recertification_v4/ci_forensics_v4_1/unified_ce_gate_latest.md`
- `research/option_e2e_recertification_v4/composite_contract_authority.py`
- `research/option_e2e_recertification_v4/contract_identity_oracle.py`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/__init__.py`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/analyze_contract_reconstruction.py`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/coverage_matrix.csv`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/coverage_matrix.json`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/coverage_matrix.json.sha256`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/summary.json`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/__init__.py`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/build_reconstruction.py`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/evidence_component_counts.json`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/file_reconstruction.json`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/filename_evidence.py`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/manifest_evidence.py`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/observed_universe.py`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/reconstruction_summary.json`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/reconstruction_summary.json.sha256`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/row_evidence.py`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/schema_classifier.py`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/schema_families.json`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/schema_families.json.sha256`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/token_mapping.py`
- `research/option_e2e_recertification_v4/controls.py`
- `research/option_e2e_recertification_v4/cost_model.py`
- `research/option_e2e_recertification_v4/data_census/__init__.py`
- `research/option_e2e_recertification_v4/data_census/census.py`
- `research/option_e2e_recertification_v4/data_census/option_data_census.csv`
- `research/option_e2e_recertification_v4/data_census/option_data_census.json`
- `research/option_e2e_recertification_v4/data_census/option_data_census.json.sha256`
- `research/option_e2e_recertification_v4/data_census/option_data_census_summary.json`
- `research/option_e2e_recertification_v4/data_census_v4_1/__init__.py`
- `research/option_e2e_recertification_v4/data_census_v4_1/census.py`
- `research/option_e2e_recertification_v4/data_census_v4_1/option_data_census_v4_1.csv`
- `research/option_e2e_recertification_v4/data_census_v4_1/option_data_census_v4_1.json`
- `research/option_e2e_recertification_v4/data_census_v4_1/option_data_census_v4_1.json.sha256`
- `research/option_e2e_recertification_v4/data_census_v4_1/option_data_census_v4_1_summary.json`
- `research/option_e2e_recertification_v4/data_census_v4_1/root_proof_v4_1.json`
- `research/option_e2e_recertification_v4/evidence_schema.py`
- `research/option_e2e_recertification_v4/expiry_resolver.py`
- `research/option_e2e_recertification_v4/foundation_manifest.json`
- `research/option_e2e_recertification_v4/foundation_manifest.json.sha256`
- `research/option_e2e_recertification_v4/foundation_v2_manifest.json`
- `research/option_e2e_recertification_v4/foundation_v2_manifest.json.sha256`
- `research/option_e2e_recertification_v4/inventory/alias_graph_v4.json`
- `research/option_e2e_recertification_v4/inventory/canonical_strategy_registry_v4.json`
- `research/option_e2e_recertification_v4/inventory/discovery_commands_v4.txt`
- `research/option_e2e_recertification_v4/inventory/evidence_hashes_v4.json`
- `research/option_e2e_recertification_v4/inventory/historical_claim_map_v4.json`
- `research/option_e2e_recertification_v4/inventory_v4_1/__init__.py`
- `research/option_e2e_recertification_v4/inventory_v4_1/build_inventory_v4_1.py`
- `research/option_e2e_recertification_v4/inventory_v4_1/historical_strategy_inventory_v4_1.json`
- `research/option_e2e_recertification_v4/inventory_v4_1/manifest_v4_1.json`
- `research/option_e2e_recertification_v4/inventory_v4_1/manifest_v4_1.json.sha256`
- `research/option_e2e_recertification_v4/observed_contract_universe.py`
- `research/option_e2e_recertification_v4/option_candidate_builder.py`
- `research/option_e2e_recertification_v4/pipeline_audit.json`
- `research/option_e2e_recertification_v4/pipeline_audit.json.sha256`
- `research/option_e2e_recertification_v4/point_in_time_contract_universe.py`
- `research/option_e2e_recertification_v4/premium_geometry.py`
- `research/option_e2e_recertification_v4/reconciliation.py`
- `research/option_e2e_recertification_v4/redteam/pipeline_defect_ledger.md`
- `research/option_e2e_recertification_v4/replay_bridge.py`
- `research/option_e2e_recertification_v4/signal_contract.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10/__init__.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10/git_discovery.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10/lane_executor.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10/lane_reconciliation.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10/ledger_builder.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10/ledger_oracle.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10/repository_inventory.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10/signal_artifact_loader.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10/source_contract.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/__init__.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/artifact_parser.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/determinism.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/execution_contract.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/generate_source_evidence.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/lane_executor.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/ledger_builder.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/ledger_oracle.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/reconciliation.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/signal_schema.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/source_discovery.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/source_search_manifest.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/tamper.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/vwap_adapter.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_2/__init__.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_2/build_signal_ledgers.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_2/signal_ledgers.json`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_2/signal_ledgers.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_2/signal_ledgers_summary.json`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/__init__.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/adapter_contract.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/audit_real_manifest_evidence.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/coverage_report.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/evidence/real_manifest_audit.json`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/evidence/real_manifest_audit.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/evidence/real_manifest_audit_oracle.json`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/evidence/real_manifest_audit_oracle.json.sha256`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/evidence/real_manifest_audit_summary.md`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/ledger_builder.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/ledger_oracle.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/real_manifest_audit_oracle.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/source_registry.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_4/source_resolver.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_7/__init__.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_7/determinism.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_7/deterministic_adapter.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_7/historical_source_discovery.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_7/lane_status.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_7/ledger_builder.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_7/ledger_oracle.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_7/signal_artifact_loader.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_7/source_contract.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_7/strategy_source_registry.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_8/__init__.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_8/determinism.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_8/deterministic_adapter.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_8/historical_source_discovery.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_8/lane_status.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_8/ledger_builder.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_8/ledger_oracle.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_8/repo_inventory.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_8/signal_artifact_loader.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_8/source_contract.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_8/strategy_source_registry.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/__init__.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/archive_discovery.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/determinism.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/deterministic_generator_adapter.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/evidence_classifier.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/filesystem_discovery.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/git_discovery.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/historical_implementation_loader.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/lane_executor.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/lane_reconciliation.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/ledger_builder.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/ledger_oracle.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/repository_inventory.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/signal_artifact_loader.py`
- `research/option_e2e_recertification_v4/signal_ledgers_v4_9/source_contract.py`
- `research/option_e2e_recertification_v4/strike_resolver.py`
- `research/option_e2e_recertification_v4/time_utils.py`
- `research/option_e2e_recertification_v4/v4_10_2_supersession/__init__.py`
- `research/option_e2e_recertification_v4/v4_10_2_supersession/v4_10_1_option_replay_blocker_invalidation.json`
- `research/option_e2e_recertification_v4/v4_10_2_supersession/v4_10_1_option_replay_blocker_invalidation.json.sha256`
- `research/option_e2e_recertification_v4/v4_10_3_supersession/__init__.py`
- `research/option_e2e_recertification_v4/v4_10_3_supersession/v4_10_2_placeholder_execution_context_invalidation.json`
- `research/option_e2e_recertification_v4/v4_10_3_supersession/v4_10_2_placeholder_execution_context_invalidation.json.sha256`
- `research/option_e2e_recertification_v4/v4_2_supersession/__init__.py`
- `research/option_e2e_recertification_v4/v4_2_supersession/v4_1_authority_verdict_invalidation.json`
- `research/option_e2e_recertification_v4/v4_2_supersession/v4_1_authority_verdict_invalidation.json.sha256`
- `research/option_e2e_recertification_v4/v4_3_supersession/__init__.py`
- `research/option_e2e_recertification_v4/v4_3_supersession/v4_2_evidence_implementation_invalidation.json`
- `research/option_e2e_recertification_v4/v4_3_supersession/v4_2_evidence_implementation_invalidation.json.sha256`
- `research/option_e2e_recertification_v4/v4_7_supersession/v4_6_dormant_source_confusion_invalidation.json`
- `research/option_e2e_recertification_v4/v4_7_supersession/v4_6_dormant_source_confusion_invalidation.json.sha256`
- `research/option_e2e_recertification_v4/v4_9_supersession/v4_8_unexecuted_no_signals_invalidation.json`
- `research/option_e2e_recertification_v4/v4_9_supersession/v4_8_unexecuted_no_signals_invalidation.json.sha256`
- `research/option_e2e_recertification_v4/wfa.py`
- `scripts/research/option_e2e_census_build.py`
- `scripts/research/option_e2e_census_v4_1_build.py`
- `tests/option_backtest/test_engine.py`
- `tests/research/option_e2e/test_all_strategy_authority_closure_v1.py`
- `tests/research/option_e2e/test_all_strategy_source_census_v1.py`
- `tests/research/option_e2e/test_authority_blockers_priority_v1.py`
- `tests/research/option_e2e/test_authority_compact_publication_v1.py`
- `tests/research/option_e2e/test_authority_oracle_v4_1.py`
- `tests/research/option_e2e/test_authority_signal_ledger_v1.py`
- `tests/research/option_e2e/test_authority_strategy_matrix_v1.py`
- `tests/research/option_e2e/test_authority_unresolved_sources_v1.py`
- `tests/research/option_e2e/test_composite_contract_authority.py`
- `tests/research/option_e2e/test_contract_reconstruction_v4_1.py`
- `tests/research/option_e2e/test_contract_reconstruction_v4_2.py`
- `tests/research/option_e2e/test_foundation_contracts.py`
- `tests/research/option_e2e/test_inventory_v4_1.py`
- `tests/research/option_e2e/test_signal_ledgers_v4_10.py`
- `tests/research/option_e2e/test_signal_ledgers_v4_10_2.py`
- `tests/research/option_e2e/test_signal_ledgers_v4_2.py`
- `tests/research/option_e2e/test_signal_ledgers_v4_4.py`
- `tests/research/option_e2e/test_signal_ledgers_v4_7.py`
- `tests/research/option_e2e/test_signal_ledgers_v4_8.py`
- `tests/research/option_e2e/test_signal_ledgers_v4_9.py`
- `tests/research/test_option_e2e_census_v4.py`
- `tests/research/test_option_e2e_census_v4_1.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/option_backtest/test_engine.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_all_strategy_authority_closure_v1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_all_strategy_source_census_v1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_authority_blockers_priority_v1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_authority_compact_publication_v1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_authority_oracle_v4_1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_authority_signal_ledger_v1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_authority_strategy_matrix_v1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_authority_unresolved_sources_v1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_composite_contract_authority.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_contract_reconstruction_v4_1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_contract_reconstruction_v4_2.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_foundation_contracts.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_inventory_v4_1.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_signal_ledgers_v4_10.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_signal_ledgers_v4_10_2.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_signal_ledgers_v4_2.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_signal_ledgers_v4_4.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_signal_ledgers_v4_7.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_signal_ledgers_v4_8.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_signal_ledgers_v4_9.py` | `PASS` | `test_reality_accepted` |
| `tests/research/test_option_e2e_census_v4.py` | `PASS` | `test_reality_accepted` |
| `tests/research/test_option_e2e_census_v4_1.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/option_backtest/engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/ALL_STRATEGY_AUTHORITY_CLOSURE_V1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/ALL_STRATEGY_SOURCE_CENSUS_V1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_authority_oracle_v4_1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_ci_forensics_v4_1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_contract_reconstruction_v4_1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4_1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_pipeline_audit_v4.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_v4_10_1_option_replay_blocker_invalidation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_v4_1_authority_verdict_invalidation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_v4_2_evidence_implementation_invalidation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_v4_6_dormant_source_confusion_invalidation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_v4_8_unexecuted_no_signals_invalidation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/reports/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/all_strategy_option_e2e_recertification_v4.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/all_strategy_option_e2e_recertification_v4.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/authority_closure_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/blocker_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/blockers_priority.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/build_external_closure.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/closure.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/compact_publication.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_family_authority_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/dataset_version_authority_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/external_evidence_manifest.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/priority_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/schema.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_authority.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/signal_ledger_authority_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_authority_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/strategy_matrix.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/unresolved_source_authority_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_authority_closure_v1/unresolved_sources.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_source_census_v1/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_source_census_v1/census.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_source_census_v1/census_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_source_census_v1/dataset_family_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_source_census_v1/dataset_version_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_source_census_v1/execution_readiness_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_source_census_v1/external_evidence_manifest.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_source_census_v1/schema.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/all_strategy_source_census_v1/signal_ledger_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/authority_oracle_v4_1/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/authority_oracle_v4_1/oracle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/ci_forensics_v4_1/changed_paths.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/ci_forensics_v4_1/unified_ce_gate_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/composite_contract_authority.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_identity_oracle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/analyze_contract_reconstruction.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/coverage_matrix.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/build_reconstruction.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/evidence_component_counts.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/file_reconstruction.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/filename_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/manifest_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/observed_universe.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/reconstruction_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/row_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/schema_classifier.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/schema_families.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/contract_reconstruction_v4_2/token_mapping.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/controls.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/cost_model.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census/census.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census/option_data_census.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census/option_data_census_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census_v4_1/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census_v4_1/census.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census_v4_1/option_data_census_v4_1.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census_v4_1/option_data_census_v4_1_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census_v4_1/root_proof_v4_1.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/evidence_schema.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/expiry_resolver.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/foundation_manifest.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/foundation_v2_manifest.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory/alias_graph_v4.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory/canonical_strategy_registry_v4.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory/discovery_commands_v4.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory/evidence_hashes_v4.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory/historical_claim_map_v4.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory_v4_1/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory_v4_1/build_inventory_v4_1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory_v4_1/historical_strategy_inventory_v4_1.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory_v4_1/manifest_v4_1.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/observed_contract_universe.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/option_candidate_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/pipeline_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/point_in_time_contract_universe.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/premium_geometry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/reconciliation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/redteam/pipeline_defect_ledger.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/replay_bridge.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10/git_discovery.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10/lane_executor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10/lane_reconciliation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10/ledger_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10/ledger_oracle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10/repository_inventory.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10/signal_artifact_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10/source_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/artifact_parser.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/determinism.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/execution_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/generate_source_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/lane_executor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/ledger_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/ledger_oracle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/reconciliation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/signal_schema.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/source_discovery.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/source_search_manifest.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/tamper.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_10_2/vwap_adapter.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_2/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_2/build_signal_ledgers.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_2/signal_ledgers.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_2/signal_ledgers_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/adapter_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/audit_real_manifest_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/coverage_report.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/evidence/real_manifest_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/evidence/real_manifest_audit_oracle.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/evidence/real_manifest_audit_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/ledger_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/ledger_oracle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/real_manifest_audit_oracle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/source_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_4/source_resolver.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_7/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_7/determinism.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_7/deterministic_adapter.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_7/historical_source_discovery.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_7/lane_status.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_7/ledger_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_7/ledger_oracle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_7/signal_artifact_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_7/source_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_7/strategy_source_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_8/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_8/determinism.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_8/deterministic_adapter.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_8/historical_source_discovery.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_8/lane_status.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_8/ledger_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_8/ledger_oracle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_8/repo_inventory.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_8/signal_artifact_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_8/source_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_8/strategy_source_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/archive_discovery.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/determinism.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/deterministic_generator_adapter.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/evidence_classifier.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/filesystem_discovery.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/git_discovery.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/historical_implementation_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/lane_executor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/lane_reconciliation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/ledger_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/ledger_oracle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/repository_inventory.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/signal_artifact_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_ledgers_v4_9/source_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/strike_resolver.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/time_utils.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/v4_10_2_supersession/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/v4_10_2_supersession/v4_10_1_option_replay_blocker_invalidation.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/v4_10_3_supersession/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/v4_10_3_supersession/v4_10_2_placeholder_execution_context_invalidation.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/v4_2_supersession/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/v4_2_supersession/v4_1_authority_verdict_invalidation.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/v4_3_supersession/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/v4_3_supersession/v4_2_evidence_implementation_invalidation.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/v4_7_supersession/v4_6_dormant_source_confusion_invalidation.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/v4_9_supersession/v4_8_unexecuted_no_signals_invalidation.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/wfa.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/research/option_e2e_census_build.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/research/option_e2e_census_v4_1_build.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/option_backtest/test_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_all_strategy_authority_closure_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_all_strategy_source_census_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_authority_blockers_priority_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_authority_compact_publication_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_authority_oracle_v4_1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_authority_signal_ledger_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_authority_strategy_matrix_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_authority_unresolved_sources_v1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_composite_contract_authority.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_contract_reconstruction_v4_1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_contract_reconstruction_v4_2.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_foundation_contracts.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_inventory_v4_1.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_signal_ledgers_v4_10.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_signal_ledgers_v4_10_2.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_signal_ledgers_v4_2.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_signal_ledgers_v4_4.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_signal_ledgers_v4_7.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_signal_ledgers_v4_8.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_signal_ledgers_v4_9.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/test_option_e2e_census_v4.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/test_option_e2e_census_v4_1.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/ALL_STRATEGY_AUTHORITY_CLOSURE_V1.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/ALL_STRATEGY_SOURCE_CENSUS_V1.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_authority_oracle_v4_1.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_ci_forensics_v4_1.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_contract_reconstruction_v4_1.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4_1.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_pipeline_audit_v4.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_v4_10_1_option_replay_blocker_invalidation.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_v4_1_authority_verdict_invalidation.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_v4_2_evidence_implementation_invalidation.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_v4_6_dormant_source_confusion_invalidation.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/option_e2e_v4_8_unexecuted_no_signals_invalidation.md` | `PASS` | `evidence_contract_satisfied` |
