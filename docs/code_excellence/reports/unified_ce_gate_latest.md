# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `64`
- total_findings: `67`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `3` | `0` |  |
| `cerberus` | `PASS` | `0` | `64` | `0` |  |
| `evidence` | `PASS` | `0` | `0` | `0` |  |

## Changed Paths

- `core/intelligence/calibration/factors.py`
- `core/intelligence/calibration/relevance_model.py`
- `core/intelligence/config.py`
- `core/intelligence/context_adapter.py`
- `core/intelligence/extractors/base.py`
- `core/intelligence/extractors/hardened_base.py`
- `core/intelligence/extractors/nse_extractor.py`
- `core/intelligence/extractors/rbi_extractor.py`
- `core/intelligence/extractors/sebi_extractor.py`
- `core/intelligence/fetchers/base.py`
- `core/intelligence/fetchers/http_fetcher.py`
- `core/intelligence/knowledge/graph.py`
- `core/intelligence/replay/intelligence_replay.py`
- `core/intelligence/robots_gate.py`
- `core/intelligence/sources.py`
- `core/intelligence/storage/sqlite_store.py`
- `core/intelligence/storage/store.py`
- `core/intelligence/telemetry.py`
- `core/intelligence/validators/schemas.py`
- `docs/mip/01_repository_reverse_engineering.md`
- `docs/mip/02_non_negotiable_safety_boundaries.md`
- `docs/mip/03_market_intelligence_architecture.md`
- `docs/mip/04_fetch_infrastructure_report.md`
- `docs/mip/05_extraction_report.md`
- `docs/mip/06_knowledge_graph_report.md`
- `docs/mip/07_calibration_report.md`
- `docs/mip/08_replay_intelligence_report.md`
- `docs/mip/09_tradebot_integration_report.md`
- `docs/mip/10_dashboard_reporting_report.md`
- `docs/mip/11_test_report.md`
- `docs/mip/12_anti_heuristic_architecture_audit.md`
- `docs/mip/13_production_readiness_report.md`
- `docs/mip/14_alpha_research_governance_report.md`
- `docs/mip_excellence/01_operational_audit.md`
- `docs/mip_excellence/02_end_to_end_validation.md`
- `docs/mip_excellence/03_replay_validation.md`
- `docs/mip_excellence/04_fault_injection_report.md`
- `docs/mip_excellence/05_soak_test.md`
- `docs/mip_excellence/06_benchmark_report.md`
- `docs/mip_excellence/07_security_audit.md`
- `docs/mip_hardening/01_current_state_audit.md`
- `docs/mip_hardening/02_tradebot_integration_map.md`
- `docs/mip_hardening/03_fetch_hardening_report.md`
- `docs/mip_hardening/04_persistence_report.md`
- `docs/mip_hardening/05_extraction_hardening_report.md`
- `docs/mip_hardening/06_factor_model_report.md`
- `docs/mip_hardening/07_replay_calibration_report.md`
- `docs/mip_hardening/08_telemetry_report.md`
- `docs/mip_hardening/09_runner_scheduler_report.md`
- `docs/mip_hardening/10_dashboard_reporting_report.md`
- `docs/mip_hardening/11_security_compliance_report.md`
- `docs/mip_hardening/12_test_expansion_report.md`
- `docs/mip_hardening/13_anti_heuristic_audit.md`
- `docs/mip_hardening/14_production_readiness_score.md`
- `scripts/generate_mip_report.py`
- `scripts/run_benchmark.py`
- `scripts/run_e2e_validation.py`
- `scripts/run_fault_injection.py`
- `scripts/run_intelligence_pipeline.py`
- `scripts/run_operational_audit.py`
- `scripts/run_soak_test.py`
- `tests/intelligence/test_extractors.py`
- `tests/intelligence/test_mip_hardening.py`
- `tests/intelligence/test_mip_safety.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/intelligence/test_extractors.py` | `PASS` | `test_reality_accepted` |
| `tests/intelligence/test_mip_hardening.py` | `PASS` | `test_reality_accepted` |
| `tests/intelligence/test_mip_safety.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/intelligence/calibration/factors.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/calibration/relevance_model.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/config.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/context_adapter.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/extractors/base.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/extractors/hardened_base.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/extractors/nse_extractor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/extractors/rbi_extractor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/extractors/sebi_extractor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/fetchers/base.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/fetchers/http_fetcher.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/knowledge/graph.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/replay/intelligence_replay.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/robots_gate.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/sources.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/storage/sqlite_store.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/storage/store.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/telemetry.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/intelligence/validators/schemas.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/01_repository_reverse_engineering.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/02_non_negotiable_safety_boundaries.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/03_market_intelligence_architecture.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/04_fetch_infrastructure_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/05_extraction_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/06_knowledge_graph_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/07_calibration_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/08_replay_intelligence_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/09_tradebot_integration_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/10_dashboard_reporting_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/11_test_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/12_anti_heuristic_architecture_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/13_production_readiness_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/14_alpha_research_governance_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_excellence/01_operational_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_excellence/02_end_to_end_validation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_excellence/03_replay_validation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_excellence/04_fault_injection_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_excellence/05_soak_test.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_excellence/06_benchmark_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_excellence/07_security_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/01_current_state_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/02_tradebot_integration_map.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/03_fetch_hardening_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/04_persistence_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/05_extraction_hardening_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/06_factor_model_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/07_replay_calibration_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/08_telemetry_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/09_runner_scheduler_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/10_dashboard_reporting_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/11_security_compliance_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/12_test_expansion_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/13_anti_heuristic_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_hardening/14_production_readiness_score.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/generate_mip_report.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_benchmark.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_e2e_validation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_fault_injection.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_intelligence_pipeline.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_operational_audit.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_soak_test.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/intelligence/test_extractors.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/intelligence/test_mip_hardening.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/intelligence/test_mip_safety.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

- No findings.
