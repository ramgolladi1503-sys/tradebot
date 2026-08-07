# S002 — Deterministic Constitution Contract Implementation

Program: MROS  
Milestone: M1 — Research Governance  
Work Package: WP001 — Research Constitution  
Sprint: S002  
Status: FINAL_BOOTSTRAP_REPAIR_IMPLEMENTED_PENDING_NATIVE_VALIDATION  
Authority: `Research / R`  
Runtime authority: `NONE`

## Objective

Operationalize the frozen S001 interface as deterministic, fail-closed governance validation without changing RC-001 through RC-010 or granting runtime authority.

## Canonical Validation Surface

The canonical executable validator is:

`scripts/mros/validate_s002_fixtures.py`

It loads two immutable evidence corpora:

1. `S002_FIXTURES.json` — v4 baseline, 53 historical/regression cases;
2. `S002_FIXTURES_V5_ADDENDUM.json` — final bootstrap-review closure cases.

Case IDs must be unique across both files. Any fixture-load/schema/duplicate-ID failure exits non-zero.

## Deterministic Classification

- direct measurement + provenance → `OBSERVED_FACT`;
- derived reasoning + provenance → `INFERENCE`;
- falsifiable unverified proposition → `HYPOTHESIS`;
- unsupported conjecture → `SPECULATION`;
- ambiguous classification → `REVIEW_REQUIRED` / E002;
- observed fact/inference without provenance → `INVALID_INPUT` / E015.

## Promotion Semantics

Legal transitions remain:

`Research / R → Grade C → Grade B → Grade A → Grade A+`

`Rejected` and `Unknown` have no implicit promotion path.

Promotion must:

- use valid authority values;
- provide non-empty canonical `EVID-*` new evidence refs;
- provide the complete prior evidence-ref set explicitly via `evidence_refs` before PASS;
- provide `evidence_provenance_complete=true` before PASS;
- prevent canonical old/new ref overlap and duplicate new refs;
- derive mandatory Grade B/A/A+ gate requirements from the requested grade;
- reject malformed optional boolean gate flags instead of silently ignoring them.

The literal reference identity is treated as the stable MROS evidence-registry identity at S002. Stronger content-hash/registry enforcement may be introduced only through controlled later registry work; S002 does not invent a separate evidence registry.

## Constitutional Fail-Closed Semantics

A request cannot receive PASS merely because one dependent field is recognizable.

Dependent-only requests such as:

- `destroyers` without `material_claim`;
- `completion_evidence_refs` without `completion_claim`;
- `supersession_decision_ref` without `supersedes`;

return controlled `INVALID_INPUT` / E001.

Causal-time, runtime, and scope pairs remain fail-closed. Malformed types/timestamps return controlled `INVALID_INPUT`, not uncaught exceptions.

## RC-009

Denominator-relevant inputs require deterministic confirmatory or `EXPLORATORY_POST_HOC` authority context.

Contracts must contain non-empty/type-valid denominator identity fields. Confirmatory post-outcome changes fail E008/E009. Legitimate preregistered unchanged contracts remain valid.

`EXPLORATORY_POST_HOC` semantically requires `outcomes_inspected=true`; declaring post-hoc analysis while asserting outcomes were not inspected is contradictory and now returns `INVALID_INPUT`.

A valid changed post-hoc analysis must preserve the original result, use a new analysis identity/rationale, account for multiplicity, and reduce authority.

## Enum Validation

`VALIDATE_CONTRACT_ENUMS` requires at least one controlled enum field (`knowledge_class`, `verdict`, or `status`). An empty or irrelevant enum-validation request cannot return PASS.

## Review History

The final bootstrap-independent review of candidate `c8864050e5df1a0d2303cadf88908c5eef6410c3` returned:

`S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED`

with 5 MAJOR, 1 MINOR, 0 CRITICAL, 1 UNKNOWN.

The five MAJOR classes were:

1. partial/dependent constitutional requests silently passing;
2. empty enum-validation requests passing;
3. contradictory post-hoc RC-009 state passing;
4. incomplete genuine-new-evidence identity/lineage enforcement;
5. malformed promotion-schema types being ignored or substantively misclassified.

The current v5 repair addresses those classes in implementation and adds dedicated adversarial fixtures. The prior UNKNOWN concerning repository-sealed native evidence is not declared closed by implementation; a new exact-head native run is required.

## Non-Goals

S002 does not:

- accept itself;
- accept WP001;
- start S003;
- start M2;
- authorize Review/Audit Boards;
- start M9;
- modify strategy/broker/risk/execution/runtime behavior.

## Observed Facts

- S001 remains accepted with one non-blocking minor finding.
- Multiple independent S002 rounds have found real fail-open defects.
- Failed reviews and prior native results remain preserved as historical evidence.
- The current implementation includes the 53-case v4 corpus plus the v5 adversarial addendum.

## Inferences

Repeated independent attack is strengthening the governance validator; no previous green fixture result is treated as authority for a changed HEAD.

## Hypotheses

The v5 repair may close the currently known S002 fail-open classes, but this remains unproven until native validation and a fresh bootstrap-independent re-review of the exact repaired HEAD.

## Assumptions

The frozen S001 contract and current MROS authority model remain authoritative.

## Destroyers / Falsifiers

S002 remains unacceptable if a valid adversarial input can silently PASS through missing/contradictory decision semantics, evidence-only promotion, RC-009, runtime separation, malformed schema handling, or controlled enum validation.

## Unknowns

- exact-head native validation for the current v5 repair;
- fresh bootstrap-independent review of that exact native-validated HEAD.

## Next Experiment

Run the canonical combined fixture validator natively from the exact current S002 repair HEAD, preserve complete provenance, then obtain a fresh independent re-review. Do not start S003 beforehand.

## Authority Grade

`Research / R`
