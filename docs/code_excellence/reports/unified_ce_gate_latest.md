# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `29`
- total_findings: `31`
- total_blocks: `1`
- exit_code: `1`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `BLOCK` | `1` | `1` | `1` |  |
| `cerberus` | `PASS` | `0` | `29` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `core/research_registry/__init__.py`
- `core/research_registry/dependency_graph.py`
- `core/research_registry/evidence_linker.py`
- `core/research_registry/experiment_loader.py`
- `core/research_registry/experiment_registry.py`
- `core/research_registry/experiment_validator.py`
- `core/research_registry/hypothesis_registry.py`
- `core/research_registry/lineage_tracker.py`
- `core/research_registry/promotion_policy.py`
- `core/research_registry/report_generator.py`
- `core/research_registry/research_engine.py`
- `core/research_registry/research_models.py`
- `core/research_registry/research_types.py`
- `core/research_registry/validation.py`
- `docs/agent_reviews/PR-6_research_registry.md`
- `docs/research_registry/01_hypothesis_inventory.md`
- `docs/research_registry/02_experiment_inventory.md`
- `docs/research_registry/03_lineage_graph.md`
- `docs/research_registry/04_parameter_history.md`
- `docs/research_registry/05_failed_experiments.md`
- `docs/research_registry/06_successful_experiments.md`
- `docs/research_registry/07_promotion_candidates.md`
- `docs/research_registry/08_duplicate_detection.md`
- `docs/research_registry/09_limitations.md`
- `docs/research_registry/10_architecture.md`
- `docs/research_registry/11_governance.md`
- `docs/research_registry/12_summary.md`
- `scripts/run_research_registry.py`
- `tests/research_registry/test_research_registry.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/research_registry/test_research_registry.py` | `BLOCK` | `fake_confidence_test_not_valid_proof` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/research_registry/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/dependency_graph.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/evidence_linker.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/experiment_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/experiment_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/experiment_validator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/hypothesis_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/lineage_tracker.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/promotion_policy.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/report_generator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/research_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/research_models.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/research_types.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/research_registry/validation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR-6_research_registry.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/01_hypothesis_inventory.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/02_experiment_inventory.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/03_lineage_graph.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/04_parameter_history.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/05_failed_experiments.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/06_successful_experiments.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/07_promotion_candidates.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/08_duplicate_detection.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/09_limitations.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/10_architecture.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/11_governance.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research_registry/12_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_research_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/research_registry/test_research_registry.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/PR-6_research_registry.md` | `PASS` | `evidence_contract_satisfied` |

## Failed Gates

- `minerva` failed with exit_code `1`: blocked findings present
