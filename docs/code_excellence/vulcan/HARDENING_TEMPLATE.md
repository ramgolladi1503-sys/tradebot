# Vulcan Production Hardening Template

## Purpose

Vulcan converts an accepted Daedalus remediation plan into a production-grade hardening contract.

Vulcan is not a free pass to rewrite code. It is the final implementation discipline before a scoped patch is written.

## Required Inputs

A Vulcan hardening contract must start from:

- an accepted Daedalus remediation plan
- a clear Hermes scope pass
- a known risk/proof model
- explicit files allowed to change
- explicit files not allowed to change

## Hardening Contract Template

```yaml
vulcan_contract_id: CE-VULCAN-YYYY-NNN
status: draft | reviewed | accepted | blocked | superseded | complete
created_at: YYYY-MM-DD
owner: TBD
source_remediation_plan_id: null
source_cluster_id: null
related_prs: []

problem:
  title: ""
  root_cause: ""
  current_maturity: basic | fragile | partial | hardened | production_grade
  target_maturity: hardened | production_grade

scope:
  allowed_files: []
  forbidden_files: []
  explicit_non_goals: []
  max_change_surface: small | medium | blocked

implementation_contract:
  behavior_to_change: ""
  behavior_to_preserve: []
  safe_defaults: []
  fail_closed_rules: []
  deterministic_logic_rules: []
  explicit_contracts_or_types: []
  structured_rejection_reasons: []
  evidence_outputs: []
  forbidden_shortcuts: []

proof_contract:
  positive_tests: []
  negative_tests: []
  regression_tests: []
  edge_case_tests: []
  evidence_assertions: []
  ci_checks: []

risk_controls:
  safety_risks: []
  product_risks: []
  evidence_risks: []
  operational_risks: []
  rollback_plan: ""

vulcan_verdict:
  result: pass | needs_more_proof | blocked
  reason: ""
```

## Required Sections

### Problem

State the root cause from Daedalus. Do not restate only the visible failure.

### Scope

List the exact files allowed to change and forbidden to change.

The allowed file list must be small enough for review. If the change spans unrelated modules, Vulcan must block it.

### Implementation Contract

Define the behavior delta before code is written.

Required items:

- behavior to change
- behavior to preserve
- safe defaults
- fail-closed behavior
- deterministic rules
- explicit contracts or types
- structured rejection reasons
- evidence-rich outputs

### Proof Contract

Define tests and evidence before code is written.

Required when safety/actionability is involved:

- positive test
- negative unsafe-path test
- regression test for exact bug
- evidence/report assertion
- repo-forensics PR gate

### Risk Controls

Name how the hardening could make the product worse.

Required categories:

- safety risk
- product risk
- evidence risk
- operational risk

## Verdict Rules

### PASS

Use only when implementation behavior, scope, risks, and proof are specific.

### NEEDS_MORE_PROOF

Use when the patch idea is reasonable but proof is incomplete or weak.

### BLOCKED

Use when scope is broad, root cause is weak, safety is ambiguous, or tests are fake confidence.

## Hard Rules

- Do not harden without a Daedalus contract.
- Do not change files outside the approved scope.
- Do not loosen safety gates.
- Do not replace behavior proof with shape-only tests.
- Do not hide broken state behind fallback.
- Do not claim production-grade maturity without negative tests.
- Do not touch broker/live behavior unless explicitly scoped.
