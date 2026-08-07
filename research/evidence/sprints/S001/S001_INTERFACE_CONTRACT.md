# S001 — Frozen Interface / Schema / Status / Error Contract

Sprint: S001
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Branch: `research/mros-program-v1`
Status: FROZEN_FOR_S002_IMPLEMENTATION
Authority Grade: Research / R
Repair source: `S001_INDEPENDENT_REVIEW.md` F-002
Operational authority: NONE

## Purpose

Freeze the machine-checkable semantic surface that later WP001 sprints must implement and verify. This artifact defines contract semantics only. It does **not** implement S002.

## Component Boundary

WP001 exposes a governance-validation boundary with four logical responsibilities:

1. `StatementClassificationContract` — classifies a material research statement into one primary knowledge class or an ambiguity/error state.
2. `VerdictContract` — constrains legal scientific verdicts and prevents unsupported coercion.
3. `AuthorityPromotionContract` — validates requested authority transitions against new evidence and required gates.
4. `ConstitutionalRuleContract` — evaluates declared research actions against RC-001 through RC-010 and fails closed on invalid or insufficient inputs.

These names describe the frozen interface responsibilities. S002 may implement them in code, fixtures, schemas, or validators, but may not silently change their semantics.

## Required Input Surface

A governed evaluation input must be capable of carrying, directly or by stable reference:

- `statement_id` or temporary local identity;
- `statement_text`;
- `knowledge_class_current` where already assigned;
- `requested_verdict` where applicable;
- `authority_current`;
- `authority_requested` where applicable;
- `evidence_refs`;
- `new_evidence_refs` for promotion attempts;
- `decision_timestamp` where causal availability matters;
- `input_availability_timestamps` or equivalent provenance where causal time is evaluated;
- `experiment_contract_ref` where denominator/horizon/population rules are relevant;
- `denominator_definition` and `exclusion_rule_refs` where metrics are used;
- `independent_attack_ref` where promotion requires independence;
- `calibration_ref` where strong claims depend on calibrated instrumentation;
- `destroyers` / falsifiers for material scientific claims;
- `assumptions`;
- `unknowns`;
- `runtime_context` flag/reference when runtime separation is in question.

Missing fields that are not relevant to a given evaluation may be null/absent only when the validator can prove they are not required by the requested operation. Missing fields that are required for a decision must fail closed.

## Required Output Surface

A governed evaluation result must contain or deterministically imply:

- `status` from the controlled status vocabulary below;
- `verdict` where a scientific verdict is being evaluated;
- `knowledge_class` where classification is requested;
- `authority_grade` where authority is evaluated;
- `violated_rules` as zero or more RC identifiers;
- `error_codes` as zero or more controlled error codes;
- `evidence_used`;
- `assumptions`;
- `unknowns`;
- `reason` / machine- or human-readable rationale;
- `can_promote` boolean or equivalent deterministic result for promotion checks.

A result that cannot determine a required semantic output must not default to PASS.

## Controlled Knowledge Classes

Exactly one primary knowledge class may be assigned when classification succeeds:

- `OBSERVED_FACT`
- `INFERENCE`
- `HYPOTHESIS`
- `SPECULATION`

If the evidence is insufficient to choose exactly one class, classification must return an ambiguity/insufficient-evidence status rather than arbitrarily choosing the strongest or most favorable class.

## Controlled Scientific Verdicts

Legal verdicts:

- `SUPPORTED`
- `REJECTED`
- `UNKNOWN`
- `INSUFFICIENT_EVIDENCE`

`UNKNOWN` and `INSUFFICIENT_EVIDENCE` are non-failure scientific outcomes. They must not be silently translated to `SUPPORTED` or `REJECTED`.

A future implementation may introduce narrower internal sub-statuses only if they preserve these semantics and are recorded through controlled change.

## Controlled Authority Grades

The only current authority grades are:

- `Research / R`
- `Grade C`
- `Grade B`
- `Grade A`
- `Grade A+`
- `Rejected`
- `Unknown`

The superseded `A0–A5` bootstrap scale is invalid for new MROS records.

## Controlled Evaluation Statuses

The minimum status vocabulary is:

- `PASS`
- `FAIL`
- `UNKNOWN`
- `INVALID_INPUT`
- `BLOCKED`
- `REVIEW_REQUIRED`

Semantics:

- `PASS`: requested governance condition is directly satisfied.
- `FAIL`: requested governance condition is contradicted or a mandatory rule is violated.
- `UNKNOWN`: evidence is insufficient to determine the requested scientific/governance condition.
- `INVALID_INPUT`: input violates schema/contract requirements; no scientific conclusion may be inferred.
- `BLOCKED`: a required dependency/evidence source is unavailable; no automatic promotion.
- `REVIEW_REQUIRED`: automated checks are insufficient and the frozen contract requires independent/human review.

No implementation may map `UNKNOWN`, `INVALID_INPUT`, `BLOCKED`, or `REVIEW_REQUIRED` to `PASS` merely to continue a workflow.

## Fail-Closed Error Codes

The minimum controlled error set is:

