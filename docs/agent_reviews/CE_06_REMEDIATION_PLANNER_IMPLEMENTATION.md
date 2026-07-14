# CE-06 — Remediation Planner Implementation

## Agent Work Contract

### Purpose

Implement a deterministic Daedalus remediation planner that converts Ariadne clusters or normalized findings into bounded remediation plans.

The planner is read-only. It does not mutate product code, auto-fix, auto-open implementation PRs, execute runtime flows, or call brokers.

### Files Changed

- `tools/code_excellence/remediation_planner.py`
- `scripts/run_daedalus_planner.py`
- `tests/test_code_excellence_remediation_planner.py`
- `docs/agent_reviews/CE_06_REMEDIATION_PLANNER_IMPLEMENTATION.md`

### In Scope

- Load normalized findings or Ariadne cluster input from JSON.
- Reuse CE-04 Ariadne clustering when normalized findings are provided.
- Consume CE-05B `load_code_excellence_agent_parameters()`.
- Use configured Daedalus decisions and block rules.
- Emit deterministic remediation plans with:
  - decision
  - priority
  - files_to_change
  - files_not_to_touch
  - patch_behavior
  - tests_required
  - negative_tests_required
  - evidence_required
  - regression_risks
  - done_means
  - proof_required
- Write a Markdown report through a CLI.
- Add deterministic fail-closed tests.

### Out of Scope

- No implementation patch generation.
- No code mutation.
- No auto-fix.
- No auto-PR.
- No product code changes.
- No broker calls.
- No live runtime execution.
- No dashboard changes.
- No strategy changes.
- No baseline debt cleanup.
- No changes to repo-forensics gate behavior.

## Gate 1 — Scope and Intent

PASS.

The implementation is limited to a planning layer. It produces remediation plan reports only.

## Gate 2 — Truth and Root-Cause

PASS.

The planner blocks weak remediation candidates when the configured Daedalus block rules detect missing root cause, broad file scope, missing file scope, or safety/runtime issues without root-cause proof.

The planner does not pretend unknowns are fixable. Weak RCA becomes `ACCEPTED_UNKNOWN` and blocked plan status.

## Gate 3 — Hardening and Proof

PASS pending CI.

Tests cover:

- normalized finding input routed through Ariadne clustering
- FIX_NOW plan generation from high-confidence RCA
- blocked plan generation when root cause is missing
- deterministic cluster ordering and plan IDs
- empty source rejection
- fail-closed behavior when required Daedalus decision config is missing

## Grill Me Review

### Challenge

A remediation planner can become fake precision if it turns every finding into a fix.

### Findings

- Good: unknown or blocked root cause does not get an implementation patch.
- Good: planner consumes configured Daedalus and Minerva/Cerberus parameters instead of hardcoding all proof rules.
- Good: files_not_to_touch is generated from configured entrypoints and critical modules.
- Good: normalized findings reuse Ariadne clustering instead of creating a second clustering path.
- Risk: the planner is only as good as the upstream normalized finding quality.
- Risk: first version emits conservative proof plans, not detailed implementation steps.

### Verdict

PASS for CE-06.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No broker behavior changed.
- [x] No live runtime behavior changed.
- [x] No dashboard behavior changed.
- [x] No strategy behavior changed.
- [x] No auto-fix introduced.
- [x] No auto-PR introduced.
- [x] No test weakening.

### Boundary Risk

The new script reads JSON and writes Markdown only. It does not import trading runtime modules.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Planner module added.
- [x] CLI added.
- [x] Tests added.
- [x] Agent evidence added.
- [x] CE-05B parameter bridge consumed.
- [x] CE-04 Ariadne clustering reused for normalized finding input.

### Test Command

```bash
PYTHONPATH=. pytest -q tests/test_code_excellence_remediation_planner.py
```

### Required CI

```text
repo-forensics-pr-gate
```

### Verdict

PASS pending CI.

## Scope Guard

### Files Allowed

- `tools/code_excellence/remediation_planner.py`
- `scripts/run_daedalus_planner.py`
- `tests/test_code_excellence_remediation_planner.py`
- `docs/agent_reviews/CE_06_REMEDIATION_PLANNER_IMPLEMENTATION.md`

### Files Not Touched

- product runtime modules
- broker modules
- strategy modules
- dashboard modules
- repo-forensics gate implementation
- existing evidence schemas

## Final Verdict

PASS pending CI.

## Next PR

CE-07 — Vulcan Production Hardening Template.

Do not jump into actual remediation patches yet. CE-06 only plans remediation; it does not authorize product fixes by itself.


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
