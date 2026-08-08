# S002 — Deterministic Constitution Contract Implementation

Program: MROS  
Milestone: M1 — Research Governance  
Work Package: WP001 — Research Constitution  
Sprint: S002  
Status: RC002_SEMANTIC_GATE_BINDING_REPAIR_PENDING_NATIVE_VALIDATION  
Authority: `Research / R`  
Runtime authority: `NONE`

## Objective

Operationalize the frozen S001 interface as deterministic, fail-closed governance validation without changing RC-001 through RC-010 or granting runtime authority.

## Canonical Validation Surface

The canonical executable validator is:

`scripts/mros/validate_s002_fixtures.py`

It loads four preserved evidence corpora:

1. `S002_FIXTURES.json` — v4 baseline/regression corpus;
2. `S002_FIXTURES_V5_ADDENDUM.json` — final bootstrap-review closure cases;
3. `S002_FIXTURES_V6_GATE_BINDING.json` — syntactic new-evidence gate binding and lineage controls;
4. `S002_FIXTURES_V7_GATE_SEMANTIC_BINDING.json` — semantic gate-to-authoritative-evidence binding attacks and positive controls.

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
- bind every requested promotion gate to a canonical new `EVID-*` identity;
- bind that same identity to the authoritative gate metadata field (`reproducibility_ref`, `independent_attack_ref`, `calibration_ref`, `scientific_certification_ref`, `economic_certification_ref`, `live_forward_evidence_ref`, or `monitoring_ref` as applicable);
- reject stale gate metadata paired with unrelated newly labelled evidence;
- reject malformed optional boolean/gate/schema values instead of silently ignoring them.

The literal `EVID-*` identity is the stable MROS evidence-registry identity at S002. S002 does not claim to inspect future registry content semantics; it does deterministically prevent a caller from presenting one evidence identity as the authoritative gate evidence while binding a different unrelated identity as the supposedly new evidence satisfying that gate.

## Constitutional Fail-Closed Semantics

A request cannot receive PASS merely because one dependent field is recognizable. Partial/dependent requests fail closed. Causal-time, runtime, denominator, scope, enum, and malformed-schema paths remain controlled.

## RC-009

Denominator-relevant inputs require deterministic confirmatory or `EXPLORATORY_POST_HOC` authority context. Confirmatory post-outcome changes fail E008/E009. Legitimate preregistered unchanged contracts remain valid. A changed post-hoc analysis must preserve the original result, use a new analysis identity/rationale, account for multiplicity, and reduce authority.

## Review History

The independent review of exact candidate `89d3abd3b2b2c20951c123063b534c56af7ebf60` returned `S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED` with 1 MAJOR and 1 MINOR.

The MAJOR (`89D3-F-001`) proved that v6 only enforced syntactic membership/non-overlap: stale authoritative gate metadata could coexist with unrelated new evidence caller-labelled as the requested gate and still PASS. The v7 repair closes that contradiction by requiring equality between each requested gate binding and its authoritative gate evidence reference.

The MINOR was documentation drift about fixture-corpus count; this document now lists all four active/preserved corpora accurately.

## Non-Goals

S002 does not accept itself, accept WP001, start S003/M2/M9, authorize Review/Audit Boards, or modify strategy/broker/risk/execution/runtime behavior.

## Observed Facts

- Exact candidate `89d3abd3...` had native 70/70 PASS but failed independent review on one real RC-002 semantic binding defect.
- The failed review is preserved at `S002_INDEPENDENT_RE_REVIEW_89D3_FINAL.md`.
- v7 adds deterministic attacks for unrelated/stale gate evidence and legitimate promotion controls.

## Inferences

The repair is stricter than v6: it no longer accepts arbitrary new evidence merely because a caller assigns a gate label to it while the authoritative gate metadata points elsewhere.

## Hypotheses

The v7 repair closes `89D3-F-001`; this remains unproven until native validation and a fresh independent review of the exact repaired HEAD.

## Assumptions

The frozen S001 contract and current MROS authority model remain authoritative.

## Destroyers / Falsifiers

S002 remains unacceptable if stale/unrelated gate evidence can still produce authority promotion, or if the v7 repair regresses any previously accepted fail-closed behavior.

## Unknowns

- exact-head native validation for the v7 repair;
- fresh bootstrap-independent review of that exact validated HEAD.

## Next Experiment

Run the canonical combined fixture validator natively from the exact repaired HEAD, preserve exact provenance, then obtain a fresh independent re-review. Do not start S003 beforehand.

## Authority Grade

`Research / R`
