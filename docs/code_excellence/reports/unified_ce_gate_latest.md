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
- total_findings: `44`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `7` | `0` |  |
| `cerberus` | `PASS` | `0` | `37` | `0` |  |
| `evidence` | `PASS` | `0` | `0` | `0` |  |

## Changed Paths

- `core/strategy_truth/__init__.py`
- `core/strategy_truth/audit_engine.py`
- `core/strategy_truth/control_flow.py`
- `core/strategy_truth/decision_graph.py`
- `core/strategy_truth/dependency_analyzer.py`
- `core/strategy_truth/heuristic_detector.py`
- `core/strategy_truth/implementation_auditor.py`
- `core/strategy_truth/mathematical_auditor.py`
- `core/strategy_truth/parameter_auditor.py`
- `core/strategy_truth/registry_bridge.py`
- `core/strategy_truth/report_generator.py`
- `core/strategy_truth/rule_extractor.py`
- `core/strategy_truth/semantic_comparator.py`
- `core/strategy_truth/semantic_vocabulary.py`
- `core/strategy_truth/source_scanner.py`
- `core/strategy_truth/truth_models.py`
- `core/strategy_truth/truth_types.py`
- `docs/strategy_truth/01_loaded_registry.md`
- `docs/strategy_truth/02_parameter_inventory.md`
- `docs/strategy_truth/03_heuristic_audit.md`
- `docs/strategy_truth/04_indicator_inventory.md`
- `docs/strategy_truth/05_dependency_graph.md`
- `docs/strategy_truth/06_strategy_truth_summary.md`
- `docs/strategy_truth/07_semantic_gap_audit.md`
- `docs/strategy_truth/08_control_flow_graphs.md`
- `docs/strategy_truth/09_semantic_comparison.md`
- `docs/strategy_truth/10_mathematical_audit.md`
- `docs/strategy_truth/11_hardened_strategy_truth_summary.md`
- `scripts/run_strategy_truth_audit.py`
- `tests/strategy_truth/__init__.py`
- `tests/strategy_truth/fixtures/dummy_strat.py`
- `tests/strategy_truth/test_audit.py`
- `tests/strategy_truth/test_htf_strategy_truth.py`
- `tests/strategy_truth/test_legacy_quarantine.py`
- `tests/strategy_truth/test_mean_reversion_candidate_truth.py`
- `tests/strategy_truth/test_pro_engine_strategies.py`
- `tests/strategy_truth/test_semantic_audit.py`
- `tests/strategy_truth/test_trade_builder_strategies.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/strategy_truth/test_audit.py` | `PASS` | `test_reality_accepted` |
| `tests/strategy_truth/test_htf_strategy_truth.py` | `PASS` | `test_reality_accepted` |
| `tests/strategy_truth/test_legacy_quarantine.py` | `PASS` | `test_reality_accepted` |
| `tests/strategy_truth/test_mean_reversion_candidate_truth.py` | `PASS` | `test_reality_accepted` |
| `tests/strategy_truth/test_pro_engine_strategies.py` | `PASS` | `test_reality_accepted` |
| `tests/strategy_truth/test_semantic_audit.py` | `PASS` | `test_reality_accepted` |
| `tests/strategy_truth/test_trade_builder_strategies.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/strategy_truth/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/audit_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/control_flow.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/decision_graph.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/dependency_analyzer.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/heuristic_detector.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/implementation_auditor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/mathematical_auditor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/parameter_auditor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/registry_bridge.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/report_generator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/rule_extractor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/semantic_comparator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/semantic_vocabulary.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/source_scanner.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/truth_models.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/truth_types.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/01_loaded_registry.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/02_parameter_inventory.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/03_heuristic_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/04_indicator_inventory.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/05_dependency_graph.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/06_strategy_truth_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/07_semantic_gap_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/08_control_flow_graphs.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/09_semantic_comparison.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/10_mathematical_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/11_hardened_strategy_truth_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_strategy_truth_audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/fixtures/dummy_strat.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_htf_strategy_truth.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_legacy_quarantine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_mean_reversion_candidate_truth.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_pro_engine_strategies.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_semantic_audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_truth/test_trade_builder_strategies.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

- No findings.
