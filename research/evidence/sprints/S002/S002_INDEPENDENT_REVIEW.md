# S002 Independent Review — Repaired Head

Program: MROS
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Sprint: S002
Reviewer role: Independent reviewer; did not implement or direct the S002 repair
Branch: `research/mros-program-v1`
Reviewed HEAD: `ac3429b88709f313037c0f124fc1545e51d2b36c`
Accepted S001 baseline: `9afbd8208acf667059cf8ac191f58b534cbf68d7`
Authority: `Research / R`
Runtime authority: `NONE`
Final verdict: `S002_INDEPENDENT_REVIEW_REPAIR_REQUIRED`

## Independence and scope

This review does not modify the S002 implementation to obtain a passing result. It reviews the exact repaired S002 head, consumes the supplied native execution evidence, attacks the S002 controls beyond the frozen fixture cases, verifies the S001 contract boundary, and checks the S001→S002 diff for out-of-scope contamination. It does not advance program state, accept S002, start S003, or grant runtime authority.

## Exact-head pin

Immediately before review and again immediately before this artifact was written, repository comparison showed:

- base: `ac3429b88709f313037c0f124fc1545e51d2b36c`
- head: `research/mros-program-v1`
- status: `identical`
- ahead: 0
- behind: 0

The review target therefore did not move during the substantive review.

## Native validation evidence consumed

The reviewer consumed the supplied native execution record for the exact reviewed head:

```text
HEAD=ac3429b88709f313037c0f124fc1545e51d2b36c
COMMAND=python3 scripts/mros/validate_s002_fixtures.py
PYTHON=Python 3.12.2
RESULT=23/23 PASS
EXIT_CODE=0
```

The reviewed fixture file contains exactly 23 cases, `S002-C001` through `S002-C023`, and the reviewed validator is the implementation targeted by that record. The green native run proves that the committed 23 expected cases agree with the validator. It does not prove that unrepresented adversarial inputs fail closed.

At the reviewed HEAD, `MROS_PROGRAM_STATE.yaml` and `SPRINT_LEDGER.jsonl` still describe the native-validation gate as pending. That status is preserved here rather than rewritten by the reviewer. The primary MROS session remains responsible for sealing acceptance evidence after a valid passing independent review; this review does not do so.

## Reviewed sources

- `research/evidence/sprints/S001/S001_INTERFACE_CONTRACT.md`
- `research/governance/AUTHORITY_GRADES.md`
- `research/evidence/sprints/S002/S002_CONTRACT_IMPLEMENTATION.md`
- `research/evidence/sprints/S002/S002_FIXTURES.json`
- `scripts/mros/validate_s002_fixtures.py`
- `research/evidence/sprints/S002/S002_INDEPENDENT_REVIEW_BLOCKER.md`
- `research/evidence/sprints/S002/S002_NATIVE_VALIDATION_BLOCKER.md`
- `research/program/MROS_PROGRAM_STATE.yaml`
- `research/program/SPRINT_LEDGER.jsonl`
- S001 accepted baseline → repaired S002 HEAD repository diff

## S001 contract compatibility

The additive S002 enum codes:

- `MROS-S002-E018-INVALID_KNOWLEDGE_CLASS_ENUM`
- `MROS-S002-E019-INVALID_VERDICT_ENUM`
- `MROS-S002-E020-INVALID_STATUS_ENUM`

are additive and fail closed to `INVALID_INPUT`. They do not rename, weaken, or supersede S001 E001–E017. This part passes.

The S001 contract, however, also requires missing decision-critical inputs to fail closed, evidence provenance for authority-bearing validation, explicit independence/calibration requirements where applicable, no unsupported stage skipping, and denominator/exclusion metadata sufficient to detect contract changes. Those requirements are not fully enforced by the repaired S002 validator.

## Adversarial review matrix

