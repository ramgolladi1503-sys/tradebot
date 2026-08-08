# S002 — Deterministic Constitution Contract Implementation

Program: MROS  
Milestone: M1 — Research Governance  
Work Package: WP001 — Research Constitution  
Sprint: S002  
Status: V8_INHERITED_GATE_PROVENANCE_REPAIR_PENDING_NATIVE_VALIDATION  
Authority: `Research / R`  
Runtime authority: `NONE`

## Objective

Operationalize the frozen S001 interface as deterministic, fail-closed governance validation without changing RC-001 through RC-010 or granting runtime authority.

## Canonical Validation Surface

The canonical executable validator is:

`scripts/mros/validate_s002_fixtures.py`

It loads five preserved evidence corpora:

1. `S002_FIXTURES.json` — v4 baseline/regression corpus;
2. `S002_FIXTURES_V5_ADDENDUM.json` — final bootstrap-review closure cases;
3. `S002_FIXTURES_V6_GATE_BINDING.json` — syntactic new-evidence gate binding and lineage controls;
4. `S002_FIXTURES_V7_GATE_SEMANTIC_BINDING.json` — semantic requested-gate binding attacks and positive controls;
5. `S002_FIXTURES_V8_INHERITED_GATE_PROVENANCE.json` — inherited mandatory gate provenance and exact binding-schema controls.

Historical PASS cases superseded by stronger promotion controls remain preserved but are excluded from the active suite. Case IDs must be unique across active corpora. Fixture load/schema/duplicate-ID failures exit non-zero.

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
- derive mandatory Grade B/A/A+ requirements from the requested grade;
- bind every newly requested promotion gate to a canonical new `EVID-*` identity;
- bind that same identity to the authoritative gate metadata field;
- require inherited mandatory gate evidence to be canonical registered `EVID-*` identities already present in the declared prior evidence provenance;
- require `new_evidence_gate_bindings` to contain exactly the requested transition gates, rejecting both missing and extra known/unknown gate entries;
- reject stale gate metadata paired with unrelated newly labelled evidence;
- reject malformed optional boolean/gate/schema values instead of silently ignoring them.

The literal `EVID-*` identity is the stable MROS evidence-registry identity at S002. S002 does not claim to inspect future registry content semantics; it deterministically enforces identity/provenance consistency within the declared governance input.

## Constitutional Fail-Closed Semantics

A request cannot receive PASS merely because one dependent field is recognizable. Partial/dependent requests fail closed. Causal-time, runtime, denominator, scope, enum, and malformed-schema paths remain controlled.

## RC-009

Denominator-relevant inputs require deterministic confirmatory or `EXPLORATORY_POST_HOC` authority context. Confirmatory post-outcome changes fail E008/E009. Legitimate preregistered unchanged contracts remain valid. A changed post-hoc analysis must preserve the original result, use a new analysis identity/rationale, account for multiplicity, and reduce authority.

## Review History

The bootstrap-independent review of exact candidate `8e87223efdb33bc73b58436cf590b7f3c7c10717` returned `S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED` with 1 MAJOR, 0 MINOR, 0 CRITICAL, and 0 mandatory UNKNOWN.

The prior blocker `89D3-F-001` was closed as written. The new MAJOR (`8E872-V2-F-001`) found two remaining fail-open schema/provenance paths:

1. inherited mandatory Grade-B evidence such as `independent_attack_ref` and `calibration_ref` could be malformed or absent from the declared complete prior `evidence_refs` set while a B→A promotion still PASSed;
2. extra known entries inside `new_evidence_gate_bindings` were ignored when they were not required for the requested transition, allowing malformed extra gate metadata to coexist with PASS.

The v8 repair closes those paths by canonicalizing inherited mandatory evidence, requiring its membership in prior provenance, and requiring exact requested-gate key equality for the binding object.

## Non-Goals

S002 does not accept itself, accept WP001, start S003/M2/M9, authorize Review/Audit Boards, or modify strategy/broker/risk/execution/runtime behavior.

## Observed Facts

- Exact candidate `8e87223e...` had native 78/78 PASS but failed a genuinely independent review on one real fail-open provenance/schema defect class.
- That review is preserved at `S002_INDEPENDENT_RE_REVIEW_8E872_BOOTSTRAP_V2.md`.
- v8 adds four direct regression attacks covering malformed inherited refs, missing inherited provenance, malformed extra known bindings, and valid-looking extra known bindings.

## Inferences

The v8 repair is stricter than v7: PASS now requires both newly requested gate evidence and inherited mandatory gate evidence to be internally consistent with declared evidence provenance.

## Hypotheses

The v8 repair closes `8E872-V2-F-001`; this remains unproven until native validation and a fresh bootstrap-independent re-review of the exact repaired HEAD.

## Assumptions

The frozen S001 contract and current MROS authority model remain authoritative.

## Destroyers / Falsifiers

S002 remains unacceptable if malformed/unproven inherited gate evidence or ignored extra gate metadata can still produce authority promotion, or if the v8 rewrite regresses any previously accepted fail-closed behavior.

## Unknowns

- exact-head native validation for the v8 repair;
- fresh bootstrap-independent review of that exact validated HEAD.

## Next Experiment

Run the canonical combined fixture validator natively from the exact repaired HEAD. The active suite should contain 82 cases. Preserve exact HEAD/Python/command/output/exit provenance, then obtain a fresh independent re-review. Do not start S003 beforehand.

## Authority Grade

`Research / R`
