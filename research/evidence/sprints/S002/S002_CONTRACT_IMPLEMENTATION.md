# S002 — Deterministic Constitution Contract Implementation

Program: MROS
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Sprint: S002
Status: ACTIVE
Authority: `Research / R`
Runtime authority: `NONE`

## Objective

Operationalize the frozen S001 interface with deterministic, machine-checkable fixtures and validation rules without changing RC-001 through RC-010 or the frozen authority semantics.

## Implemented Fixture Model

S002 uses JSON fixtures with:

- `case_id`
- `operation`
- `input`
- `expected.status`
- `expected.knowledge_class` where applicable
- `expected.can_promote` where applicable
- `expected.error_codes`
- `expected.violated_rules`

Allowed operations are `CLASSIFY_STATEMENT`, `VALIDATE_PROMOTION`, and `VALIDATE_CONSTITUTIONAL_ACTION`.

## Deterministic Classification Rules

Classification fixtures are intentionally explicit rather than probabilistic:

- direct recorded measurement with evidence provenance → `OBSERVED_FACT`;
- reasoned conclusion derived from recorded facts → `INFERENCE`;
- falsifiable unverified proposition → `HYPOTHESIS`;
- unsupported/conjectural proposition → `SPECULATION`;
- statement satisfying multiple primary classes without sufficient disambiguation → `UNKNOWN`/`REVIEW_REQUIRED` with `MROS-S001-E002-AMBIGUOUS_KNOWLEDGE_CLASS`.

No language model confidence score is authority evidence.

## Promotion Rules

Promotion fixtures fail closed when:

- no genuinely new evidence is referenced;
- a stage is skipped;
- mandatory independent attack is absent;
- calibration required by the requested grade is absent;
- evidence provenance is absent;
- obsolete A0–A5 authority tokens appear.

## Constitutional Action Rules

Fixtures explicitly attack:

- future-data use;
- post-hoc denominator/exclusion changes;
- runtime-created research authority;
- silent supersession;
- non-falsifiable material claims;
- scope drift;
- unsupported completion claims.

## S001 Minor Finding Closure Target

S002 includes an explicit negative fixture for obsolete `A0–A5` authority values. This closes the executable-coverage gap recorded as `RR-F-002` if targeted validation proves the fixture is actually enforced. The historical finding remains preserved; it is not rewritten away.

## Non-Goals

S002 does not accept WP001, change the Constitution, start M2, certify market claims, or grant runtime authority.

## Observed Facts

S001 was independently accepted with one non-blocking minor verification-description mismatch.

## Inferences

A deterministic fixture corpus can make the frozen constitutional semantics executable without expanding the architecture.

## Hypotheses

The fixture corpus will expose semantic regressions before later MROS governance components depend on them.

## Assumptions

S001 frozen contract remains authoritative.

## Destroyers / Falsifiers

Any fixture that permits authority promotion without new evidence, accepts obsolete authority grades, coerces Unknown to PASS, or allows runtime to manufacture research truth invalidates S002.

## Unknowns

Targeted executable validation and independent attack of S002 are not yet sealed.

## Next Experiment

Execute the deterministic S002 fixture validator and negative controls against the exact repository HEAD.

## Authority Grade

`Research / R`
