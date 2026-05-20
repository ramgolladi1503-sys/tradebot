# Example Daedalus Plan — Final Emit Truth Contract

## Metadata

```yaml
remediation_plan_id: CE-DAEDALUS-2026-001
status: example
source_rca_id: CE-RCA-2026-001
related_prs:
  - PR-103
  - PR-104
```

## Problem

### Title

Final emit truth can contradict candidate actionability.

### Root-Cause Summary

Runtime evidence showed executable-looking final emit output for candidates that were queue-only, blocked, or aborted. The final emit layer needed explicit truth labels instead of ambiguous executable wording.

### Affected Contracts

- candidate actionability truth
- final emit truth label
- runtime evidence readability

### Affected Modules

- final emit formatting path
- candidate readiness/evidence path
- tests covering runtime truth consistency

## Scope

### In Scope

- final emit truth label construction
- final emit diagnostic text
- regression tests for queue-only, blocked, and aborted states
- evidence file documenting proof

### Out of Scope

- broker behavior
- strategy scoring
- dashboard UI
- feed subscription
- paper ledger mutation
- profitability logic

### Must Not Touch

- broker adapters
- live order routing
- strategy entry rules
- feed connection code

## Change Plan

### Intended Behavior Change

Final emit must use explicit truth labels:

```text
FINAL_EMIT_EXECUTABLE
FINAL_EMIT_QUEUE_ONLY
FINAL_EMIT_BLOCKED
FINAL_EMIT_ABORTED
FINAL_EMIT_NON_EXECUTABLE
```

A non-executable candidate must never be logged with executable final truth.

### Implementation Steps

1. Add a small helper that maps candidate/actionability state to final emit truth label.
2. Replace ambiguous final emit wording with the helper output.
3. Add regression tests for queue-only, blocked, aborted, and executable cases.
4. Add evidence documenting the truth contract.

## Risk Model

### Product Risks

- final emit output could become incompatible with existing consumers
- evidence wording could confuse operators if labels are inconsistent

### Safety Risks

- non-executable candidate could still appear actionable if one branch bypasses the helper

### Evidence Risks

- tests could assert only label text and miss state/actionability mismatch

### Operational Risks

- logs could become noisier if labels are emitted too often

### Rollback Plan

Revert the final emit truth contract PR while preserving existing safety gates. Do not loosen candidate actionability gates as rollback.

## Proof Plan

### Positive Tests

- executable candidate emits `FINAL_EMIT_EXECUTABLE`

### Negative Tests

- queue-only candidate does not emit executable truth
- blocked candidate does not emit executable truth
- aborted candidate does not emit executable truth

### Regression Tests

- previous queue-only/executable contradiction cannot reappear

### Evidence

- agent review evidence file
- final emit truth contract test output

### Required CI

- targeted runtime truth tests
- repo-forensics PR gate

## Forbidden Shortcuts

- changing only log text without checking candidate state
- deleting final emit evidence
- weakening queue-only/actionability tests
- treating aborted candidate as executable because a price exists

## Acceptance Criteria

- all non-executable final states emit non-executable truth labels
- executable final truth appears only for truly executable candidates
- regression tests fail if queue-only/blocked/aborted candidates emit executable truth
- repo-forensics PR gate passes

## Daedalus Verdict

```yaml
result: pass
reason: Plan is bounded, safety-preserving, and proof requirements target the exact runtime truth contradiction.
```
