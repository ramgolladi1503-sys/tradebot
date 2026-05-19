# GSD-FOR-04 — Entrypoint and Runtime Wiring Audit

## Agent Work Contract

### Scope

Add a static runtime wiring auditor to the existing repo-forensics gate.

This PR extends the single local runner so it can read configured runtime flows from `.gsd-forensics.yaml`, check whether configured files/modules/symbols are statically present, and include a runtime wiring table in the Markdown report.

### Files Changed

- `tools/repo_forensics/config_loader.py`
- `tools/repo_forensics/runtime_wiring.py`
- `tools/repo_forensics/report_writer.py`
- `scripts/run_repo_forensics.py`
- `tests/test_repo_forensics_runtime_wiring.py`
- `docs/agent_reviews/GSD_FOR_04_RUNTIME_WIRING_AUDIT.md`

### Hard Boundaries

- No TradeBot runtime imports.
- No broker calls.
- No live runtime execution.
- No dashboard execution.
- No product behavior changes.
- No auto-fix.
- No auto-PR.
- No merge automation.

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
3. Report Writer

## Grill Me Review

### Challenge

Static reference checks can overclaim runtime truth. A symbol existing does not prove the exact runtime path executes it.

### Findings

- Good: statuses are limited to PASS / FAIL / UNKNOWN.
- Good: report still states this is static proof only.
- Good: missing modules fail; unproven symbols become UNKNOWN.
- Risk: deeper caller-chain proof is still not implemented. That belongs to GSD-FOR-05.

### Verdict

PASS — valid for GSD-FOR-04. Do not treat as execution proof.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No broker imports introduced.
- [x] No live behavior introduced.
- [x] No dashboard behavior introduced.
- [x] No runtime scripts changed except local forensics runner.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Safety Verification

The auditor parses source files as text/AST. It does not import or execute TradeBot runtime modules.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Runtime flow config exposed.
- [x] Runtime wiring auditor added.
- [x] Report writer includes runtime wiring section.
- [x] Existing runner invokes cartography + wiring checks together.
- [x] Tests added.
- [x] Next action is clear: GSD-FOR-05 Critical Module Caller Check.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Static runtime-flow reference checks.
- Flow table in report.
- Runner integration.
- Tests for configured flows and missing module failure.

### Out of Scope

- Full import graph reachability.
- Critical module caller proof.
- Test reality classifier.
- Safety boundary scanner.
- Evidence auditor.
- Architecture drift detector.
- Ariadne/Daedalus/Vulcan implementation.
- Trade quality intelligence.

### Boundary Verification

- [x] No broker calls.
- [x] No live runtime execution.
- [x] No target runtime imports.
- [x] No auto-fix.
- [x] No auto-PR.
- [x] No merge automation.

## 3-Gate Result

### Gate 1 — Scope and Intent

PASS — narrow runtime wiring audit implementation.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR extends static inspection only and avoids overclaiming.

### Gate 3 — Hardening and Proof

PASS pending CI — tests cover configured TradeBot flows and missing module failure.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_config_loader.py tests/test_repo_forensics_cartographer.py tests/test_repo_forensics_runtime_wiring.py
```

Manual scanner command:

```bash
python scripts/run_repo_forensics.py --repo . --config .gsd-forensics.yaml
```

## Final Verdict

PASS pending CI.

## Next PR

GSD-FOR-05 — Critical Module Caller Check

Expected next deliverables:

- static import/reference graph
- critical module caller status
- test-only vs production caller classification
- no target runtime execution
