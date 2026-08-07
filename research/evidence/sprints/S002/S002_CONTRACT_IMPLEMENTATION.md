# S002 — Deterministic Constitution Contract Implementation

Program: MROS
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Sprint: S002
Status: REPAIRED_PENDING_NATIVE_VALIDATION_AND_INDEPENDENT_RE_REVIEW
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

Allowed operations are:

- `CLASSIFY_STATEMENT`
- `VALIDATE_PROMOTION`
- `VALIDATE_CONSTITUTIONAL_ACTION`
- `VALIDATE_CONTRACT_ENUMS`

## Deterministic Classification Rules

Classification fixtures are intentionally explicit rather than probabilistic:

- direct recorded measurement with evidence provenance → `OBSERVED_FACT`;
- reasoned conclusion derived from recorded facts with evidence provenance → `INFERENCE`;
- falsifiable unverified proposition → `HYPOTHESIS`;
- unsupported/conjectural proposition → `SPECULATION`;
- statement satisfying multiple primary classes without sufficient disambiguation → `REVIEW_REQUIRED` with `MROS-S001-E002-AMBIGUOUS_KNOWLEDGE_CLASS`;
- `OBSERVED_FACT` or `INFERENCE` without evidence provenance → `INVALID_INPUT` with `MROS-S001-E015-EVIDENCE_PROVENANCE_MISSING`.

No language-model confidence score is authority evidence.

## Promotion Rules

Promotion is fail-closed and uses explicit legal transitions:

- `Research / R` → `Grade C`
- `Grade C` → `Grade B`
- `Grade B` → `Grade A`
- `Grade A` → `Grade A+`

`Rejected` and `Unknown` do not silently re-enter the promotion ladder. Any undeclared transition fails with `MROS-S001-E004-AUTHORITY_STAGE_SKIP` / RC-002 and requires a separately governed claim/evidence path rather than an implicit promotion.

Promotion always requires genuinely new evidence. Strong-grade requirements are derived from the requested grade rather than caller-supplied `requires_*` booleans:

- `Grade B` requires independent-attack/replication evidence and calibration evidence;
- `Grade A` additionally requires scientific-certification and economic-certification references;
- `Grade A+` requires the strong-grade independence/calibration evidence plus live/forward evidence and monitoring evidence.

Explicit caller-supplied independence/calibration requirements remain honored for lower-grade cases, but callers cannot suppress requirements that are mandatory for the requested grade.

## Constitutional Action Rules

A constitutional-action request with no recognizable decision surface is `INVALID_INPUT` / E001 rather than PASS. Paired causal-time, runtime, and scope fields also fail closed when structurally incomplete.

Fixtures explicitly attack:

- future-data use;
- post-hoc denominator/exclusion changes;
- runtime-created research authority;
- silent supersession;
- non-falsifiable material claims;
- scope drift;
- unsupported completion claims.

### RC-009 denominator contract

Confirmatory denominator validation no longer relies on a caller declaring `denominator_changed_after_outcome=true`.

For confirmatory or explicitly exploratory post-hoc denominator analysis, S002 requires:

- `experiment_contract_ref`;
- `outcomes_inspected`;
- `frozen_denominator_contract`;
- `current_denominator_contract`.

Each denominator contract must carry at least:

- `denominator_definition`;
- `exclusion_rule_refs`;
- `population_identity`;
- `horizon`;
- `regimes`;
- `symbols`;
- `dates_ref`;
- `search_family_id`.

A confirmatory frozen/current contract change after outcomes are inspected fails with E008/E009 / RC-009.

A scientifically justified exploratory post-hoc change is permitted only when the original result is preserved, a new analysis identity and rationale are supplied, multiplicity is accounted for, and authority is explicitly reduced. This preserves the original S001 RC-009 semantics rather than laundering the changed denominator into the confirmatory result.

A preregistered data-quality exclusion represented identically in the frozen/current contract remains valid.

## S002 Repair Response

The independent review of HEAD `ac3429b88709f313037c0f124fc1545e51d2b36c` returned `S002_INDEPENDENT_REVIEW_REPAIR_REQUIRED` with five MAJOR findings. The repair addresses them as follows:

| Finding | Repair |
|---|---|
| F-001 empty constitutional action silently PASS | minimum recognizable action surface + conditional required-field checks; empty input → E001 / `INVALID_INPUT` |
| F-002 strong-grade gates caller-optional | grade-derived mandatory independence/calibration and higher-grade evidence requirements |
| F-003 `Rejected`/`Unknown` bypass stage checks | explicit legal transition map; undeclared transitions fail closed |
| F-004 observed fact without provenance | `OBSERVED_FACT` and `INFERENCE` require `evidence_refs`; missing provenance → E015 |
| F-005 RC-009 self-declared laundering boolean | frozen/current denominator-contract metadata comparison with confirmatory and exploratory semantics |

The fixture corpus is expanded from 23 to 39 cases. The previous native `23/23 PASS` evidence remains preserved but is no longer sufficient for this repaired implementation.

## S001 Minor Finding Closure Target

S002 retains an explicit negative fixture for obsolete `A0–A5` authority values. This continues to exercise the executable-coverage gap recorded as S001 `RR-F-002`; historical evidence remains preserved.

## Non-Goals

S002 does not accept WP001, change the Constitution, start S003, start M2, certify market claims, modify TradeBot runtime, or grant runtime authority.

## Observed Facts

- S001 was accepted with one non-blocking minor finding.
- The first independent S002 review of `ac3429b88709f313037c0f124fc1545e51d2b36c` found five MAJOR fail-closed gaps.
- The repaired fixture corpus contains 39 cases.

## Assumptions

The frozen S001 contract and current authority-grade definitions remain authoritative.

## Destroyers / Falsifiers

S002 remains unacceptable if any adversarial input can:

- obtain PASS from an empty/indeterminate governance request;
- promote without mandatory gate evidence;
- bypass legal authority transitions;
- create an observed fact without provenance;
- launder a post-outcome denominator change into confirmatory evidence;
- accept obsolete authority grades;
- coerce Unknown/Blocked/Invalid/Review Required into PASS;
- create research authority from runtime.

## Unknowns

Native exact-checkout execution of the repaired 39-case validator has not yet been sealed. A fresh independent reviewer has not yet reviewed the exact native-validated repaired HEAD.

## Next Gate

1. Pin the exact final repaired S002 HEAD.
2. Run `python3 scripts/mros/validate_s002_fixtures.py` natively from that checkout.
3. Preserve exact HEAD, Python version, command, stdout/stderr, case count, and exit code.
4. Obtain a separate independent re-review of that exact validated HEAD.
5. Only the primary MROS session may accept S002 and activate S003 after a passing independent re-review.

## Authority Grade

`Research / R`