| Attack | Result | Classification |
|---|---|---|
| E001 missing `statement_text` in classification | Fixture C016 returns `INVALID_INPUT` / E001 | PASS |
| E001 empty constitutional validation input | `VALIDATE_CONSTITUTIONAL_ACTION` with `{}` returns `PASS` because `constitutional()` has no minimum required action fields | MAJOR |
| E003 invalid authority enum | Fixture C017 returns `INVALID_INPUT` / E003 | PASS |
| E006 independent attack explicitly required but missing | Fixture C018 returns `REVIEW_REQUIRED` / E006 | PASS for declared flag; bypass exists when requirement flag is omitted |
| E010 calibration explicitly required but missing | Fixture C019 returns `BLOCKED` / E010 | PASS for declared flag; bypass exists when requirement flag is omitted |
| Grade C → Grade B with only `new_evidence_refs` | Returns `PASS`, because Grade-B replication/calibration requirements are enforced only if the caller self-declares `requires_independent_attack` / `requires_calibration` | MAJOR |
| Rejected/Unknown → Grade A/A+ with new evidence | Can return `PASS`; `Rejected` and `Unknown` are accepted authority values but are absent from `STAGES`, so stage-skip enforcement is bypassed | MAJOR |
| E015 promotion provenance explicitly false | Fixture C020 returns `INVALID_INPUT` / E015 | PASS for explicit false |
| Direct-measurement classification without `evidence_refs` | Returns `PASS` / `OBSERVED_FACT`; classifier does not require provenance for a claim classified as observed fact | MAJOR |
| Invalid knowledge-class enum | Fixture C021 returns `INVALID_INPUT` / S002-E018 | PASS |
| Invalid verdict enum | Fixture C022 returns `INVALID_INPUT` / S002-E019 | PASS |
| Invalid status enum | Fixture C023 returns `INVALID_INPUT` / S002-E020 | PASS |
| Future information after decision timestamp | Fixture C009 returns `FAIL` / E007 / RC-008 | PASS |
| Post-hoc denominator change explicitly declared | Fixture C010 returns `FAIL` / E008+E009 / RC-009 | PASS for declared boolean |
| Denominator laundering detection without self-declared violation flag | Validator does not compare frozen denominator/exclusion metadata and can return `PASS` when the caller omits `denominator_changed_after_outcome`; this does not satisfy S001's requirement for metadata sufficient to detect contract changes | MAJOR |
| Runtime authority creation explicitly declared | Fixture C011 returns `FAIL` / E011 / RC-010 | PASS |
| Unrecorded supersession | Fixture C014 returns `FAIL` / E012 / RC-006 | PASS |
| Non-falsifiable material claim | Fixture C012 returns `FAIL` / E013 / RC-007 | PASS |
| Unsupported completion claim | Fixture C013 returns `FAIL` / E016 | PASS |
| Scope drift | Fixture C015 returns `FAIL` / E014 / RC-001 | PASS |
| Obsolete A0–A5 authority | Fixture C008 returns `INVALID_INPUT` / E017 | PASS |

## Findings

### F-001 — MAJOR — Missing/empty constitutional action can silently PASS

`constitutional()` returns `PASS` when no recognized validation-relevant field is supplied. Therefore an empty or structurally insufficient `VALIDATE_CONSTITUTIONAL_ACTION` request can be interpreted as satisfying governance rather than `INVALID_INPUT`, `UNKNOWN`, `BLOCKED`, or `REVIEW_REQUIRED`.

This conflicts with the frozen S001 rule that missing fields required for a decision must fail closed and that an indeterminate required semantic output must not default to PASS.

Required repair: define a minimum deterministic constitutional-action input contract or action subtype and return E001/`INVALID_INPUT` (or another frozen fail-closed status where appropriate) when the requested validation cannot be determined.

### F-002 — MAJOR — Strong-grade promotion gates are caller-optional

`promotion()` enforces independent attack and calibration only when the caller supplies `requires_independent_attack=true` and `requires_calibration=true`. A caller can omit both flags and obtain `PASS` for a one-stage promotion such as `Grade C → Grade B` with only a non-empty `new_evidence_refs` list.

`AUTHORITY_GRADES.md` defines Grade B as requiring independent or meaningfully distinct replication and calibrated statistical authority. The frozen S001 contract requires explicit independence/calibration requirements where applicable. These requirements cannot safely depend on a caller volunteering the fact that they are required.