- `MROS-S001-E001-MISSING_REQUIRED_FIELD`
- `MROS-S001-E002-AMBIGUOUS_KNOWLEDGE_CLASS`
- `MROS-S001-E003-INVALID_AUTHORITY_GRADE`
- `MROS-S001-E004-AUTHORITY_STAGE_SKIP`
- `MROS-S001-E005-NO_NEW_EVIDENCE_FOR_PROMOTION`
- `MROS-S001-E006-INDEPENDENT_ATTACK_REQUIRED`
- `MROS-S001-E007-CAUSAL_TIME_VIOLATION`
- `MROS-S001-E008-DENOMINATOR_CONTRACT_VIOLATION`
- `MROS-S001-E009-POST_HOC_EXCLUSION_DETECTED`
- `MROS-S001-E010-CALIBRATION_REQUIRED`
- `MROS-S001-E011-RUNTIME_AUTHORITY_VIOLATION`
- `MROS-S001-E012-UNRECORDED_SUPERSESSION`
- `MROS-S001-E013-NON_FALSIFIABLE_CLAIM`
- `MROS-S001-E014-SCOPE_DRIFT`
- `MROS-S001-E015-EVIDENCE_PROVENANCE_MISSING`
- `MROS-S001-E016-UNSUPPORTED_COMPLETION_CLAIM`
- `MROS-S001-E017-OBSOLETE_AUTHORITY_SCALE`

Implementations may add error codes but may not weaken these conditions without controlled change.

## Core Invariants

### I-001 — Evidence-only promotion
An authority increase must identify genuinely new registered evidence satisfying the predeclared gate.

### I-002 — No stage skipping
Promotion may not bypass required authority stages/gates.

### I-003 — Independence is substantive
The implementing/discovering agent cannot satisfy its own mandatory independent-attack gate.

### I-004 — Unknown fails safe
Insufficient evidence results in `UNKNOWN`, `INSUFFICIENT_EVIDENCE`, `BLOCKED`, or `REVIEW_REQUIRED`, not automatic support/rejection/promotion.

### I-005 — Causal availability
Information unavailable at the declared decision time cannot support causal evidence.

### I-006 — Denominator immutability for confirmatory evidence
The frozen eligible population, observations/trades/events, exclusions, horizons, regimes, dates, symbols, hypothesis/search-family membership, and metric denominator cannot be changed after outcome inspection to improve a confirmatory result.

### I-007 — Post-hoc analyses remain distinct
Scientifically justified post-hoc denominator/exclusion changes must preserve the original result and become a separately identified exploratory analysis/search family with appropriate multiplicity and reduced authority until independently confirmed.

### I-008 — Runtime cannot create research truth
Runtime output cannot establish or promote research authority.

### I-009 — No silent supersession
Prior claims/evidence/decisions remain queryable and changed belief requires an explicit supersession relationship/decision.

### I-010 — Invalid input cannot promote
Schema/contract failure must fail closed and cannot produce scientific promotion.

## Schema Constraints for S002

S002 must make these semantics deterministic and machine-checkable. At minimum, its schema/fixtures must enforce:

1. enum validation for knowledge classes, verdicts, authority grades, and controlled statuses;
2. required-field validation conditional on the requested operation;
3. explicit error reporting using stable error codes;
4. deterministic handling of ambiguous statement classification;
5. denominator/exclusion metadata sufficient to detect contract changes;
6. evidence-reference presence for promotion attempts;
7. explicit independence/calibration requirements where applicable;
8. no dependency on TradeBot runtime to determine governance truth.

## Invalid / Ambiguous Input Behavior

- Unknown enum value → `INVALID_INPUT` plus the applicable error code.
- Missing mandatory field → `INVALID_INPUT` + `MROS-S001-E001-MISSING_REQUIRED_FIELD`.
- Ambiguous knowledge class → `UNKNOWN` or `REVIEW_REQUIRED` + `MROS-S001-E002-AMBIGUOUS_KNOWLEDGE_CLASS`.
- Unsupported authority transition → `FAIL` plus transition/evidence error code(s).
- Missing mandatory independent attack → `REVIEW_REQUIRED` or `BLOCKED` plus `MROS-S001-E006-INDEPENDENT_ATTACK_REQUIRED`.
- Causal-time violation → `FAIL` + `MROS-S001-E007-CAUSAL_TIME_VIOLATION`; affected evidence is inadmissible until repaired/rerun.
- Post-hoc denominator/exclusion change presented as confirmatory evidence → `FAIL` + `MROS-S001-E008-DENOMINATOR_CONTRACT_VIOLATION` and/or `MROS-S001-E009-POST_HOC_EXCLUSION_DETECTED`.
- Runtime attempt to create/promote research authority → `FAIL` + `MROS-S001-E011-RUNTIME_AUTHORITY_VIOLATION`.

## Evidence Obligations

Every validation intended to influence authority must preserve:

- exact branch/ref and commit;
- contract/schema version;
- input fixture identity/hash;
- validator/test version;
- command/procedure;
- output/result;
- error/status codes;
- reviewer/independence provenance where required;
- assumptions and unknowns;
- evidence artifact identity/hash when registry support is available.

## Change Control

This contract is frozen for S002 implementation. Any semantic change must:

1. stop progression;
2. cite evidence/reason;
3. preserve the prior contract;
4. receive a controlled decision/impact review;
5. be independently re-reviewed if it affects S001 acceptance semantics.

## Non-Goals

This artifact does not:

- implement classification code;
- implement schemas/fixtures;
- certify WP001;
- certify any market claim;
- touch TradeBot runtime;
- authorize S002 before S001 acceptance.

## S001 Acceptance Effect

Existence of this contract resolves the design-freeze gap identified as F-002 only if independent re-review confirms the semantics are adequate. It does not itself mark S001 PASS.
