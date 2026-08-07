# S002 Independent Re-Review

Program: MROS
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Sprint: S002
Review role: bootstrap-independent reviewer
Branch: `research/mros-program-v1`
Reviewed exact candidate HEAD: `834843ae2bc3222de52e0621455fbe0c763d9519`
Authority: `Research / R`
Runtime authority: `NONE`
Final verdict: `S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED`

## Independence statement

This review session did not implement or direct the S002 repair and did not modify the S002 implementation to obtain a passing result. It did not use the Autonomous Review Board to certify S002 or the Board itself. The Board is treated only as post-candidate bootstrap infrastructure and remains non-authoritative for this review.

This review does not accept S002, advance program state, start S003, calibrate or authorize the Review Board, begin M2/M9, touch runtime behavior, or merge anything.

## Exact-head and evidence binding

The immutable implementation target reviewed here is:

`834843ae2bc3222de52e0621455fbe0c763d9519`

The candidate commit exists and records the repaired S002 validation blocker. The current program branch is ahead of the candidate because it contains the later native-evidence record and Review Board bootstrap infrastructure; the candidate implementation itself is unchanged and remains the review target.

Native validation evidence consumed:

- Evidence artifact: `research/evidence/sprints/S002/S002_NATIVE_VALIDATION_OUTPUT.txt`
- Evidence target HEAD: `834843ae2bc3222de52e0621455fbe0c763d9519`
- Python: `3.12.2`
- Command: `python3 scripts/mros/validate_s002_fixtures.py`
- Result: `39/39 PASS`
- Exit code: `0`
- Fixture schema: `mros-s002-fixtures-v3`
- Cases: `S002-C001` through `S002-C039`

The evidence artifact explicitly states that it is an operator-supplied terminal capture from a genuine local Git worktree and binds the run to the exact candidate HEAD. This reviewer consumes that record as the designated native implementation-side evidence; this session did not independently re-run the native validator.

The 39/39 result proves that the committed fixture expectations agree with the committed validator for those 39 cases. It does not establish fail-closed behavior for adversarial inputs not represented by the fixture corpus.

## Sources reviewed

- `research/evidence/sprints/S001/S001_INTERFACE_CONTRACT.md`
- `research/governance/AUTHORITY_GRADES.md`
- `research/evidence/sprints/S002/S002_CONTRACT_IMPLEMENTATION.md`
- `research/evidence/sprints/S002/S002_FIXTURES.json`
- `scripts/mros/validate_s002_fixtures.py`
- `research/evidence/sprints/S002/S002_INDEPENDENT_REVIEW.md`
- `research/evidence/sprints/S002/S002_REPAIR_EVIDENCE.md`
- `research/evidence/sprints/S002/S002_REPAIRED_NATIVE_VALIDATION_BLOCKER.md`
- `research/program/MROS_PROGRAM_STATE.yaml`
- `research/program/SPRINT_LEDGER.jsonl`
- accepted S001 baseline `9afbd8208acf667059cf8ac191f58b534cbf68d7` → candidate HEAD repository comparison
- current post-candidate bootstrap boundary/evidence only to confirm that S002 is still ACTIVE and the Review Board is not authoritative

## Closure status of the original 5 MAJOR findings

| Prior finding | Re-attack result | Closure |
|---|---|---|
| F-001 — empty/indeterminate constitutional action silently PASS | `{}` now fails, but recognizable fields with empty/indeterminate values can still fall through to `PASS` because the constitutional validator checks pair presence and then guards semantic checks with truthiness | **NOT CLOSED — MAJOR** |
| F-002 — strong-grade promotion gates caller-optional | `STRONG_GRADE_REQUIREMENTS` derives mandatory Grade B/A/A+ reference requirements from `authority_requested`; caller omission of `requires_*` no longer suppresses those grade-derived gates | **CLOSED for the original defect** |
| F-003 — `Rejected`/`Unknown` bypass stage validation | `LEGAL_PROMOTIONS` explicitly gives `Rejected` and `Unknown` no legal promotion transitions; attempted promotion fails E004/RC-002 | **CLOSED** |
| F-004 — observed fact without provenance | `OBSERVED_FACT` and `INFERENCE` now require non-empty `evidence_refs`; missing provenance returns E015 / `INVALID_INPUT` | **CLOSED for the original defect** |
| F-005 — RC-009 relied on self-declared laundering boolean | Frozen/current contracts are compared when the caller declares `confirmatory=true` or `analysis_mode=EXPLORATORY_POST_HOC`, but denominator-relevant changed contracts can still bypass RC-009 when mode is omitted; required nested denominator fields are also accepted solely by key presence even when semantically empty | **NOT CLOSED — MAJOR** |

