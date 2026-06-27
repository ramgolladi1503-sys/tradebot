# PR-11: Live Drift Persistence

## Agent Identity
- Agent: Antigravity
- Task: Replace mock data with disk-backed loader in Live Drift Engine.

## Required Proof of Safety

- is_order_action: false
- broker_api_called: false
- risk_gate_modified: false
- live_execution_changed: false
- append_only_evidence_changed: false

## PR Scope & Summary

This PR introduces disk-persistence capabilities to the `core/live_drift` module, replacing `build_mock_data()` with `DiskLiveDriftLoader`. The orchestrator will now use actual artifact files instead of hardcoded synthetic baseline/snapshot data.

- Replaced synthetic outputs in `scripts/run_live_drift.py` with `DiskLiveDriftLoader`.
- Introduced `LiveDriftInputMissingError`.
- Validated correct blocking behavior when inputs are missing.

## What Changed

- `core/live_drift/disk_loader.py` was created to implement `DiskLiveDriftLoader`.
- `core/live_drift/drift_errors.py` was added to hold custom domain errors.
- `scripts/run_live_drift.py` was refactored to require a `--strategy` flag and load using `DiskLiveDriftLoader`.

## What Did Not Change

- Drift logic, baseline rules, or snapshot parsing mechanics.
- The downstream `StrategyCertificationReport` generator was untouched.
- Core broker, risk, execution, or execution contracts remain completely unaffected.

## Tests and Evidence

Tests proving disk loading:
- `tests/live_drift/test_disk_loader.py` covering success and failure pathways.

Run `PYTHONPATH=. pytest tests/live_drift/test_disk_loader.py` to confirm.

## What Could Still Fail

- If downstream pipelines run `run_live_drift.py` without proper inputs being populated beforehand, it will block with `LiveDriftInputMissingError` (which is the desired failure mode).
