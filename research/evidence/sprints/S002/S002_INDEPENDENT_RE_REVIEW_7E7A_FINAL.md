# MROS S002 — Bootstrap-Independent Re-Review of 7e7a (Final)

## Controlled verdict

`S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED`

Finding counts:

- CRITICAL: 0
- MAJOR: 2
- MINOR: 0
- mandatory UNKNOWN: 0

S002 is **not acceptance-eligible** because `MAJOR != 0`.

---

## Reviewer independence statement

This review was performed as a fresh bootstrap-independent review of the frozen candidate. I did not implement S002, direct S002 repairs, design the S002 validator/fixtures, implement the Review Board or Audit Board, or aggregate a prior S002 review. Prior review artifacts were used only as adversarial targets and historical evidence; they were not treated as authoritative conclusions.

The repository and frozen exact candidate were treated as the authority. No implementation, fixture, expected-result, state, acceptance, runtime, strategy, broker, risk, or execution changes were made by this review.

---

## Exact reviewed candidate and native evidence

Reviewed candidate:

`7e7a0d8fc747b6376c5b1016c2bdb606a64b9c79`

Candidate commit message:

`mros(S002): keep v8 active corpus at four targeted attacks [skip ci]`

Native validation evidence commit:

`6122212c04c6aeab8f5ffb64b9789e4e9ed521ce`

Native validation artifact:

`research/evidence/sprints/S002/S002_NATIVE_VALIDATION_OUTPUT_82_CASES.txt`

Consumed native evidence records:

- checkout HEAD: `7e7a0d8fc747b6376c5b1016c2bdb606a64b9c79`
- Python: `3.12.2`
- validator: `scripts/mros/validate_s002_fixtures.py`
- checks: `82`
- pass: `82`
- fail: `0`
- marker: `S002_TARGETED_VALIDATION_PASS`
- exit: `0`

### Exact-head provenance conclusion

**MATCH CONFIRMED.** The native artifact explicitly detached to and printed the exact reviewed candidate SHA before executing the validator. The evidence commit is later than the candidate and contains the captured validation output, not an implementation substitution.

The branch has later governance/evidence commits after `7e7a`; comparison from the candidate to the review-request branch state shows only native evidence, program state/ledger governance updates, and the frozen review request. Those later commits were not treated as candidate implementation.

Native 82/82 PASS is accepted only as regression evidence, not certification.

---

## Review method

The review inspected the exact candidate source and active fixture corpora, then independently attacked behavior beyond the committed 82 fixtures. In particular, the review read the exact `promotion`, `classify`, enum, denominator, timestamp, constitutional, dispatch, fixture-loading, and exception-control paths from the frozen candidate and exercised adversarial input variants against those semantics.

No repair was attempted.

---

## Mandatory v8 re-attack matrix

### A. Inherited mandatory evidence provenance

Targeted `Grade B -> Grade A` and `Grade A -> Grade A+` inherited mandatory evidence.

| Attack | Observed behavior | Result |
|---|---|---|
| malformed inherited string | `INVALID_INPUT / E021` | PASS |
| canonical-looking inherited ref absent from prior `evidence_refs` | `INVALID_INPUT / E015` | PASS |
| duplicate prior evidence refs | `INVALID_INPUT / E021` | PASS |
| inherited mandatory ref points to a `new_evidence_refs` member instead of prior provenance | provenance failure | PASS |
| lower-case / surrounding-whitespace spelling of an otherwise registered identity | canonicalized before comparison | ACCEPTABLE NORMALIZATION; no bypass found |
| missing `independent_attack_ref` | `REVIEW_REQUIRED / E006` | expected semantic missing-gate control |
| missing `calibration_ref` | `BLOCKED / E010` | expected semantic missing-gate control |
| non-string `independent_attack_ref` | `REVIEW_REQUIRED / E006`, not `INVALID_INPUT` | **FAIL — MAJOR F-001** |
| non-string `calibration_ref` | `BLOCKED / E010`, not `INVALID_INPUT` | **FAIL — MAJOR F-001** |

### Finding `7E7A-F-001` — MAJOR

**Mandatory inherited-ref type precedence is still wrong for non-string values.**

The required v8 behavior states that malformed inherited refs must produce controlled `INVALID_INPUT`. The exact candidate performs an early `nonempty_str(...)` presence check for mandatory `independent_attack_ref` / `calibration_ref` before the later canonical schema validation. Therefore a non-string value such as an integer is treated as if the evidence were semantically missing:

- malformed `independent_attack_ref = 123` -> `REVIEW_REQUIRED / E006`;
- malformed `calibration_ref = 123` -> `BLOCKED / E010`.

Both are fail-closed (`can_promote=false`), so this is **not** the old fail-open defect. However, it directly violates the mandatory v8 re-review contract requiring malformed inherited refs to be classified as `INVALID_INPUT`. The input is a schema/type error, not a review/calibration state.

Severity is MAJOR because this is an explicit mandatory repaired-contract condition, not an optional diagnostic preference.

---

### B. Exact gate-binding schema

Attacked all transition shapes represented by the common promotion logic, including `Research / R -> Grade C`, `Grade C -> Grade B`, `Grade B -> Grade A`, and `Grade A -> Grade A+`.

The candidate now enforces:

`set(new_evidence_gate_bindings) == set(required_gates)`

and canonical equivalence between each required binding, the authoritative gate field, and a member of `new_evidence_refs`.

Observed attacks:

| Attack | Observed behavior | Result |
|---|---|---|
| missing required gate key | `INVALID_INPUT / E021` | PASS |
| extra known gate key | `INVALID_INPUT / E021` | PASS |
| extra unknown gate key | `INVALID_INPUT / E021` | PASS |
| bindings object is list/non-dict | `INVALID_INPUT / E021` | PASS |
| malformed/null required gate value | `INVALID_INPUT / E021` | PASS |
| required binding points to old evidence | `FAIL / E005 / RC-002` | PASS |
| required binding points to unrelated new evidence | `FAIL / E005 / RC-002` | PASS |
| binding differs from authoritative gate metadata | `FAIL / E005 / RC-002` | PASS |
| authoritative gate metadata absent | `INVALID_INPUT / E001` | PASS |
| valid positive controls | `PASS / can_promote=true` | PASS |

No extra known gate can now be silently ignored. The second limb of `8E872-V2-F-001` is closed.

---

## Closure status of previous blocker `8E872-V2-F-001`

**CLOSED AS TO THE ORIGINAL FAIL-OPEN BEHAVIORS.**

The candidate now fails closed when inherited mandatory evidence is malformed/not registered in declared prior provenance, and it rejects both extra known and extra unknown binding keys.

The new `7E7A-F-001` is a related but distinct type-precedence defect: non-string inherited mandatory refs no longer PASS, but they return the wrong controlled status/error class rather than `INVALID_INPUT`.

---

## C073 semantic-precedence re-check

Historical C073 is not accepted merely because its expected result was changed. The exact promotion logic distinguishes the three semantic failure classes required by this review:

1. **Malformed inherited evidence metadata** such as `ATTACK-META` / `CAL-META` -> `INVALID_INPUT / E021`.
2. **Syntactically valid old gate evidence bound as if it were new** -> `FAIL / E005 / RC-002` (no-new-evidence failure).
3. **Syntactically valid inherited mandatory evidence absent from declared complete prior provenance** -> `INVALID_INPUT / E015` (provenance failure).

No fail-open PASS was found in these three C073 classes.

**C073 precedence check: PASS.**

---

## Broader adversarial review

The 82-fixture regression suite was not treated as exhaustive.

### Finding `7E7A-F-002` — MAJOR

**`CLASSIFY_STATEMENT` silently ignores unrecognized classification signals and can return PASS.**

The exact candidate constructs the classification set only from signals present in the hard-coded mapping:

`classes = {mapping[x] for x in set(classification_signals) if x in mapping}`

This means unknown tokens are discarded instead of rejected.

Two concrete adversarial examples:

1. `classification_signals = ["DIRECT_MEASUREMENT", "UNKNOWN_SIGNAL"]` with a non-empty evidence ref returns `PASS / OBSERVED_FACT`.
2. `classification_signals = ["FALSIFIABLE_UNVERIFIED", "GARBAGE"]` returns `PASS / HYPOTHESIS`.

The malformed/unrecognized input does not become `INVALID_INPUT` or `REVIEW_REQUIRED`; the unknown signal simply disappears. That is exactly an **unrecognized path that silently returns PASS**, which the final review request explicitly requires attacking.

Impact: a caller can attach arbitrary unsupported classification metadata to a recognized signal and still obtain a successful controlled knowledge classification. For a governance validator whose stated objective is deterministic fail-closed behavior, silently dropping unknown input is a real fail-open schema defect.

Severity: **MAJOR**.

