# S002 — Deterministic Constitution Contract Implementation

Program: MROS  
Milestone: M1 — Research Governance  
Work Package: WP001 — Research Constitution  
Sprint: S002  
Status: V10_NULL_MANDATORY_REF_SCHEMA_REPAIR_PENDING_NATIVE_VALIDATION  
Authority: `Research / R`  
Runtime authority: `NONE`

## Objective

Operationalize the frozen S001 interface as deterministic, fail-closed governance validation without changing RC-001 through RC-010 or granting runtime authority.

## Canonical Validation Surface

Canonical validator:

`scripts/mros/validate_s002_fixtures.py`

It loads seven preserved corpora:

1. `S002_FIXTURES.json` — v4 baseline/regression;
2. `S002_FIXTURES_V5_ADDENDUM.json` — bootstrap-review closure;
3. `S002_FIXTURES_V6_GATE_BINDING.json` — syntactic new-evidence binding/lineage;
4. `S002_FIXTURES_V7_GATE_SEMANTIC_BINDING.json` — semantic requested-gate binding;
5. `S002_FIXTURES_V8_INHERITED_GATE_PROVENANCE.json` — inherited mandatory provenance and exact gate-key schema;
6. `S002_FIXTURES_V9_CLASSIFICATION_SCHEMA.json` — malformed mandatory-ref type precedence, unknown classification-signal rejection, and canonical classification provenance;
7. `S002_FIXTURES_V10_NULL_MANDATORY_REF_SCHEMA.json` — explicit-null inherited mandatory-ref schema precedence.

Historical superseded cases remain preserved in Git history/evidence but are excluded from the active suite. Active case IDs must be unique. Fixture loading/schema failures exit non-zero.

## Deterministic Classification

- direct measurement + canonical provenance → `OBSERVED_FACT`;
- derived reasoning + canonical provenance → `INFERENCE`;
- falsifiable unverified proposition → `HYPOTHESIS`;
- unsupported conjecture → `SPECULATION`;
- conflicting recognized classes → `REVIEW_REQUIRED` / E002;
- missing observed/inference provenance → `INVALID_INPUT` / E015;
- unknown classification signals → `INVALID_INPUT` / E021;
- malformed observed/inference evidence identities → `INVALID_INPUT` / E021.

Unknown classification metadata is never silently discarded to obtain PASS.

## Promotion Semantics

Legal transitions remain:

`Research / R → Grade C → Grade B → Grade A → Grade A+`

`Rejected` and `Unknown` have no promotion path.

Promotion must:

- use valid authority values;
- provide non-empty canonical `EVID-*` new evidence;
- provide complete prior evidence via `evidence_refs`;
- set `evidence_provenance_complete=true`;
- prevent old/new overlap and duplicate identities;
- derive Grade B/A/A+ requirements from requested grade;
- distinguish semantic absence from malformed schema types;
- treat an absent mandatory `independent_attack_ref` / `calibration_ref` as its controlled semantic missing state;
- treat an explicitly present JSON `null` or other non-string mandatory evidence ref as malformed schema → `INVALID_INPUT / E021`;
- require inherited mandatory gate evidence to be canonical and present in declared prior provenance;
- require `new_evidence_gate_bindings` to contain exactly the gates required for the requested transition;
- bind each requested gate to the same canonical genuinely new evidence identity used by its authoritative gate field;
- reject stale/unrelated gate evidence and malformed binding metadata.

## Constitutional Fail-Closed Semantics

Partial requests fail closed. Causal-time, runtime, denominator, scope, enums, timestamps, and malformed schema paths remain controlled. Runtime cannot create research authority.

## RC-009

Confirmatory denominator changes after outcomes are inspected fail E008/E009. Legitimate preregistered unchanged contracts remain valid. Changed post-hoc exploratory analyses require a new analysis identity/rationale, preserved original result, multiplicity accounting, and reduced authority.

## Review History

The fresh independent review of exact candidate `2a10c33c34e4d8d7c95b90dee2d88d59b906b6e4` returned `S002_INDEPENDENT_RE_REVIEW_UNKNOWN` with 1 MAJOR, 0 CRITICAL, 0 MINOR, and 1 mandatory UNKNOWN.

`2A10C-F-001` found that explicit JSON `null` for inherited mandatory refs was still treated as semantic absence (`REVIEW_REQUIRED` / `BLOCKED`) instead of malformed non-string input (`INVALID_INPUT / E021`). v10 fixes that precedence and adds direct regression cases C097-C098.

The mandatory UNKNOWN was provenance-only: the independent reviewer could not verify a committed exact-head 88/88 native-validation artifact, and repository state still recorded v9 native validation as PENDING. The operator-supplied native transcript for exact candidate `2a10c33c...` has now been durably committed as `S002_NATIVE_VALIDATION_OUTPUT_88_CASES.txt` with transcript SHA-256 and exact HEAD/Python/result/exit metadata. That evidence is historical for v9 because v10 changes implementation.

The same review found `7E7A-F-002` (unknown classification-signal fail-open) closed and found no new classification-provenance blocker.

## Non-Goals

S002 does not accept itself, accept WP001, start S003/M2/M9, authorize Review/Audit Boards, or modify strategy/broker/risk/execution/runtime behavior.

## Observed Facts

- Exact v9 candidate `2a10c33c...` received native 88/88 PASS, Python 3.12.2, exit 0 from the operator's native detached checkout.
- That native evidence is now committed at `research/evidence/sprints/S002/S002_NATIVE_VALIDATION_OUTPUT_88_CASES.txt` and is bound exclusively to v9 candidate `2a10c33c...`.
- The independent v9 review is preserved at `S002_INDEPENDENT_RE_REVIEW_2A10C_FINAL.md`.
- v10 adds C097-C098 for explicit-null mandatory-ref precedence.

## Inferences

v10 is a narrow schema-precedence repair: it does not alter authority stages, gate identity rules, classification semantics, causal-time controls, denominator controls, runtime boundaries, or strategy/broker/risk/execution behavior.

## Hypotheses

The v10 repair closes `2A10C-F-001`; this remains unproven until exact-head native validation and a fresh independent re-review.

## Destroyers / Falsifiers

S002 remains unacceptable if explicit null mandatory refs do not return `INVALID_INPUT / E021`, if absent mandatory refs lose their intended semantic missing states, if any v9/v8 protections regress, or if the exact v10 candidate cannot obtain native validation plus independent review.

## Unknowns

- exact-head native validation for v10;
- fresh bootstrap-independent review of the exact validated v10 candidate.

## Next Experiment

Run the canonical validator natively against the exact v10 candidate. The active suite must contain 90 cases. Preserve exact HEAD/Python/command/output/exit provenance and commit that evidence before independent review. Only after native PASS obtain a fresh independent re-review. Do not start S003 beforehand.

## Authority Grade

`Research / R`