Required repair: derive mandatory gates from the requested authority transition / governed claim type, or require a complete predeclared gate contract and fail closed when it is absent. Do not default omitted gate-requirement fields to `False` for authority-bearing promotion.

### F-003 — MAJOR — Stage-skip protection is bypassable from `Rejected` and `Unknown`

`Rejected` and `Unknown` are valid values in `AUTH`, but they are not present in `STAGES`. The stage-skip check executes only when both current and requested authorities are in `STAGES`. Consequently transitions such as `Rejected → Grade A+` or `Unknown → Grade A` can fall through to `PASS` when `new_evidence_refs` is non-empty.

This violates the frozen no-stage-skipping invariant and permits unsupported authority promotion from non-promotable/insufficient-evidence states.

Required repair: define explicit legal transitions for `Rejected` and `Unknown` and fail closed on any undeclared transition. A non-stage authority value must never disable transition validation.

### F-004 — MAJOR — Evidence provenance is not mandatory for observed-fact classification

`classify()` requires `statement_text` and `classification_signals` but does not require `evidence_refs`. A statement with `DIRECT_MEASUREMENT` therefore returns `PASS` / `OBSERVED_FACT` even when no evidence provenance is supplied.

The S001 contract defines observed facts as directly evidence-supported and requires evidence/provenance obligations for authority-bearing validation. S002's current behavior permits a caller-provided signal label to manufacture an observed-fact classification without provenance.

Required repair: for `DIRECT_MEASUREMENT` / `OBSERVED_FACT`, require the evidence/provenance reference(s) needed by the frozen contract or fail closed. Similar operation-specific provenance requirements should be explicit rather than caller-optional.

### F-005 — MAJOR — RC-009 detection relies on a self-declared laundering boolean

The RC-009 fixture proves only that the validator rejects an already-declared `denominator_changed_after_outcome=true`. The validator does not compare `experiment_contract_ref`, denominator definitions, exclusion rules, population identities, or before/after contract metadata. Omitting the self-accusing boolean allows the constitutional check to return `PASS` even though S001 explicitly requires denominator/exclusion metadata sufficient to detect contract changes.

This is not an implementation of denominator-laundering detection; it is enforcement after the caller declares the violation.

Required repair: make the S002 fixture/schema carry enough frozen/current denominator and exclusion identity to deterministically detect a contract change, or fail closed when confirmatory denominator provenance is insufficient. Preserve legitimate preregistered exclusions and separately identified exploratory post-hoc analysis semantics.

## Scope / contamination review

Comparison from accepted S001 baseline `9afbd8208acf667059cf8ac191f58b534cbf68d7` to reviewed S002 HEAD `ac3429b88709f313037c0f124fc1545e51d2b36c` shows only:

- `research/evidence/sprints/S002/S002_CONTRACT_IMPLEMENTATION.md`
- `research/evidence/sprints/S002/S002_FIXTURES.json`
- `research/evidence/sprints/S002/S002_INDEPENDENT_REVIEW_BLOCKER.md`
- `research/evidence/sprints/S002/S002_NATIVE_VALIDATION_BLOCKER.md`
- `research/program/MROS_PROGRAM_STATE.yaml`
- `research/program/SPRINT_LEDGER.jsonl`
- `scripts/mros/validate_s002_fixtures.py`

No S003, runtime, M2, strategy, broker, risk, execution, or M9 implementation path is changed. Scope contamination check passes.

## Finding counts

- MINOR: 0
- MAJOR: 5
- CRITICAL: 0
- UNKNOWN: 0

## Final verdict

`S002_INDEPENDENT_REVIEW_REPAIR_REQUIRED`

The native 23/23 green result is valid evidence that the declared fixtures agree with the validator, but the fixture set misses authority-bearing fail-closed bypasses. S002 does not deserve acceptance at this head because strong-grade promotion, non-stage authority transitions, observed-fact provenance, empty constitutional actions, and denominator-laundering detection are not enforced safely enough under the frozen S001 contract.

S002 must remain unaccepted and S003 must remain unstarted until repairs are made, natively validated on the exact repaired head, and independently re-reviewed. This reviewer does not repair the implementation and does not advance program state.
