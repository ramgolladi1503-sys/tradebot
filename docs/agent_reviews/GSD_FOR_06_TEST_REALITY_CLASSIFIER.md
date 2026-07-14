# GSD-FOR-06 — Test Reality Classifier

## Agent Work Contract

### Scope

Add a static test-reality classifier to the existing repo-forensics gate.

This PR extends the single local runner so it can classify test files into proof-strength categories and flag fake-confidence/unknown tests for review.

### Files Changed

- `tools/repo_forensics/test_reality.py`
- `tools/repo_forensics/report_writer.py`
- `scripts/run_repo_forensics.py`
- `tests/test_repo_forensics_test_reality.py`
- `docs/agent_reviews/GSD_FOR_06_TEST_REALITY_CLASSIFIER.md`

### Hard Boundaries

- No TradeBot runtime imports.
- No broker calls.
- No live runtime execution.
- No dashboard execution.
- No product behavior changes.
- No auto-fix.
- No auto-PR.
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
5. Report Writer

## Classifier Categories

- `SHAPE_ONLY`
- `UNIT_BEHAVIOR`
- `INTEGRATION_WIRING`
- `SAFETY_REGRESSION`
- `RUNTIME_COMMAND`
- `EVIDENCE_CONTRACT`
- `FAKE_CONFIDENCE`
- `UNKNOWN`

## Grill Me Review

### Challenge

Static classification can mislabel tests. It should not pretend to understand every assertion perfectly.

### Findings

- Good: fake-confidence and unknown tests are warnings for review, not automatic code edits.
- Good: safety/evidence/runtime markers create stronger categories.
- Good: shape-only and weak patterns are surfaced instead of hidden.
- Risk: classifier is heuristic. It should guide review, not replace human judgment.

### Verdict

PASS — valid for GSD-FOR-06 as a first static classifier.

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

The classifier parses test files as text/AST. It does not import or execute TradeBot runtime modules.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Test reality classifier added.
- [x] Report writer includes test reality section.
- [x] Existing runner invokes cartography + wiring + caller checks + test reality together.
- [x] Tests added for shape/fake-confidence, safety, evidence, behavior, and unknown categories.
- [x] Next action is clear: GSD-FOR-07 Safety Boundary Auditor.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Static test classification.
- Fake-confidence signal detection.
- Unknown test signal detection.
- Runner integration.
- Report integration.
- Tests for classifier behavior.

### Out of Scope

- Running all tests.
- Rewriting tests.
- Weakening tests.
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

PASS — narrow test reality classifier implementation.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR classifies proof strength only and avoids overclaiming.

### Gate 3 — Hardening and Proof

PASS pending CI — tests cover classifier categories and unknown behavior.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_config_loader.py tests/test_repo_forensics_cartographer.py tests/test_repo_forensics_runtime_wiring.py tests/test_repo_forensics_critical_module_checker.py tests/test_repo_forensics_test_reality.py
```

Manual scanner command:

```bash
python scripts/run_repo_forensics.py --repo . --config .gsd-forensics.yaml
```

## Final Verdict

PASS pending CI.

## Next PR

GSD-FOR-07 — Safety Boundary Auditor

Expected next deliverables:

- SIM/PAPER/LIVE static boundary scan
- forbidden broker/action pattern detection
- read-only action-field checks
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
