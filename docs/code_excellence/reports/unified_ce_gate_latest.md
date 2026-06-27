# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `28`
- total_findings: `30`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `1` | `0` |  |
| `cerberus` | `PASS` | `0` | `28` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `core/live_drift/__init__.py`
- `core/live_drift/audit_log.py`
- `core/live_drift/baseline_loader.py`
- `core/live_drift/certification_lifecycle.py`
- `core/live_drift/drift_detector.py`
- `core/live_drift/drift_models.py`
- `core/live_drift/drift_types.py`
- `core/live_drift/execution_drift.py`
- `core/live_drift/freshness_checker.py`
- `core/live_drift/live_snapshot_loader.py`
- `core/live_drift/notification_engine.py`
- `core/live_drift/performance_drift.py`
- `core/live_drift/regime_drift.py`
- `core/live_drift/report_generator.py`
- `core/live_drift/validation.py`
- `docs/agent_reviews/PR-7_live_drift.md`
- `docs/live_drift/01_baseline.md`
- `docs/live_drift/02_current_snapshot.md`
- `docs/live_drift/03_drift_analysis.md`
- `docs/live_drift/04_regime_drift.md`
- `docs/live_drift/05_execution_drift.md`
- `docs/live_drift/06_certification_status.md`
- `docs/live_drift/07_notifications.md`
- `docs/live_drift/08_audit_log.md`
- `docs/live_drift/09_limitations.md`
- `docs/live_drift/10_summary.md`
- `scripts/run_live_drift.py`
- `tests/live_drift/test_live_drift.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/live_drift/test_live_drift.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/live_drift/__init__.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/audit_log.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/baseline_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/certification_lifecycle.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/drift_detector.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/drift_models.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/drift_types.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/execution_drift.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/freshness_checker.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/live_snapshot_loader.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/notification_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/performance_drift.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/regime_drift.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/report_generator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/live_drift/validation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR-7_live_drift.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/01_baseline.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/02_current_snapshot.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/03_drift_analysis.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/04_regime_drift.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/05_execution_drift.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/06_certification_status.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/07_notifications.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/08_audit_log.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/09_limitations.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/live_drift/10_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_live_drift.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/live_drift/test_live_drift.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/PR-7_live_drift.md` | `PASS` | `evidence_contract_satisfied` |
