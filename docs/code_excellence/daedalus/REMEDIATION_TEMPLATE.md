# Daedalus Remediation Template

## Purpose

Daedalus turns an accepted Ariadne RCA or root-cause cluster into a bounded remediation plan.

Daedalus is a planning layer only. It does not change code, auto-fix, or auto-merge.

## Remediation Plan Template

```yaml
remediation_plan_id: CE-DAEDALUS-YYYY-NNN
status: draft | reviewed | accepted | blocked | superseded | complete
created_at: YYYY-MM-DD
owner: TBD
source_rca_id: null
source_cluster_id: null
source_findings: []
related_prs: []

problem:
  title: ""
  root_cause_summary: ""
  affected_contracts: []
  affected_modules: []

scope:
  in_scope: []
  out_of_scope: []
  must_not_touch: []
  allowed_files: []
  forbidden_files: []

change_plan:
  intended_behavior_change: ""
  implementation_steps:
    - step: ""
      files: []
      reason: ""
  data_or_schema_changes: []
  evidence_changes: []

risk_model:
  product_risks: []
  safety_risks: []
  evidence_risks: []
  operational_risks: []
  rollback_or_revert_plan: ""

proof_plan:
  required_tests:
    positive: []
    negative: []
    regression: []
    edge: []
  required_evidence: []
  required_manual_validation: []
  required_ci_checks: []

forbidden_shortcuts: []
acceptance_criteria: []

daedalus_verdict:
  result: pass | needs_more_design | blocked
  reason: ""
```

## Required Inputs

A plan must start from one of:

- accepted Ariadne RCA
- Ariadne cluster requiring remediation
- approved manual exception with evidence

## Required Sections

### Problem

State the selected root cause, not just the visible symptom.

### Scope

Define what can change and what must not change.

The scope must be small enough to review safely.

### Change Plan

Every step needs:

- file list
- reason
- expected behavior change
- proof requirement

### Risk Model

Name how the change could make the product worse.

Required categories:

- product risk
- safety risk
- evidence risk
- operational risk

### Proof Plan

The proof plan must include tests and evidence strong enough for the risk level.

For runtime or safety-related changes, include:

- positive test
- negative test when applicable
- regression test for the exact issue
- evidence/report update when behavior changes
- repo-forensics PR gate

## Verdict Rules

### PASS

Use when root cause, scope, risks, and proof are clear.

### NEEDS_MORE_DESIGN

Use when the fix idea is plausible but scope, risk, or proof is incomplete.

### BLOCKED

Use when RCA is weak, scope is broad, risk is unknown, or proof is fake.

## Hard Rules

- Do not plan broad rewrites.
- Do not change unrelated modules.
- Do not hide failures behind silent fallback behavior.
- Do not weaken tests to match broken behavior.
- Do not claim profitability impact from planning.
- Do not approve remediation without proof requirements.
