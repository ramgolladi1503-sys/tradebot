# CE-03 — Finding Normalization Contract

## Agent Work Contract

### Scope

Add the Code Excellence finding normalization contract.

This PR defines a shared normalized finding schema, severity/source mapping, deduplication rules, and examples. It prepares the ground for Ariadne clustering in CE-04.

### Files Changed

- `docs/code_excellence/finding_normalization/NORMALIZED_FINDING_SCHEMA.md`
- `docs/code_excellence/finding_normalization/SEVERITY_SOURCE_MAPPING.md`
- `docs/code_excellence/finding_normalization/DEDUPLICATION_RULES.md`
- `docs/code_excellence/finding_normalization/EXAMPLES.md`
- `docs/agent_reviews/CE_03_FINDING_NORMALIZATION_CONTRACT.md`

### Hard Boundaries

- No product code changes.
- No finding normalization implementation.
- No Ariadne clustering engine.
- No remediation planner.
- No scanner behavior changes.
- No trading logic changes.
- No broker behavior changes.
- No live runtime execution.
- No auto-fix.
- No auto-PR.
- No baseline debt cleanup.
- No test weakening.

## Deliverables

This PR adds:

- normalized finding schema
- finding type taxonomy
- severity mapping rules
- source mapping rules
- deduplication rules
- examples for repo-forensics, runtime logs, tests, product reality, and architecture drift

## Gate 1 — Scope and Intent

PASS.

This is contract work only. It defines the common finding language before implementation begins.

## Gate 2 — Truth and Root-Cause

PASS.

This PR does not claim to fix any production issue. It defines how future issues will be normalized before RCA and clustering.

## Gate 3 — Hardening and Proof

PASS pending CI.

Docs-only PR. The required repo-forensics PR gate must pass.

## Grill Me Review

### Challenge

Finding normalization can become paperwork if it does not reduce duplicate work or improve RCA quality.

### Findings

- Good: schema separates symptom, source, classification, impact, relationships, RCA, remediation, and proof.
- Good: severity rules escalate executable truth and safety-boundary ambiguity.
- Good: deduplication rules prevent filename-only grouping.
- Good: examples cover real TradeBot signal types.
- Risk: CE-04 must implement deterministic normalization/clustering discipline instead of leaving this as documentation only.

### Verdict

PASS.

## Hermes Review

### Scope Verification

- [x] No product code changed.
- [x] No implementation added.
- [x] No scanner behavior changed.
- [x] No broker behavior changed.
- [x] No live behavior changed.
- [x] No tests weakened.
- [x] No auto-fix or auto-PR behavior introduced.

### Verdict

PASS.

## GSD Review

### Delivery Check

- [x] Normalized finding schema added.
- [x] Severity/source mapping added.
- [x] Deduplication rules added.
- [x] Examples added.
- [x] Agent evidence added.
- [x] Next action is clear: CE-04 — Ariadne Root-Cause Clustering Engine.

### Verdict

PASS pending CI.

## Scope Guard

### In Scope

- Finding schema.
- Finding taxonomy.
- Severity mapping.
- Source mapping.
- Deduplication rules.
- Examples.
- Agent evidence file.

### Out of Scope

- Normalizer implementation.
- Clustering engine.
- Remediation planning.
- Product fixes.
- Runtime execution.

## Test Plan

No runtime tests required for documentation-only PR.

Required CI:

```text
repo-forensics-pr-gate
```

## Final Verdict

PASS pending CI.

## Next PR

CE-04 — Ariadne Root-Cause Clustering Engine

Expected deliverables:

- deterministic normalized finding loader
- root-cause family grouping
- duplicate/related finding grouping
- cluster report writer
- tests for deterministic clustering
- no auto-fix
