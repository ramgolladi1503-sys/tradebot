# S002 — Deterministic Constitution Contract Implementation

Program: MROS  
Milestone: M1 — Research Governance  
Work Package: WP001 — Research Constitution  
Sprint: S002  
Status: V9_CLASSIFICATION_SCHEMA_REPAIR_PENDING_NATIVE_VALIDATION  
Authority: `Research / R`  
Runtime authority: `NONE`

## Objective

Operationalize the frozen S001 interface as deterministic, fail-closed governance validation without changing RC-001 through RC-010 or granting runtime authority.

## Canonical Validation Surface

Canonical validator:

`scripts/mros/validate_s002_fixtures.py`

It loads six preserved corpora:

1. `S002_FIXTURES.json` — v4 baseline/regression;
2. `S002_FIXTURES_V5_ADDENDUM.json` — bootstrap-review closure;
3. `S002_FIXTURES_V6_GATE_BINDING.json` — syntactic new-evidence binding/lineage;
4. `S002_FIXTURES_V7_GATE_SEMANTIC_BINDING.json` — semantic requested-gate binding;
5. `S002_FIXTURES_V8_INHERITED_GATE_PROVENANCE.json` — inherited mandatory provenance and exact gate-key schema;
6. `S002_FIXTURES_V9_CLASSIFICATION_SCHEMA.json` — malformed mandatory-ref type precedence, unknown classification-signal rejection, and canonical classification provenance.

Historical superseded cases remain in Git history/evidence but are excluded from the active suite. Active case IDs must be unique. Fixture loading/schema failures exit non-zero.

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
- return `INVALID_INPUT / E021` for non-string mandatory evidence refs rather than `REVIEW_REQUIRED`/`BLOCKED`;
- require inherited mandatory gate evidence to be canonical and present in declared prior provenance;
- require `new_evidence_gate_bindings` to contain exactly the gates required for the requested transition;
- bind each requested gate to the same canonical genuinely new evidence identity used by its authoritative gate field;
- reject stale/unrelated gate evidence and malformed binding metadata.

## Constitutional Fail-Closed Semantics

Partial requests fail closed. Causal-time, runtime, denominator, scope, enums, timestamps, and malformed schema paths remain controlled. Runtime cannot create research authority.

## RC-009

Confirmatory denominator changes after outcomes are inspected fail E008/E009. Legitimate preregistered unchanged contracts remain valid. Changed post-hoc exploratory analyses require a new analysis identity/rationale, preserved original result, multiplicity accounting, and reduced authority.

## Review History

The genuinely independent review of exact candidate `7e7a0d8fc747b6376c5b1016c2bdb606a64b9c79` returned `S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED` with 2 MAJOR findings, 0 CRITICAL, 0 MINOR, and 0 mandatory UNKNOWN.

`7E7A-F-001` found non-string inherited mandatory refs were fail-closed but misclassified as `REVIEW_REQUIRED`/`BLOCKED` instead of schema-invalid. v9 now distinguishes missing semantic evidence from malformed type and returns `INVALID_INPUT / E021` for non-string refs.

`7E7A-F-002` found unknown classification signals were silently discarded, allowing recognized+unknown inputs to PASS. v9 rejects any unrecognized signal. The reviewer also noted classification provenance accepted arbitrary strings; v9 resolves that adjacent ambiguity by requiring canonical `EVID-*` identities for `OBSERVED_FACT` and `INFERENCE`.

## Non-Goals

S002 does not accept itself, accept WP001, start S003/M2/M9, authorize Review/Audit Boards, or modify strategy/broker/risk/execution/runtime behavior.

## Observed Facts

- Candidate `7e7a0d8f...` had native 82/82 PASS but failed fresh independent review on two genuine fail-closed contract defects.
- The review is preserved at `S002_INDEPENDENT_RE_REVIEW_7E7A_FINAL.md`.
- v9 adds six direct regression cases C091-C096.

## Inferences

v9 closes the two reported MAJOR findings and the adjacent classification-provenance ambiguity without weakening promotion, runtime, causal-time, or denominator controls.

## Hypotheses

The v9 repair is correct; this remains unproven until exact-head native validation and fresh independent re-review.

## Destroyers / Falsifiers

S002 remains unacceptable if non-string mandatory refs are not schema-invalid, unknown classification signals can still PASS, malformed classification provenance can still PASS, or any previous fail-closed behavior regresses.

## Unknowns

- exact-head native validation for v9;
- fresh bootstrap-independent review of the exact validated v9 candidate.

## Next Experiment

Run the canonical validator natively against the exact v9 candidate. The active suite should contain 88 cases. Preserve exact HEAD/Python/command/output/exit provenance. Only after PASS obtain a fresh independent re-review. Do not start S003 beforehand.

## Authority Grade

`Research / R`
