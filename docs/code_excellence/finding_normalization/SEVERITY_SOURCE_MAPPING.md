# Severity and Source Mapping

## Purpose

This document defines how raw findings from different sources map into normalized finding severity, confidence, and finding type.

## Source Type Mapping

| Raw Source | Normalized `source_type` |
|---|---|
| GitHub Actions failure | `ci` |
| pytest failure | `test_failure` |
| repo-forensics report | `repo_forensics` |
| runtime log / evidence log | `runtime_log` |
| product reality audit | `product_reality` |
| manual review | `manual_review` |
| live read-only observation | `live_read_only_observation` |

## Severity Mapping

### Critical

Use `critical` when the finding could allow or imply unsafe trading action, broken execution truth, or broker/live boundary ambiguity.

Examples:

- fallback contract reaches executable-looking trace
- stale feed reaches executable readiness
- queue-only candidate appears executable
- broker/live/order action appears in a read-only path
- required safety gate is bypassed

### High

Use `high` when the finding can break product truth, runtime reliability, or future safety proof, but does not directly show action leakage.

Examples:

- runtime wiring failure
- missing critical module caller proof
- missing required evidence fields
- hard repo-forensics failure
- repeated architecture drift in active runtime path

### Medium

Use `medium` when the finding weakens confidence but is not currently safety-critical.

Examples:

- fake-confidence test signal
- status-only evidence
- weak product reality proof
- duplicate module names outside active path

### Low

Use `low` for cleanup or clarity issues with limited product risk.

Examples:

- stale documentation reference
- minor evidence wording ambiguity
- low-risk naming drift

### Info

Use `info` for observations that are useful but not actionable yet.

Examples:

- capability classified as partially proven but no regression detected
- baseline-only known debt with no new delta

## Confidence Mapping

### High Confidence

Use when evidence is direct and repeatable.

Examples:

- failing deterministic test
- CI failure with clear stack trace
- exact runtime log contradiction
- repo-forensics hard failure with affected path

### Medium Confidence

Use when evidence is plausible but incomplete.

Examples:

- architecture drift signal without runtime proof
- dashboard reader drift without broken user-visible behavior
- product reality partial proof

### Low Confidence

Use when evidence is suspicious but weak.

Examples:

- manual review concern without reproduction
- single vague log line
- unknown classification due to missing context

## Finding Type Mapping

| Raw Signal | Normalized Finding Type |
|---|---|
| executable/non-executable disagreement | `contract_violation` |
| truth detected in one layer but missing downstream | `propagation_gap` |
| missing reason/source/actionability fields | `evidence_gap` |
| mock-only or shape-only test | `test_reality_gap` |
| broker/live/order boundary ambiguity | `safety_boundary_gap` |
| duplicate old/new implementation paths | `architecture_drift` |
| stale/fallback/missing market data | `data_quality_gap` |
| missing validation/runbook/evidence step | `operational_gap` |

## Source-Specific Rules

### CI

CI failures should preserve:

- workflow name
- job name
- failing command
- failing test if available
- commit SHA

Default severity:

- critical if safety gate fails
- high if required CI fails
- medium if optional/non-blocking check fails

### Repo Forensics

Repo-forensics findings should preserve:

- report path
- section name
- severity
- affected path
- baseline delta when available

Mapping:

- safety critical → critical
- evidence high → high
- drift high → high
- fake-confidence tests → medium
- unknowns → medium unless safety-related

### Runtime Logs

Runtime log findings should preserve:

- log file
- event name
- timestamp if available
- symbol/candidate id if available
- contradictory fields

Runtime truth contradictions are at least high severity and become critical if actionability is unclear.

### Product Reality Audit

Product reality findings map as:

| Product Reality Status | Default Severity |
|---|---|
| PROVEN | info |
| PARTIALLY_PROVEN | medium |
| THEORETICAL | medium |
| MOCKED | high if capability is safety/runtime-related, else medium |
| UNPROVEN | high if capability is safety/runtime-related, else medium |

### Test Failure

Test failures should preserve:

- test file
- test name
- assertion or error
- expected behavior
- observed behavior
- whether test is contract/regression/negative/mock-only

A failed safety regression test is critical.

A failed contract test is high unless the contract is safety-critical, then critical.

## Escalation Rules

Escalate severity to critical if any of these are true:

- broker/live/order boundary is unclear
- executable truth is contradicted
- stale/fallback data reaches actionability
- queue-only state appears actionable
- safety gate is bypassed

Escalate severity to high if any of these are true:

- finding repeats across sources
- root cause is unknown
- evidence is missing for a critical product capability
- runtime wiring is unproven

## De-escalation Rules

Only de-escalate when evidence proves lower risk.

Do not de-escalate because:

- the failure is intermittent
- the code path is believed to be rare
- the issue has not caused a live order yet
- the test is inconvenient

## Baseline Rule

Existing baseline debt is still debt.

However, future PR gates should distinguish:

```text
known baseline finding
```

from:

```text
new regression introduced by current PR
```

New regressions must be treated more strictly than unchanged baseline debt.
