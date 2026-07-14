# Daedalus Change Rules

## Purpose

These rules define what a remediation plan may change, what it must not change, and when the plan must be blocked.

## Allowed Change Types

### Contract Repair

Allowed when a documented or expected behavior contract is violated.

Examples:

- ensure queue-only state cannot emit executable truth
- ensure fallback contract status is preserved downstream
- ensure stale feed blockers are reflected in readiness evidence

Required proof:

- regression test
- negative test when relevant
- evidence/report update when output changes

### Evidence Repair

Allowed when behavior may be correct but proof is incomplete or ambiguous.

Examples:

- add miss_ing reason field
- add missing source flag
- add explicit actionability status

Required proof:

- evidence contract test
- sample report/log assertion

### Test Reality Repair

Allowed when tests are too weak to prove behavior.

Examples:

- replace shape-only assertion with behavior assertion
- add negative path
- add regression test for a known bug

Required proof:

- test fails before fix or clearly protects documented behavior
- test cannot pass with the broken behavior

### Safety Boundary Repair

Allowed when a read-only, paper, SIM, LIVE, broker, or order boundary is ambiguous.

Examples:

- add explicit guard
- add no-action evidence fields
- block unsafe state before readiness emission

Required proof:

- safety regression test
- repo-forensics PR gate
- explicit no-action evidence

## Forbidden Change Types

### Broad Rewrite

Forbidden unless separately approved.

Bad signs:

- many unrelated files
- unclear behavior delta
- no exact root cause
- tests only updated after rewrite

### Silent Fallback

Forbidden when it hides broken data, broken contracts, or unsafe state.

### Test Weakening

Forbidden when tests are changed to match broken behavior.

### Scope Mixing

Forbidden without explicit justification.

Examples:

- runtime fix plus dashboard redesign
- safety fix plus strategy scoring rewrite
- evidence fix plus broker adapter change

### Risky Behavior Change Without Proof

Forbidden when behavior changes but tests/evidence do not prove the new contract.

## File Scope Rules

A remediation plan must state:

- allowed files
- forbidden files
- expected files
- reason for every file changed

If implementation touches files not listed in the plan, the PR must update the plan or stop.

## Safety Boundary Rules

Any plan touching runtime truth, readiness, broker boundary, or order actionability must include:

- explicit non-actionability proof for blocked states
- proof that read-only paths remain read-only
- proof that fallback or stale data cannot become executable

## Review Rules

Daedalus plans are not approval to merge.

They are approval to implement a scoped patch.

The implemented PR still needs:

- tests
- evidence
- repo-forensics PR gate
- three CE gates
