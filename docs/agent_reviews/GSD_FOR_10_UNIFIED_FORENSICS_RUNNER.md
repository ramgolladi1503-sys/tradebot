# GSD-FOR-10 — Unified Forensics Runner

## Agent Work Contract

### Scope

Add a reusable unified runner service for the repo-forensics gate.

This PR introduces a single orchestration module that runs the existing static scanners, writes the report, computes stable summary counts, applies a stable exit policy, and renders PR-friendly summary output.

### Files Changed

- `tools/repo_forensics/unified_runner.py`
- `tests/test_repo_forensics_unified_runner.py`
- `docs/agent_reviews/GSD_FOR_10_UNIFIED_FORENSICS_RUNNER.md`

### Hard Boundaries

- No TradeBot runtime imports.
- No broker calls.
- No live runtime execution.
- No dashboard execution.
- No product behavior changes.
- No auto-fix.
- No auto-PR.
- No evidence mutation beyond the requested report output path.
- No merge automation.
- No test weakening.

## Approval Batching Model

This continues the low-friction model:

```text
many checks internally
one local gate externally
```

The reusable service now centralizes:

1. scanner toggles
2. scanner orchestration
3. summary counts
4. verdict calculation
5. exit policy
6. PR-friendly summary output

## What Changed

Added:

- `ForensicsCheckToggles`
- `ForensicsCounts`
- `ForensicsRunResult`
- `ForensicsReports`
- `run_forensics()`
- `render_pr_summary()`

Exit policies:

- `strict`
- `report-only`

## Grill Me Review

### Challenge

A unified runner can become an overengineered abstraction if it changes behavior or hides scanner failures.

### Findings

- Good: this PR does not add new scanner behavior.
- Good: hard failures remain explicit in `ForensicsCounts.hard_failures`.
- Good: unknowns and warnings are separated from hard failures.
- Good: report-only mode is explicit and tested.
- Risk: the existing CLI wrapper is not fully migrated in this PR because connector-side update attempts were blocked. The service is still useful and test-covered.

### Verdict

PASS — valid for GSD-FOR-10 as a runner-service consolidation PR. Do not claim full CLI cleanup beyond the added service.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No broker imports introduced.
- [x] No live behavior introduced.
- [x] No dashboard behavior introduced.
- [x] No scanner behavior changed.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Safety Verification

The unified runner calls only existing repo-forensics scanners. Those scanners are static/read-only and do not import or execute TradeBot runtime modules.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Unified runner service added.
- [x] Stable count model added.
- [x] Stable verdict model added.
- [x] Stable exit policy added.
- [x] PR-friendly summary renderer added.
- [x] Tests added for report generation, summary output, strict/report-only exit behavior, and count grouping.
- [x] Next action is clear: GSD-FOR-11 3-Agent Evidence Integration.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Unified runner service.
- Summary count model.
- Exit policy model.
- PR summary renderer.
- Tests for runner behavior.

### Out of Scope

- Adding new scanners.
- Changing scanner logic.
- Full CLI cleanup if connector blocks it.
- Runtime execution.
- Broker integration changes.
- Live config changes.
- Auto-fix.
- Auto-PR.
- Trade quality intelligence.

### Boundary Verification

- [x] No broker calls.
- [x] No live runtime execution.
- [x] No target runtime imports.
- [x] No scanner behavior changes.
- [x] No auto-fix.
- [x] No auto-PR.
- [x] No merge automation.

## 3-Gate Result

### Gate 1 — Scope and Intent

PASS — narrow unified runner service implementation.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR consolidates orchestration only and avoids overclaiming.

### Gate 3 — Hardening and Proof

PASS pending CI — tests cover report generation, summary output, exit policy, and count grouping.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_unified_runner.py
```

Broader repo-forensics targeted set:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_config_loader.py tests/test_repo_forensics_cartographer.py tests/test_repo_forensics_runtime_wiring.py tests/test_repo_forensics_critical_module_checker.py tests/test_repo_forensics_test_reality.py tests/test_repo_forensics_safety_boundary.py tests/test_repo_forensics_evidence_auditor.py tests/test_repo_forensics_architecture_drift.py tests/test_repo_forensics_unified_runner.py
```

## Final Verdict

PASS pending CI.

## Next PR

GSD-FOR-11 — 3-Agent Evidence Integration

Expected next deliverables:

- one generated agent-gate evidence summary format
- Grill Me / Hermes / GSD sections from scanner output
- PR-body friendly evidence block
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
