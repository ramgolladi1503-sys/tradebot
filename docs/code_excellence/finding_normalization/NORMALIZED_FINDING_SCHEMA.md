# Normalized Finding Schema

## Purpose

The normalized finding schema gives Ariadne, Daedalus, Vulcan, Minerva, and Cerberus one shared language for findings.

Without normalization, TradeBot findings stay scattered across CI failures, repo-forensics reports, runtime logs, product reality audits, manual reviews, and tests. That creates duplicate work and shallow fixes.

## Normalized Finding Record

```yaml
finding_id: CE-FINDING-YYYY-NNN
schema_version: 1
status: open | triaged | accepted | remediated | deferred | rejected | superseded
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD

source:
  source_type: ci | repo_forensics | runtime_log | test_failure | product_reality | manual_review | live_read_only_observation
  source_name: ""
  source_path: ""
  source_ref: ""
  source_timestamp: ""

classification:
  finding_type: contract_violation | propagation_gap | evidence_gap | test_reality_gap | safety_boundary_gap | architecture_drift | data_quality_gap | operational_gap | unknown
  severity: critical | high | medium | low | info
  confidence: high | medium | low
  root_cause_family: ""

summary:
  title: ""
  description: ""
  observed_behavior: ""
  expected_behavior: ""

location:
  files: []
  functions: []
  tests: []
  reports: []
  logs: []

impact:
  product_risk: ""
  safety_risk: ""
  evidence_risk: ""
  operator_risk: ""

relationships:
  duplicate_of: null
  related_findings: []
  blocked_by: []
  blocks: []
  related_prs: []

rca:
  required: true | false
  rca_id: null
  ariadne_status: not_started | needs_more_evidence | pass | blocked

remediation:
  required: true | false
  remediation_plan_id: null
  daedalus_status: not_started | planned | blocked | complete

proof:
  required_tests: []
  required_evidence: []
  safety_checks: []
  acceptance_criteria: []

notes:
  unknowns: []
  deferred_questions: []
  rejection_reason: ""
```

## Required Fields

Every normalized finding must include:

- `finding_id`
- `schema_version`
- `status`
- `source.source_type`
- `classification.finding_type`
- `classification.severity`
- `classification.confidence`
- `summary.title`
- `summary.observed_behavior`
- `summary.expected_behavior`
- `proof.acceptance_criteria`

## Finding Types

### contract_violation

A known contract is violated.

Example:

```text
candidate_status=advisory_only but final emit says executable
```

### propagation_gap

Truth is detected in one layer but not carried into another.

Example:

```text
fallback contract resolution is detected but not propagated into final actionability fields
```

### evidence_gap

Behavior may be correct, but evidence is incomplete or ambiguous.

Example:

```text
stat-us exists but reason, source, or b-roker_api_called flag is miss-ing
```

### test_reality_gap

Tests do not prove real behavior.

Example:

```text
mock-only test proves shape but not runtime contract
```

### safety_boundary_gap

Safety boundary is unclear, unsafe, or unproven.

Example:

```text
read-only path contains order-like behavior without explicit guard
```

### architecture_drift

Multiple paths create ownership or behavior ambiguity.

Example:

```text
legacy and current ranking modules both appear active
```

### data_quality_gap

Input data is stale, fallback-based, incomplete, or unproven.

Example:

```text
stale feed reaches readiness path
```

### operational_gap

Manual process or missing run discipline creates risk.

Example:

```text
post-merge live-read-only validation evidence is missing
```

### unknown

Used only when evidence is insufficient to classify safely.

## Confidence Levels

### high

Evidence is direct and repeatable.

### medium

Evidence is plausible but incomplete.

### low

Finding is suspicious but weakly supported.

## Status Lifecycle

```text
open
→ triaged
→ accepted
→ remediated
```

Alternative paths:

```text
open → rejected
open → deferred
accepted → superseded
```

## RCA Requirement Rule

RCA is required when:

- severity is critical or high
- safety boundary is involved
- finding type is propagation_gap
- finding repeats across more than one source
- remediation would touch runtime behavior

RCA may be skipped when:

- finding is documentation-only
- root cause is obvious and low risk
- no product behavior changes are needed

## Non-Goals

This schema does not auto-fix findings.

It does not decide the remediation plan.

It does not prove profitability.

It exists to normalize evidence before root-cause clustering and remediation planning.
