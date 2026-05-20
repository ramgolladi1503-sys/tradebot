# GSD-FOR-11 — 3-Agent Evidence Integration

## Agent Work Contract

### Scope

Add deterministic 3-agent evidence formatting for the repo-forensics gate.

This PR converts unified runner output into one concise evidence block with Scope Guard, Grill Me, Hermes, and GSD sections. It preserves the low-friction approval model:

```text
many checks internally
one evidence gate externally
```

### Files Changed

- `tools/repo_forensics/agent_evidence.py`
- `tests/test_repo_forensics_agent_evidence.py`
- `docs/agent_reviews/GSD_FOR_11_3_AGENT_EVIDENCE_INTEGRATION.md`

### Hard Boundaries

- No TradeBot runtime imports.
- No broker calls.
- No live runtime execution.
- No dashboard execution.
- No product behavior changes.
- No auto-fix.
- No auto-PR.
- No merge automation.
- No scanner behavior changes.
- No test weakening.

## Approval Batching Model

The evidence formatter keeps the approval model practical:

```text
Before:
Argus approve -> Atlas approve -> Minerva approve -> Cerberus approve -> Evidence approve -> Drift approve -> report approve

After:
Run one local gate -> generate one 3-agent evidence block -> review one summary
```

## What Was Added

- `AgentEvidenceBlock`
- `render_agent_gate_evidence()`
- `render_pr_body_agent_summary()`

Generated sections:

- Gate Summary
- Scope Guard
- Grill Me Review
- Hermes Review
- GSD Review
- final no-runtime/no-broker scope guard

## Grill Me Review

### Challenge

Evidence summaries can become fake confidence if they turn warnings into approval.

### Findings

- Good: hard failures become BLOCKED.
- Good: unknowns become NEEDS REVIEW.
- Good: warnings become PASS WITH WARNINGS.
- Good: summary is deterministic and derived from scanner counts.
- Risk: this PR formats evidence only; it does not run the scanner itself.

### Verdict

PASS — valid for GSD-FOR-11 as deterministic evidence formatting.

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

The formatter consumes `ForensicsRunResult` data only. It does not import or execute TradeBot runtime modules.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] 3-agent evidence formatter added.
- [x] PR-body friendly compact summary added.
- [x] Tests added for required sections, hard-failure blocking behavior, and compact PR summary.
- [x] Next action is clear: GSD-FOR-12 First TradeBot Baseline Audit.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Evidence block formatting.
- Grill Me / Hermes / GSD section generation.
- PR summary formatting.
- Tests for formatter behavior.

### Out of Scope

- Running scanner automatically in PR comments.
- Writing PR comments.
- Auto-fix.
- Auto-PR.
- Runtime execution.
- Broker integration changes.
- Live config changes.
- Scanner behavior changes.

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

PASS — narrow 3-agent evidence formatting implementation.

### Gate 2 — Truth and Root-Cause

PASS — no RCA needed; this PR formats scanner output only and avoids overclaiming.

### Gate 3 — Hardening and Proof

PASS pending CI — tests cover required evidence sections, blocking behavior, and compact PR body summary.

## Test Plan

Targeted:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_agent_evidence.py
```

Broader repo-forensics targeted set:

```bash
PYTHONPATH=. pytest -q tests/test_repo_forensics_config_loader.py tests/test_repo_forensics_cartographer.py tests/test_repo_forensics_runtime_wiring.py tests/test_repo_forensics_critical_module_checker.py tests/test_repo_forensics_test_reality.py tests/test_repo_forensics_safety_boundary.py tests/test_repo_forensics_evidence_auditor.py tests/test_repo_forensics_architecture_drift.py tests/test_repo_forensics_unified_runner.py tests/test_repo_forensics_agent_evidence.py
```

## Final Verdict

PASS pending CI.

## Next PR

GSD-FOR-12 — First TradeBot Baseline Audit

Expected next deliverables:

- run the unified repo-forensics gate on TradeBot
- commit the first baseline report under `docs/repo_forensics/reports/`
- commit generated 3-agent evidence for the baseline
- no target runtime execution