### Additional classification provenance observation

For `OBSERVED_FACT` / `INFERENCE`, the current implementation checks only that `evidence_refs` is a non-empty list of non-empty strings. It does not canonicalize those references as `EVID-*`. Thus a value such as `"not-an-evid"` is accepted as provenance and can yield `PASS / OBSERVED_FACT`.

The S002 implementation document phrases classification as requiring “provenance” but does not explicitly say classification evidence references must use the same canonical registry grammar enforced by promotion. I therefore did **not** create a separate blocking count for this ambiguity. It should be resolved when repairing F-002 rather than silently assumed either way.

### Other broader attacks / source checks

| Area | Result |
|---|---|
| empty operation / unrecognized operation | controlled `INVALID_INPUT`; no PASS |
| partial constitutional requests | fail closed via required-field checks |
| classification ambiguity among recognized classes | `REVIEW_REQUIRED / E002` |
| invalid controlled enums / malformed enum types | controlled invalid result; no PASS |
| obsolete `A0-A5` | `INVALID_INPUT / E017` |
| authority stage skipping | `FAIL / E004 / RC-002` |
| `Rejected` / `Unknown` promotion attempts | fail stage-skip |
| empty new evidence refs | no-new-evidence failure |
| duplicate new evidence refs | schema-invalid |
| old/new canonical overlap | no-new-evidence failure |
| caller-controlled `requires_independent_attack` / `requires_calibration` booleans | malformed types fail closed; true requirements cannot force PASS |
| required Grade B/A/A+ independent/calibration semantics | no PASS when semantically absent |
| malformed timestamps | controlled schema-invalid |
| timezone-naive timestamps | controlled schema-invalid |
| future input timestamp relative to decision | `FAIL / E007 / RC-008` |
| confirmatory post-outcome denominator mutation | `FAIL / E008+E009 / RC-009` |
| legitimate preregistered unchanged denominator | PASS control preserved |
| legitimate separately declared exploratory post-hoc analysis | PASS only with required identity/rationale/original-preservation/multiplicity/reduced-authority controls |
| contradictory confirmatory + exploratory state | invalid schema |
| runtime authority creation (`runtime_context=true`, promotion=true) | `FAIL / E011 / RC-010` |
| contradictory runtime inputs | fail closed |
| non-falsifiable material claims | `FAIL / E013 / RC-007` |
| unsupported completion claim | `FAIL / E016` |
| silent supersession | `FAIL / E012 / RC-006` |
| scope drift | `FAIL / E014 / RC-001` |
| malformed schema / unexpected evaluation exception in fixture runner | runner converts to controlled `INVALID_INPUT / E021`; no fixture PASS is manufactured unless expected exactly matches it |

No additional CRITICAL finding was identified.

---

## Candidate contamination check

Candidate boundary was checked using the exact frozen commit and comparison against the prior blocked candidate.

From `8e87223efdb33bc73b58436cf590b7f3c7c10717` through `7e7a0d8fc747b6376c5b1016c2bdb606a64b9c79`, changed paths are confined to S002 governance/evidence artifacts, `research/program/MROS_PROGRAM_STATE.yaml`, `research/program/SPRINT_LEDGER.jsonl`, and `scripts/mros/validate_s002_fixtures.py`.

No candidate changes were found in strategy, broker, risk, execution, market runtime, or order behavior code.

Candidate state confirms:

- active milestone: `M1`
- active work package: `WP001`
- active sprint: `S002`
- `M2 = NOT_STARTED`
- `M9 = NOT_STARTED`
- Review Board = `IMPLEMENTED_NOT_CALIBRATED`
- Audit Board = `IMPLEMENTED_NOT_CALIBRATED`
- autonomous authority = `NOT_AUTHORIZED`
- runtime authority = `NONE`

No unauthorized S003/M2/M9/runtime/strategy/broker/risk/execution implementation contamination was found in the candidate.

**Contamination check: PASS.**

---

## Acceptance gate

Required:

- CRITICAL = 0
- MAJOR = 0
- mandatory UNKNOWN = 0

Observed:

- CRITICAL = 0
- MAJOR = 2
- MINOR = 0
- mandatory UNKNOWN = 0

Therefore S002 does not meet the acceptance gate.

---

## Final controlled verdict

`S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED`

Hard stop. This review does not accept S002, activate S003, calibrate either board, begin M2/M9, modify implementation or fixtures, or change runtime/strategy/broker/risk/execution behavior.
