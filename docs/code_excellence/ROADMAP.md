# Code Excellence Roadmap

## Status

This roadmap starts after completion of the GSD-FOR repo-forensics foundation.

Completed foundation:

```text
GSD-FOR-01 through GSD-FOR-14
GSD-FOR-12B baseline artifacts
GSD-FOR-15 CI required repo-forensics PR gate
main branch protection requiring repo-forensics-pr-gate
```

## Roadmap

### CE-01 — Code Excellence Architecture Contract

Define the Code Excellence architecture, agent roles, gates, safety boundaries, and evidence requirements.

Deliverables:

- architecture contract
- CE roadmap
- gate contract
- agent evidence file

No implementation beyond documentation.

### CE-02 — Ariadne RCA Template and Contract

Define the root-cause analysis template.

Deliverables:

- RCA template
- root-cause evidence schema
- symptom/finding/source mapping rules
- example RCA for a known TradeBot issue

### CE-03 — Finding Normalization Contract

Define a common normalized finding model across repo-forensics outputs, runtime logs, test failures, CI failures, and product reality findings.

Deliverables:

- finding schema
- severity mapping
- source mapping
- deduplication rules
- tests for schema normalization

### CE-04 — Ariadne Root-Cause Clustering Engine

Implement deterministic clustering of normalized findings into likely root-cause groups.

Deliverables:

- clustering engine
- grouping by module, symptom, boundary, evidence source, and safety risk
- tests for deterministic clustering
- no auto-fix

### CE-05 — Daedalus Remediation Template and Contract

Define the remediation planning template.

Deliverables:

- remediation plan template
- allowed/forbidden change rules
- risk model
- proof plan requirements

### CE-06 — Remediation Planner Implementation

Implement deterministic remediation plan generation from root-cause clusters.

Deliverables:

- planner module
- output report
- tests for plan generation
- no code mutation
- no auto-fix

### CE-07 — Vulcan Production Hardening Template

Define production hardening checks for proposed fixes.

Deliverables:

- hardening checklist
- failure-handling checklist
- deterministic-behavior checklist
- evidence contract checklist

### CE-08 — Minerva Test Reality Hardening Gate

Add a test-quality hardening gate that classifies whether proposed tests prove real behavior.

Deliverables:

- test hardening report
- fake-confidence blocker rules
- negative/edge/regression test requirements
- tests for the gate itself

### CE-09 — Cerberus Safety Regression Gate

Add a safety regression gate for broker/live/order boundaries and read-only/runtime separation.

Deliverables:

- safety regression report
- broker/live/order leakage checks
- fallback/stale/queue-only executable contradiction checks
- tests for safety regression rules

### CE-10 — Code Excellence Evidence Bundle

Create a bundled evidence output that combines Ariadne, Daedalus, Vulcan, Minerva, Cerberus, and repo-forensics PR gate results.

Deliverables:

- evidence bundle schema
- Markdown report writer
- PR summary block
- tests for report generation

### CE-11 — First Code Excellence Baseline Review

Run the CE process against the current TradeBot repo-forensics baseline and produce the first CE baseline review.

Deliverables:

- baseline CE report
- top root-cause clusters
- first remediation priorities
- no product code changes

### CE-12 — Future PR Code Excellence Gate

Add a future PR gate that requires CE evidence for meaningful fixes/refactors.

Deliverables:

- CE PR gate command
- CI-friendly summary
- baseline-aware policy
- no auto-fix
- no auto-merge

## Mandatory Sequencing

Do not skip ahead.

The correct order is:

```text
contracts → normalization → RCA clustering → remediation planning → hardening gates → evidence bundle → baseline review → PR gate
```

## Hard Constraints

Every CE PR must preserve:

- no broker calls
- no live order actions
- no runtime execution unless explicitly scoped
- no auto-fix
- no auto-PR
- no merge automation
- no product behavior changes unless the PR explicitly scopes them
- no weakening existing tests
- no hiding failures
- no broad refactors

## Definition of Done

A CE PR is done only when:

- scope is narrow
- evidence file exists under `docs/agent_reviews/`
- three gates are explicitly addressed
- repo-forensics PR gate passes
- CI passes
- no new hard failures are introduced
