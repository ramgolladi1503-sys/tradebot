# Code Excellence Architecture Contract

## Purpose

The Code Excellence system exists to turn repo-forensics findings into disciplined root-cause analysis, safe remediation plans, and production-grade proof.

Repo forensics answers:

```text
What looks risky, weak, missing, duplicated, unsafe, or unproven?
```

Code Excellence answers:

```text
Why is it happening?
What is the smallest safe fix?
What proof is required?
Did the fix improve stability without weakening safety?
```

This system is mandatory for future TradeBot product work, fixes, refactors, and cleanup PRs unless explicitly waived.

## Operating Principle

Do not turn findings into blind patches.

Every meaningful fix must pass through:

1. Scope and Intent Gate
2. Truth and Root-Cause Gate
3. Hardening and Proof Gate

## Agent Roles

### Ariadne — Root-Cause Analysis

Ariadne clusters symptoms into likely root causes.

Ariadne must answer:

- What symptom was observed?
- What evidence proves the symptom exists?
- Which modules/logs/tests are related?
- Is this one bug or a family of bugs?
- What is the likely root cause?
- What is not yet proven?

Ariadne must not:

- propose broad rewrites
- patch code directly
- blame vague architecture without evidence
- treat a test failure as the root cause by itself

### Daedalus — Remediation Planning

Daedalus turns root cause into a safe implementation plan.

Daedalus must answer:

- What is the smallest safe fix?
- Which files should change?
- Which files must not change?
- What risks could the fix introduce?
- What tests/evidence prove the fix?
- What fallback or rollback path exists?

Daedalus must not:

- auto-fix
- rewrite unrelated modules
- loosen safety gates
- hide failures behind silent fallbacks

### Vulcan — Production Hardening

Vulcan verifies that the proposed fix is production-grade.

Vulcan must check:

- deterministic behavior
- explicit failure handling
- safe defaults
- no hidden broker/live/order side effects
- clear evidence contracts
- no fake happy-path-only tests
- no weakening of existing contracts

Vulcan must not:

- approve cosmetic fixes as production hardening
- approve unproven profitability claims
- approve runtime/live behavior changes without explicit scope

### Minerva — Test Reality Hardening

Minerva validates test quality.

Minerva must classify tests as:

- contract tests
- regression tests
- negative tests
- edge-case tests
- integration tests
- fake-confidence tests
- mock-only tests

Minerva must block:

- tests that only assert shape
- tests that update expectations to match broken behavior
- tests that mock the risk away
- tests that weaken a previous safety proof

### Cerberus — Safety Regression Protection

Cerberus protects trading safety boundaries.

Cerberus must check:

- no broker call leakage
- no live order action leakage
- no paper/SIM/LIVE boundary drift
- no fallback contract becoming executable
- no stale feed becoming executable
- no queue-only candidate becoming executable
- no dashboard/read-only path gaining order action behavior

Cerberus must block anything that risks accidental execution.

## Mandatory Gates

### Gate 1 — Scope and Intent Gate

The PR must state one clear problem and one bounded outcome.

Blocks:

- random cleanup
- vague refactors
- strategy rewrites disguised as fixes
- dashboard work inside runtime-safety PRs
- broker/live behavior unless explicitly scoped

### Gate 2 — Truth and Root-Cause Gate

The PR must prove the root cause before proposing the fix.

Blocks:

- shallow symptom fixes
- test-only fixes
- suppressing warnings
- changing logs without fixing broken truth
- fixing one visible symptom while leaving the root cause alive

### Gate 3 — Hardening and Proof Gate

The PR must prove the fix with meaningful tests and evidence.

Blocks:

- happy-path-only tests
- fake mocks
- missing negative tests
- missing regression tests
- missing evidence update
- new repo-forensics hard failures

## TradeBot Safety Boundary

Code Excellence must preserve these hard boundaries:

- No real broker calls unless explicitly scoped.
- No live order placement unless explicitly scoped.
- No modify/cancel/exit behavior unless explicitly scoped.
- No credential handling changes unless explicitly scoped.
- No LIVE default behavior.
- Unsafe or unknown behavior must fail closed.
- Read-only scanners must never import or execute TradeBot runtime modules.

## PR Evidence Requirements

Every CE PR must include:

- Agent Work Contract
- Ariadne RCA section when a root cause is involved
- Daedalus remediation plan when implementation is involved
- Vulcan hardening review
- Minerva test reality review
- Cerberus safety review
- Scope Guard
- commands/tests to run
- final evidence summary

Evidence must be committed under:

```text
docs/agent_reviews/
```

## Relationship to Repo Forensics

Repo Forensics is the detection layer.

Code Excellence is the improvement layer.

The correct flow is:

```text
Repo Forensics finding
→ Ariadne RCA
→ Daedalus remediation plan
→ scoped implementation
→ Vulcan hardening
→ Minerva test proof
→ Cerberus safety proof
→ repo-forensics PR gate
→ merge only if safe
```

## Non-Goals

This system does not promise profitability.

It does not replace trading strategy research.

It does not auto-fix code.

It does not auto-merge PRs.

It does not run live trading.

It exists to make fixes safer, more truthful, and harder to fake.
