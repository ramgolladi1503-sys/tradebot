# GSD-FOR-05 — Critical Module Caller Check

## Agent Work Contract

### Scope

Add a static critical-module caller checker to the existing repo-forensics gate.

This PR extends the single local runner so it can build a static import/reference graph, classify configured critical modules by caller strength, and report whether each critical module is production-referenced, test-only, unreferenced, or missing.

### Files Changed

- `tools/repo_forensics/import_graph.py`
- `tools/repo_forensics/critical_module_checker.py`
- `tools/repo_forensics/report_writer.py`
- `scripts/run_repo_forensics.py`
- `tests/test_repo_forensics_critical_module_checker.py`
- `docs/agent_reviews/GSD_FOR_05_CRITICAL_MODULE_CALLER_CHECK.md`

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
3. Critical Module Caller Check
4. Report Writer

## Grill Me Review

### Challenge

A static caller check can overclaim runtime truth. A reference proves only that code mentions/imports a module, not that the live runtime executes it.

### Findings

- Good: statuses distinguish production-referenced from test-only and unreferenced.
- Good: report labels unreferenced modules as UNKNOWN rather than PASS.
- Good: missing/test-only critical modules fail the gate.
- Risk: deeper runtime reachability from entrypoints is still limited. Future PRs can improve precision.

### Verdict

PASS — valid for GSD-FOR-05. Do not treat as full execution proof.

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

The checker parses source files as text/AST. It does not import or execute TradeBot runtime modules.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Static reference graph added.
- [x] Critical module caller checker added.
- [x] Report writer includes caller status section.
- [x] Existing runner invokes cartography + wiring + caller checks together.
- [x] Tests added.
- [x] Next action is clear: GSD-FOR-06 Test Reality Classifier.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Static import/reference graph.
- Critical module caller status.
- Production vs test-only vs unreferenced vs missing classification.
- Runner integration.
- Report integration.
- Tests for classification behavior.

### Out of Scope

- Full runtime reachability proof.
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

PASS — narrow critical module caller check implementation.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR extends static inspection only and avoids overclaiming.

### Gate 3 — Hardening and Proof

PASS pending CI — tests cover production-referenced, test-only, unreferenced, and missing critical module classification.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_config_loader.py tests/test_repo_forensics_cartographer.py tests/test_repo_forensics_runtime_wiring.py tests/test_repo_forensics_critical_module_checker.py
```

Manual scanner command:

```bash
python scripts/run_repo_forensics.py --repo . --config .gsd-forensics.yaml
```

## Final Verdict

PASS pending CI.

## Next PR

GSD-FOR-06 — Test Reality Classifier

Expected next deliverables:

- test file classifier
- shape-only vs behavior/safety/evidence categories
- fake-confidence test detection
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
