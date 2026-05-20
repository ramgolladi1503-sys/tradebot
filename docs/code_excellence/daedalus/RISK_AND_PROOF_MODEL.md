# Daedalus Risk and Proof Model

## Purpose

Every remediation plan must identify risk before implementation and define proof before code is changed.

A fix without proof is not a fix. It is a guess.

## Risk Categories

### Product Risk

How the change could make TradeBot product behavior worse.

Examples:

- candidate readiness becomes less reliable
- ranking evidence becomes harder to trace
- runtime output becomes ambiguous
- dashboard sees stale or contradictory state

### Safety Risk

How the change could weaken safety boundaries.

Examples:

- blocked candidate becomes actionable
- fallback contract appears tradable
- stale feed reaches readiness
- read-only path gains action-like behavior

### Evidence Risk

How the change could weaken proof.

Examples:

- reason fields are dropped
- source flags are not emitted
- validator cannot distinguish blocked vs executable
- report shape changes without tests

### Operational Risk

How the change could make operation harder.

Examples:

- logs become noisy
- validator output becomes harder to interpret
- runbook step changes without documentation
- CI becomes flaky or slow

## Risk Rating

Use:

```text
low
medium
high
critical
```

### Critical

Use when safety/actionability truth is at risk.

### High

Use when runtime correctness or proof is at risk.

### Medium

Use when confidence or maintainability is weakened.

### Low

Use for isolated, easily reversible changes.

## Proof Requirements by Risk

### Critical Risk

Required:

- regression test for exact issue
- negative test for unsafe path
- positive test for safe path
- evidence/report assertion
- safety review
- repo-forensics PR gate

### High Risk

Required:

- regression test
- behavior test
- evidence assertion if output changes
- repo-forensics PR gate

### Medium Risk

Required:

- focused unit or contract test
- evidence update if docs/reports change

### Low Risk

Required:

- basic validation or documentation proof

## Proof Quality Rules

Good proof:

- fails on the broken behavior
- checks behavior, not only shape
- includes negative path when risk exists
- preserves previous safety contracts
- is deterministic

Weak proof:

- only checks that a key exists
- mocks away the risky path
- asserts the new implementation detail instead of behavior
- updates snapshots without explaining behavior

## Acceptance Criteria Rules

Acceptance criteria must be measurable.

Bad:

```text
Improve reliability.
```

Good:

```text
A fallback-resolved contract always emits execution_allowed=false and final_action=QUEUE_ONLY.
```

Bad:

```text
Make tests better.
```

Good:

```text
Add a regression test that fails if queue-only candidate final emit contains executable truth.
```

## Rollback / Revert Plan

Every remediation plan must describe how to back out safely.

Acceptable rollback options:

- revert PR
- disable new evidence field usage while keeping old fields
- keep backward-compatible output
- leave strict safety gate in place

Unacceptable rollback options:

- loosen safety gate
- ignore validator failure
- delete failing test
- remove evidence field without replacement

## Minimum Proof Matrix

| Change Type | Positive Test | Negative Test | Regression Test | Evidence Assertion | Safety Review |
|---|---:|---:|---:|---:|---:|
| Contract repair | yes | when relevant | yes | when output changes | when safety-related |
| Evidence repair | yes | no | when bug exists | yes | when actionability-related |
| Test reality repair | yes | when relevant | yes | no | when safety-related |
| Safety boundary repair | yes | yes | yes | yes | yes |