## Adversarial re-review matrix

| Attack | Exact-head behavior | Result |
|---|---|---|
| E001: completely empty constitutional input `{}` | `INVALID_INPUT` / E001 | PASS |
| E001: paired but empty causal fields: `decision_timestamp=""`, `input_availability_timestamps=[]` | recognizable request; pair-presence test succeeds; time check is skipped by falsey values; falls through to `PASS` | **MAJOR** |
| E001 / RC-001: `declared_scope=""`, `attempted_scope="M2"` | both keys are present; comparison is skipped because `declared_scope` is falsey; falls through to `PASS` | **MAJOR (covered by RR-F-001)** |
| E003 invalid authority string | `INVALID_INPUT` / E003 | PASS |
| E006 lower-grade explicitly required independent attack missing | `REVIEW_REQUIRED` / E006 | PASS |
| Grade C → B without independent attack | grade-derived `REVIEW_REQUIRED` / E006 | PASS |
| Grade C → B with attack but no calibration | grade-derived `BLOCKED` / E010 | PASS |
| Grade B → A missing scientific/economic refs | `INVALID_INPUT` / E001 | PASS |
| Grade A → A+ missing live/monitoring refs | `INVALID_INPUT` / E001 | PASS |
| `Rejected` → Grade A+ | `FAIL` / E004 / RC-002 | PASS |
| `Unknown` → Grade A | `FAIL` / E004 / RC-002 | PASS |
| OBSERVED_FACT without evidence refs | `INVALID_INPUT` / E015 | PASS |
| INFERENCE without evidence refs | `INVALID_INPUT` / E015 | PASS |
| Invalid knowledge-class/verdict/status enum strings | fail closed using S002 E018/E019/E020 | PASS |
| Valid causal-time future leakage | `FAIL` / E007 / RC-008 | PASS |
| Malformed ISO timestamp | `datetime.fromisoformat(...)` can raise an uncaught exception instead of returning a controlled status | **MAJOR** |
| Confirmatory frozen/current denominator change after outcome inspection | `FAIL` / E008+E009 / RC-009 | PASS |
| Legitimate preregistered exclusion represented identically in frozen/current contracts | `PASS` | PASS |
| Separately identified exploratory post-hoc change with preservation/multiplicity/reduced authority | `PASS` | PASS |
| Changed denominator after outcomes with mode omitted | RC-009 helper declares the input not relevant and constitutional validation can fall through to `PASS` | **MAJOR** |
| Confirmatory denominator contracts with all required keys present but empty/null semantic values | nested validator checks only key presence; unchanged empty contracts can fall through to `PASS` | **MAJOR (covered by RR-F-002)** |
| Runtime authority creation with `runtime_context=true`, attempt=true | `FAIL` / E011 / RC-010 | PASS |
| Contradictory runtime input `runtime_context=false`, attempt=true | both keys are present, but violation check requires both values truthy; falls through to `PASS` | **MAJOR** |
| Silent supersession with missing decision ref | `FAIL` / E012 / RC-006 | PASS |
| Non-falsifiable material claim | `FAIL` / E013 / RC-007 | PASS |
| Unsupported completion claim | `FAIL` / E016 | PASS |
| Normal scope drift with non-empty scopes | `FAIL` / E014 / RC-001 | PASS |
| Obsolete A0–A5 authority strings | `INVALID_INPUT` / E017 | PASS |
| Promotion re-labels existing evidence as `new_evidence_refs` | no set-difference/identity check; a duplicate old ref can satisfy the non-empty new-evidence test and a legal transition can return `PASS` | **MAJOR** |
| Promotion omits `evidence_provenance_complete` | validator rejects only explicit `False`; omission does not block promotion | **MAJOR (covered by RR-F-004)** |
| Non-string authority value (for example integer) | obsolete-scale regex is applied before type validation and can raise an uncaught `TypeError` | **MAJOR (covered by RR-F-005)** |

## New / surviving findings

### RR-F-001 — MAJOR — F-001 is only partially repaired: recognizable but semantically empty constitutional requests can still PASS

The repair rejects a completely empty dictionary and one-sided paired fields, but it does not require the paired values themselves to be decision-capable.

Examples derived directly from the exact candidate control flow:

1. `{"decision_timestamp":"","input_availability_timestamps":[]}`
   - intersects the recognized constitutional key set;
   - both pair keys are present, so the pair-presence guard does not reject it;
   - the causal check is skipped because both values are falsey;
   - no other rule fires;
   - result falls through to `PASS`.

2. `{"declared_scope":"","attempted_scope":"M2"}`
   - both scope keys are present;
   - the scope comparison is guarded by truthiness of both values;
   - empty `declared_scope` suppresses the check;
   - result falls through to `PASS`.

The frozen S001 contract states that missing decision-critical fields must fail closed and that a required semantic output that cannot be determined must not default to PASS. An empty string/list in a required paired field is already treated as missing by the validator's own `missing_required()` helper, but constitutional pair handling does not use that helper consistently.

Required repair: validate required paired constitutional fields with semantic non-emptiness/type checks before any truthiness-guarded rule evaluation. Indeterminate recognized requests must return a controlled fail-closed status, not PASS.

### RR-F-002 — MAJOR — F-005 remains bypassable through undeclared denominator mode and semantically empty nested contracts

The repaired RC-009 helper activates only when:

- `confirmatory is True`, or
- `analysis_mode == "EXPLORATORY_POST_HOC"`.

Therefore a request can carry `experiment_contract_ref`, `frozen_denominator_contract`, `current_denominator_contract`, `outcomes_inspected=true`, and a material frozen/current change while omitting both mode declarations. The helper returns `None` as "not relevant" and constitutional evaluation can return `PASS`.

That replaces the old self-accusing `denominator_changed_after_outcome` boolean with a different caller-controlled declaration boundary. When denominator metadata and outcome-inspection state are present but analysis authority mode is missing, the validator cannot prove RC-009 is irrelevant; under the frozen contract it must fail closed.

Separately, `denominator_contract_valid()` checks only that the required keys exist. It does not reject `null`, empty strings, empty lists, or invalid types inside those decision-critical fields. A confirmatory request with two identical but semantically empty contracts can therefore receive PASS even though denominator identity is not determinable.

Required repair: when denominator-contract fields/outcome-inspection fields are supplied, require a valid explicit analysis mode or other deterministic authority context; validate nested denominator fields for non-empty/type-correct decision semantics; fail closed when the mode or denominator identity cannot be determined.

### RR-F-003 — MAJOR — Runtime authority protection can be bypassed by contradictory boolean values

The constitutional validator first checks only whether `runtime_context` and `runtime_attempts_authority_promotion` keys are both present or both absent. It then raises E011 only when both values are truthy.

Input:

`{"runtime_context": false, "runtime_attempts_authority_promotion": true}`

has both keys present and therefore passes the structural pair check. The E011 condition evaluates false because `runtime_context` is false, so the request can fall through to `PASS` despite explicitly declaring an authority-promotion attempt.

At minimum this input is contradictory/invalid and must fail closed. It must never PASS. S001 I-008 and RC-010 prohibit runtime output from establishing or promoting research authority.

Required repair: validate the runtime state as an explicit typed state machine/contract. Any declared runtime promotion attempt must fail E011 when it is a runtime action, and contradictory context/attempt declarations must be `INVALID_INPUT`, not PASS.

### RR-F-004 — MAJOR — Evidence-only promotion can accept reused evidence and omitted promotion provenance

S001 I-001 requires genuinely new registered evidence for promotion. The exact candidate checks only whether `new_evidence_refs` is truthy. It does not verify that the refs are actually new relative to `evidence_refs` or otherwise establish new-evidence identity.

Example:

- `authority_current = "Research / R"`
- `authority_requested = "Grade C"`
- `evidence_refs = ["EVID-001"]`
- `new_evidence_refs = ["EVID-001"]`

satisfies the non-empty new-evidence check and the legal transition and can return `PASS` even though no new evidence was introduced.

In addition, promotion rejects E015 only when `evidence_provenance_complete is False`; omission of the provenance field does not fail closed. For an authority-bearing promotion, omission cannot establish complete provenance.

This is separate from the repaired grade-derived Grade B/A/A+ gate-presence issue. The original F-002 is closed as to deriving those required reference fields, but the base evidence-only invariant remains under-enforced.

Required repair: enforce deterministic new-evidence identity (at minimum no overlap/relabeling of old evidence as new, or a stable registry/version identity); require authority-bearing promotion provenance to be affirmatively established rather than treating omission as acceptable.

