# GSD-FOR-09 — Architecture Drift Detector

## Agent Work Contract

### Scope

Add a static architecture drift detector to the existing repo-forensics gate.

This PR extends the single local runner so it can flag duplicate/stale/conflicting implementation signals, old/new pipeline splits, dashboard evidence-reader drift, and documentation references to missing critical modules.

### Files Changed

- `tools/repo_forensics/architecture_drift.py`
- `tools/repo_forensics/report_writer.py`
- `scripts/run_repo_forensics.py`
- `tests/test_repo_forensics_architecture_drift.py`
- `docs/agent_reviews/GSD_FOR_09_ARCHITECTURE_DRIFT_DETECTOR.md`

### Hard Boundaries

- No TradeBot runtime imports.
- No broker calls.
- No live runtime execution.
- No dashboard execution.
- No product behavior changes.
- No auto-fix.
- No auto-PR.
- No deletion of stale paths.
- No merge automation.
- No test weakening.

## Approval Batching Model

This continues the low-friction model:

```text
many checks internally
one local gate externally
```

Single command:

```bash
python scripts/run_repo_forensics.py --repo . --config .gsd-forensics.yaml
```

The command now runs:

1. Repo Cartographer
2. Runtime Wiring Auditor
3. Critical Module Caller Check
4. Test Reality Classifier
5. Safety Boundary Auditor
6. Evidence Auditor
7. Architecture Drift Detector
8. Report Writer

## Drift Checks Added

The scanner flags:

- duplicate module stems in configured watch areas
- old/new pipeline split signals
- documentation references to missing critical modules
- dashboard evidence-reader paths that do not reference configured evidence paths
- dashboard existence without evidence-reader signal

## Grill Me Review

### Challenge

Architecture drift detection is heuristic and can produce false positives. It must not delete or rewrite anything automatically.

### Findings

- Good: scanner reports drift only.
- Good: no stale path deletion or auto-remediation is included.
- Good: drift is mostly MEDIUM/UNKNOWN unless it becomes directly safety/runtime blocking elsewhere.
- Risk: duplicate names can be legitimate. Future Ariadne/Daedalus flow must triage before remediation.

### Verdict

PASS — valid for GSD-FOR-09 as static drift detection.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No broker imports introduced.
- [x] No live behavior introduced.
- [x] No dashboard behavior introduced.
- [x] No runtime scripts changed except local forensics runner.
- [x] No stale-path deletion.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Safety Verification

The detector reads files only. It does not import or execute TradeBot runtime modules and does not call any broker APIs.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Architecture drift detector added.
- [x] Report writer includes architecture drift section.
- [x] Existing runner invokes cartography + wiring + caller checks + test reality + safety + evidence + drift together.
- [x] Tests added for duplicate module stems, old/new pipeline split, and dashboard evidence-reader drift.
- [x] Next action is clear: GSD-FOR-10 Unified Forensics Runner.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Static architecture drift scan.
- Duplicate/stale/conflicting path detection.
- Dashboard evidence-reader drift signal.
- Runner integration.
- Report integration.
- Tests for drift behavior.

### Out of Scope

- Deleting stale files.
- Rewriting runtime paths.
- Canonical owner decisions.
- Runtime execution.
- Broker integration changes.
- Live config changes.
- Auto-fix.
- Ariadne/Daedalus/Vulcan implementation.
- Trade quality intelligence.

### Boundary Verification

- [x] No broker calls.
- [x] No live runtime execution.
- [x] No target runtime imports.
- [x] No stale-path deletion.
- [x] No auto-fix.
- [x] No auto-PR.
- [x] No merge automation.

## 3-Gate Result

### Gate 1 — Scope and Intent

PASS — narrow architecture drift detector implementation.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR detects static drift only and avoids overclaiming.

### Gate 3 — Hardening and Proof

PASS pending CI — tests cover duplicate module stems, old/new split, and dashboard evidence-reader drift.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_config_loader.py tests/test_repo_forensics_cartographer.py tests/test_repo_forensics_runtime_wiring.py tests/test_repo_forensics_critical_module_checker.py tests/test_repo_forensics_test_reality.py tests/test_repo_forensics_safety_boundary.py tests/test_repo_forensics_evidence_auditor.py tests/test_repo_forensics_architecture_drift.py
```

Manual scanner command:

```bash
python scripts/run_repo_forensics.py --repo . --config .gsd-forensics.yaml
```

## Final Verdict

PASS pending CI.

## Next PR

GSD-FOR-10 — Unified Forensics Runner

Expected next deliverables:

- cleaner command modes
- stable exit policy
- consolidated latest report naming
- PR-friendly summary output
- no target runtime execution


## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
