# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `26`
- total_findings: `28`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `1` | `0` |  |
| `cerberus` | `PASS` | `0` | `26` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `core/strategy_certification/__init__.py`
- `core/strategy_certification/audit_log.py`
- `core/strategy_certification/certification_engine.py`
- `core/strategy_certification/certification_models.py`
- `core/strategy_certification/certification_types.py`
- `core/strategy_certification/eligibility.py`
- `core/strategy_certification/evidence_gate.py`
- `core/strategy_certification/report_generator.py`
- `core/strategy_certification/risk_gate.py`
- `core/strategy_certification/statistics_gate.py`
- `core/strategy_certification/truth_gate.py`
- `core/strategy_certification/validation.py`
- `core/strategy_truth/semantic_comparator.py`
- `docs/agent_reviews/PR-5_strategy_certification.md`
- `docs/strategy_certification/01_registry_gate.md`
- `docs/strategy_certification/02_truth_gate.md`
- `docs/strategy_certification/03_evidence_gate.md`
- `docs/strategy_certification/04_statistics_gate.md`
- `docs/strategy_certification/05_risk_gate.md`
- `docs/strategy_certification/06_certification_matrix.md`
- `docs/strategy_certification/07_blockers.md`
- `docs/strategy_certification/08_limitations.md`
- `docs/strategy_certification/09_audit_log.md`
- `docs/strategy_certification/10_certification_summary.md`
- `scripts/run_strategy_certification.py`
- `tests/strategy_certification/test_strategy_certification.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/strategy_certification/test_strategy_certification.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/strategy_certification/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/audit_log.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/certification_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/certification_models.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/certification_types.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/eligibility.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/evidence_gate.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/report_generator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/risk_gate.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/statistics_gate.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/truth_gate.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_certification/validation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_truth/semantic_comparator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR-5_strategy_certification.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/01_registry_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/02_truth_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/03_evidence_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/04_statistics_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/05_risk_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/06_certification_matrix.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/07_blockers.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/08_limitations.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/09_audit_log.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_certification/10_certification_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_strategy_certification.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/strategy_certification/test_strategy_certification.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/PR-5_strategy_certification.md` | `PASS` | `evidence_contract_satisfied` |