### RR-F-005 — MAJOR — Malformed schema values can escape the controlled fail-closed status vocabulary by throwing exceptions

The frozen contract requires deterministic invalid-input handling. The exact candidate has unguarded parsing/type assumptions that can raise rather than return `INVALID_INPUT`.

Two concrete examples:

1. non-string authority input can reach `OBSOLETE.match(cur)` before the authority enum membership check and raise `TypeError`;
2. malformed or timezone-incompatible causal timestamps can raise from `datetime.fromisoformat(...)` or comparison instead of returning a controlled E001/E007-style result.

A validator crash is not a controlled fail-closed governance result and breaks the S002 requirement for deterministic machine-checkable contract behavior.

Required repair: validate JSON value types and timestamp parseability before regex/date operations; map malformed schema inputs to a stable controlled `INVALID_INPUT` error path and add negative fixtures for these cases.

## Requested control conclusions

- E001 missing/indeterminate required input: **BLOCKING GAP remains**.
- E003 invalid authority enum: string-enum path passes; malformed-type path can crash.
- E006 independence-required missing: grade-derived presence path passes.
- E010 calibration-required missing: grade-derived presence path passes.
- E015 provenance: classification path repaired; promotion provenance remains fail-open when omitted.
- Invalid knowledge-class/verdict/status enum strings: pass.
- Causal-time leakage: valid timestamp leakage is blocked; malformed timestamps are not safely handled.
- Denominator laundering: explicit confirmatory path is blocked, but mode omission and empty nested metadata remain bypasses.
- Runtime authority creation: normal true/true path is blocked, but contradictory false/true declaration can PASS.
- Silent supersession: pass.
- Non-falsifiable material claim: pass.
- Unsupported completion claim: pass.
- Scope drift: normal non-empty mismatch is blocked; empty declared scope can suppress the check and is covered by RR-F-001.
- Obsolete A0–A5 authority strings: pass.
- Exact-head native evidence binding: pass; evidence explicitly targets `834843ae...`, Python 3.12.2, 39/39, exit 0.

## Scope / contamination check

Accepted S001 baseline `9afbd8208acf667059cf8ac191f58b534cbf68d7` → reviewed candidate `834843ae2bc3222de52e0621455fbe0c763d9519` changes only:

- S002 evidence/contract/fixture artifacts;
- `scripts/mros/validate_s002_fixtures.py`;
- S002-related program state and sprint-ledger records.

The candidate does not add S003, M2, M9, runtime, strategy, broker, risk, execution, or market-claim implementation paths.

The current branch is later than the candidate because it contains the native validation record and Autonomous Review Board bootstrap infrastructure. Those post-candidate additions are not part of the reviewed S002 implementation. Current repository state still declares:

- `active_sprint: S002`;
- `last_completed_sprint: S001`;
- M2 `NOT_STARTED`;
- M9 `NOT_STARTED`;
- runtime authority `NONE`;
- S002 independent re-review required;
- Review Board not calibrated/not authoritative and forbidden from certifying S002 or itself.

Scope-contamination verdict for the reviewed candidate: **PASS**.

## Finding counts

- MINOR: 0
- MAJOR: 5
- CRITICAL: 0
- UNKNOWN: 0

## Final verdict

`S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED`

The repaired candidate materially improves the first reviewed implementation and closes three of the five original MAJOR defects as originally stated. However, two original fail-closed defect classes remain bypassable and three additional blocking defects are exposed by adversarial inputs outside the 39-case corpus.

The 39/39 native PASS is valid for the declared fixtures but is not sufficient to accept S002 at this exact head. A governed caller can still obtain PASS from indeterminate constitutional inputs, bypass denominator laundering checks by omitting analysis mode, bypass runtime-authority protection through contradictory booleans, relabel old evidence as new / omit promotion provenance, and cause malformed inputs to escape the controlled status vocabulary via exceptions.

S002 does not deserve acceptance at `834843ae2bc3222de52e0621455fbe0c763d9519`.

Required program consequence:

- S002 remains ACTIVE / unaccepted;
- S003 remains `NOT_STARTED`;
- M2 remains `NOT_STARTED`;
- M9 remains `NOT_STARTED`;
- runtime authority remains `NONE`;
- the Autonomous Review Board remains bootstrap-only / non-authoritative;
- Part B must not execute;
- repair, native exact-head validation, and a fresh genuinely independent review are required before acceptance.

Hard stop after this review artifact.