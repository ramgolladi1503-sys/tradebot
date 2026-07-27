# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot-option-e2e-ci-forensics-v4`
- config_path: `/Users/madhuram/tradebot-option-e2e-ci-forensics-v4/.gsd-forensics.yaml`
- changed_paths: `42`
- total_findings: `67`
- total_blocks: `30`
- exit_code: `1`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `BLOCK` | `1` | `3` | `1` |  |
| `cerberus` | `BLOCK` | `1` | `43` | `8` |  |
| `evidence` | `BLOCK` | `1` | `21` | `21` |  |

## Changed Paths

- `core/option_backtest/engine.py`
- `docs/agent_reviews/option_e2e_historical_inventory_v4.md`
- `docs/agent_reviews/option_e2e_pipeline_audit_v4.md`
- `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md`
- `docs/research/all_strategy_option_e2e_recertification_v4.json`
- `docs/research/all_strategy_option_e2e_recertification_v4.json.sha256`
- `docs/research/all_strategy_option_e2e_recertification_v4.md`
- `research/option_e2e_recertification_v4/__init__.py`
- `research/option_e2e_recertification_v4/controls.py`
- `research/option_e2e_recertification_v4/cost_model.py`
- `research/option_e2e_recertification_v4/data_census/__init__.py`
- `research/option_e2e_recertification_v4/data_census/census.py`
- `research/option_e2e_recertification_v4/data_census/option_data_census.csv`
- `research/option_e2e_recertification_v4/data_census/option_data_census.json`
- `research/option_e2e_recertification_v4/data_census/option_data_census.json.sha256`
- `research/option_e2e_recertification_v4/data_census/option_data_census_summary.json`
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
- `research/option_e2e_recertification_v4/option_candidate_builder.py`
- `research/option_e2e_recertification_v4/pipeline_audit.json`
- `research/option_e2e_recertification_v4/pipeline_audit.json.sha256`
- `research/option_e2e_recertification_v4/point_in_time_contract_universe.py`
- `research/option_e2e_recertification_v4/premium_geometry.py`
- `research/option_e2e_recertification_v4/reconciliation.py`
- `research/option_e2e_recertification_v4/redteam/pipeline_defect_ledger.md`
- `research/option_e2e_recertification_v4/replay_bridge.py`
- `research/option_e2e_recertification_v4/signal_contract.py`
- `research/option_e2e_recertification_v4/strike_resolver.py`
- `research/option_e2e_recertification_v4/wfa.py`
- `scripts/research/option_e2e_census_build.py`
- `tests/option_backtest/test_engine.py`
- `tests/research/option_e2e/test_foundation_contracts.py`
- `tests/research/test_option_e2e_census_v4.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/option_backtest/test_engine.py` | `PASS` | `test_reality_accepted` |
| `tests/research/option_e2e/test_foundation_contracts.py` | `PASS` | `test_reality_accepted` |
| `tests/research/test_option_e2e_census_v4.py` | `BLOCK` | `fake_confidence_test_not_valid_proof` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/option_backtest/engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_pipeline_audit_v4.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/all_strategy_option_e2e_recertification_v4.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/all_strategy_option_e2e_recertification_v4.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/controls.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/cost_model.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census/census.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census/option_data_census.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/data_census/option_data_census_summary.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/evidence_schema.py` | `BLOCK` | `non_action_field_not_explicitly_false` |
| `research/option_e2e_recertification_v4/evidence_schema.py` | `BLOCK` | `non_action_field_not_explicitly_false` |
| `research/option_e2e_recertification_v4/evidence_schema.py` | `BLOCK` | `non_action_field_not_explicitly_false` |
| `research/option_e2e_recertification_v4/evidence_schema.py` | `BLOCK` | `non_action_field_not_explicitly_false` |
| `research/option_e2e_recertification_v4/evidence_schema.py` | `BLOCK` | `non_action_field_not_explicitly_false` |
| `research/option_e2e_recertification_v4/evidence_schema.py` | `BLOCK` | `non_action_field_not_explicitly_false` |
| `research/option_e2e_recertification_v4/evidence_schema.py` | `BLOCK` | `non_action_field_not_explicitly_false` |
| `research/option_e2e_recertification_v4/evidence_schema.py` | `BLOCK` | `non_action_field_not_explicitly_false` |
| `research/option_e2e_recertification_v4/expiry_resolver.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/foundation_manifest.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/foundation_v2_manifest.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory/alias_graph_v4.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory/canonical_strategy_registry_v4.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory/discovery_commands_v4.txt` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory/evidence_hashes_v4.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/inventory/historical_claim_map_v4.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/option_candidate_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/pipeline_audit.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/point_in_time_contract_universe.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/premium_geometry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/reconciliation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/redteam/pipeline_defect_ledger.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/replay_bridge.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/signal_contract.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/strike_resolver.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `research/option_e2e_recertification_v4/wfa.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/research/option_e2e_census_build.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/option_backtest/test_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/option_e2e/test_foundation_contracts.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research/test_option_e2e_census_v4.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_historical_inventory_v4.md` | `BLOCK` | `weak_evidence_pattern_found` |
| `docs/agent_reviews/option_e2e_pipeline_audit_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_pipeline_audit_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_pipeline_audit_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_pipeline_audit_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_pipeline_audit_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_pipeline_audit_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/option_e2e_pipeline_redteam_v4.md` | `BLOCK` | `required_evidence_field_missing` |

## Failed Gates

- `minerva` failed with exit_code `1`: blocked findings present
- `cerberus` failed with exit_code `1`: blocked findings present
- `evidence` failed with exit_code `1`: blocked findings present
