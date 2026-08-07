# S002 Repair Round 2 Evidence

Program: MROS
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Sprint: S002
Branch: `research/mros-program-v1`
Authority: `Research / R`
Runtime authority: `NONE`

## Repair source

Independent re-review commit: `027a913e7f3908147c4db6a529665b0597724f45`
Artifact: `research/evidence/sprints/S002/S002_INDEPENDENT_RE_REVIEW.md`
Verdict: `S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED`
Findings: 5 MAJOR / 0 CRITICAL / 0 MINOR / 0 UNKNOWN.

## Repairs implemented

### RR-F-001 — semantically empty constitutional requests
Required paired constitutional fields now validate semantic non-emptiness/type before rule evaluation. Empty timestamps, empty availability lists, and empty scope fields fail closed instead of falling through to PASS.

### RR-F-002 — RC-009 undeclared mode / semantically empty denominator contracts
Any denominator-related request now requires deterministic mode authority: `confirmatory: true` or `analysis_mode: EXPLORATORY_POST_HOC`. Missing/invalid mode fails closed. Nested denominator contracts now validate non-empty typed identity fields, list fields, regimes and symbols before comparison.

### RR-F-003 — contradictory runtime authority input
Runtime fields are typed booleans. A runtime authority attempt in runtime context returns RC-010/E011. Contradictory `runtime_context=false` with promotion attempt true is invalid input rather than PASS.

### RR-F-004 — reused evidence / omitted promotion provenance
Promotion now requires affirmative `evidence_provenance_complete: true` and rejects overlap between `evidence_refs` and `new_evidence_refs` as no genuinely new evidence under RC-002/E005.

### RR-F-005 — malformed schema values crash validator
Authority values are type-checked before regex use. Timestamps require parseable timezone-aware strings and malformed values map to controlled `INVALID_INPUT` / `MROS-S002-E021-INVALID_SCHEMA_TYPE` rather than uncaught exceptions.

## Fixture expansion

Canonical fixture schema advanced from `mros-s002-fixtures-v3` / 39 cases to `mros-s002-fixtures-v4` / 53 cases.

New cases include:
- empty paired causal fields;
- empty declared scope;
- denominator metadata with omitted analysis mode;
- semantically empty denominator contracts;
- contradictory runtime authority declarations;
- old evidence relabeled as new;
- omitted promotion provenance;
- non-string authority inputs;
- malformed timestamps;
- timezone-naive timestamps;
- legitimate non-runtime false/false state;
- ambiguous denominator mode declaration;
- malformed enum type;
- valid causal-time control.

Historical v3 fixtures remain preserved as prior evidence. `S002_FIXTURES_V4.json` is also preserved as the explicit repair corpus; the canonical `S002_FIXTURES.json` now carries the same v4 corpus.

## Repair commits

- semantic validator repair: `c9307ae28d3697f8f2100bcc0eb9f30dcf2cfaee`
- v4 adversarial corpus: `acb4fbbb14b1ca628d0526564bbfc7e68551445d`
- canonical v4 fixture promotion: `76c5f42234163d3dd079a0e89601e4298202f318`

## Current decision

No S002 acceptance is claimed. The previous 39/39 native PASS applies only to HEAD `834843ae2bc3222de52e0621455fbe0c763d9519` and is historical after this repair.

Required next gate:
1. native exact-checkout validation of the final repair HEAD using `python3 scripts/mros/validate_s002_fixtures.py`;
2. expected canonical case count: 53;
3. exact HEAD/Python/command/output/exit provenance;
4. fresh genuinely independent re-review of the exact native-validated head.

S003 remains `NOT_STARTED`. M2 and M9 remain `NOT_STARTED`. Runtime authority remains `NONE`.
