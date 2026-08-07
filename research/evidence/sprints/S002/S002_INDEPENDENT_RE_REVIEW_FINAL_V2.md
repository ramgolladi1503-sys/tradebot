# MROS S002 Bootstrap-Independent Re-Review — Final V2

Program: MROS  
Milestone: M1 — Research Governance  
Work Package: WP001 — Research Constitution  
Sprint: S002  
Branch reviewed: `research/mros-program-v1`  
Exact implementation candidate reviewed: `b3f53caf73763cf57186cfba41d49653ddfc28a6`  
Authority: `Research / R`  
Runtime authority: `NONE`  
Final verdict: `S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED`

---

## 1. Reviewer Independence / No-Repair Statement

This review is a fresh bootstrap-independent re-review of the immutable S002 candidate `b3f53caf73763cf57186cfba41d49653ddfc28a6`.

The review did not:

- implement or repair S002;
- modify `scripts/mros/validate_s002_fixtures.py`;
- modify either S002 fixture corpus;
- weaken or reinterpret the frozen S001 contract;
- modify Review Board or Audit Board implementation;
- start S003;
- accept S002;
- calibrate or authorize Review/Audit Boards;
- begin M2 or M9;
- touch TradeBot runtime, strategy, ranking, risk, broker, execution, or live behavior.

Only this review artifact is added after the reviewed candidate. No candidate repair is performed by this reviewer.

---

## 2. Exact Candidate Binding

Immediately before this review artifact was committed, repository comparison showed:

- base: `b3f53caf73763cf57186cfba41d49653ddfc28a6`;
- head: `research/mros-program-v1`;
- status: `identical`;
- ahead: `0`;
- behind: `0`.

The candidate commit is:

`b3f53caf73763cf57186cfba41d49653ddfc28a6`

Commit message:

`mros(S002): preserve no-new-evidence precedence [skip ci]`

Its direct code change makes empty `new_evidence_refs` invalid as a canonical evidence collection so the promotion function can preserve the explicit C006 E005/RC-002 precedence path.

---

## 3. Native Exact-Head Evidence

Authoritative native terminal evidence supplied for this review binds to the exact candidate:

- detached HEAD: `b3f53caf73763cf57186cfba41d49653ddfc28a6`;
- Python: `3.12.2`;
- command: `python3 scripts/mros/validate_s002_fixtures.py`;
- cases: `S002-C001` through `S002-C066`;
- summary: `checks=66 pass=66 fail=0`;
- terminal verdict: `S002_TARGETED_VALIDATION_PASS`;
- exit code: `0`.

The transcript explicitly shows C006 returning:

- status `FAIL`;
- error `MROS-S001-E005-NO_NEW_EVIDENCE_FOR_PROMOTION`;
- rule `RC-002`;
- `can_promote=false`.

Therefore the prior mandatory native-evidence UNKNOWN is closed for this review. No native-evidence UNKNOWN is carried forward.

---

## 4. Authoritative Contract Sources Re-Read

This review re-read the current candidate versions of at least:

- `research/evidence/sprints/S001/S001_INTERFACE_CONTRACT.md`;
- `research/constitution/RESEARCH_CONSTITUTION.md`;
- `research/governance/AUTHORITY_GRADES.md`;
- `research/evidence/sprints/S002/S002_CONTRACT_IMPLEMENTATION.md`;
- `research/evidence/sprints/S002/S002_FIXTURES.json`;
- `research/evidence/sprints/S002/S002_FIXTURES_V5_ADDENDUM.json`;
- `scripts/mros/validate_s002_fixtures.py`;
- `research/evidence/sprints/S002/S002_INDEPENDENT_RE_REVIEW_FINAL.md`;
- `research/evidence/sprints/S002/S002_FINAL_BOOTSTRAP_REPAIR_EVIDENCE.md`;
- `research/program/MROS_PROGRAM_STATE.yaml`.

The prior failed review was used only as a historical attack list. Its verdict was not treated as authoritative for this candidate.

---

## 5. Mandatory Re-Attack Matrix

### 5.1 Partial constitutional requests — CLOSED

The candidate now defines dependent/primary relationships before any constitutional PASS can occur:

- `destroyers` requires `material_claim`;
- `completion_evidence_refs` requires `completion_claim`;
- `supersession_decision_ref` requires `supersedes`.

C054-C056 independently exercise these dependent-only requests and return controlled `INVALID_INPUT` / E001.

Existing fail-closed pair checks remain for:

- decision timestamp / input availability timestamps;
- runtime context / runtime authority-promotion attempt;
- declared scope / attempted scope.

Denominator-trigger partial requests route into `validate_denominator_semantics()` and cannot silently fall through to PASS without a coherent confirmatory or exploratory-post-hoc state.

Result: **PASS — prior FIN-F-001 closed.**

### 5.2 Empty enum-validation requests — CLOSED

`validate_enums()` now requires at least one controlled enum target from:

- `knowledge_class`;
- `verdict`;
- `status`.

C057 proves `{}` returns `INVALID_INPUT` / E001. C066 proves a valid controlled enum request still returns PASS.

Result: **PASS — prior FIN-F-002 closed.**

### 5.3 Contradictory RC-009 post-hoc states — CLOSED

`analysis_mode=EXPLORATORY_POST_HOC` now semantically requires `outcomes_inspected=true`.

A contradictory post-hoc request with `outcomes_inspected=false` returns controlled `INVALID_INPUT` rather than bypassing preservation/multiplicity/reduced-authority protections.

C058 exercises this exact class and passes natively.

The existing changed post-hoc denominator path still requires:

- `new_analysis_identity`;
- `post_hoc_rationale`;
- `original_result_preserved=true`;
- `multiplicity_accounted=true`;
- `reduced_authority=true`.

Result: **PASS — prior FIN-F-003 closed.**

### 5.4 Genuine-new-evidence / provenance enforcement — NOT CLOSED

The candidate materially improves evidence identity handling:

- `evidence_refs` is mandatory for an authority-bearing PASS;
- `evidence_provenance_complete=true` is mandatory;
- old/new evidence collections must use canonical `EVID-*` syntax;
- duplicate refs are invalid;
- canonical old/new overlap fails E005 / RC-002;
- C059, C063, C064 and C065 cover key lineage/canonicalization cases.

However, the frozen S001 invariant is stronger than syntactic non-overlap.

`S001_INTERFACE_CONTRACT.md` I-001 requires:

> An authority increase must identify genuinely new registered evidence satisfying the predeclared gate.

`RESEARCH_CONSTITUTION.md` RC-002 likewise requires new registered evidence to satisfy predeclared gates.

`AUTHORITY_GRADES.md` requires promotion to carry explicit applicable gate evidence.

The exact candidate `promotion()` function does not bind the canonical `new_evidence_refs` set to the grade-gate references used to justify the requested promotion. The independent attack/calibration/scientific/economic/live/monitoring refs are checked for presence, but they are not required to be members of the genuinely new evidence set, and no equivalent deterministic linkage is checked.

Two adversarial Grade C → Grade B requests therefore remain fail-open:

#### Attack A — impossible empty prior lineage on an already promoted grade

```json
{
  "authority_current": "Grade C",
  "authority_requested": "Grade B",
  "evidence_refs": [],
  "new_evidence_refs": ["EVID-UNRELATED-NEW"],
  "evidence_provenance_complete": true,
  "independent_attack_ref": "ATTACK-OLD",
  "calibration_ref": "CAL-OLD"
}
```

Deterministic candidate behavior: `PASS`, `can_promote=true`.

This means a caller can assert an empty complete prior lineage even though Grade C itself necessarily rests on prior reproducible evidence. The validator accepts the self-declared empty set without proving lineage consistency with the current grade.

#### Attack B — unrelated syntactically-new evidence with non-new gate refs

```json
{
  "authority_current": "Grade C",
  "authority_requested": "Grade B",
  "evidence_refs": ["EVID-PRIOR-OBSERVATION"],
  "new_evidence_refs": ["EVID-UNRELATED-ADMIN"],
  "evidence_provenance_complete": true,
  "independent_attack_ref": "ATTACK-PRIOR",
  "calibration_ref": "CAL-PRIOR"
}
```

Deterministic candidate behavior: `PASS`, `can_promote=true`.

Nothing in the validator proves that `EVID-UNRELATED-ADMIN` is the independent replication/calibration evidence required for Grade B, or that the attack/calibration refs are themselves genuinely new for this promotion.

This is the same substantive class identified previously as FIN-F-004. Canonical `EVID-*` identity closes relabel/overlap ambiguity only within the supplied evidence-reference sets; it does not close the required new-evidence-to-gate binding.

Result: **MAJOR — FIN-F-004 remains open.**

Required repair boundary for the implementer, not this reviewer: make an authority-bearing PASS deterministically prove that the genuinely new evidence satisfies the requested promotion gate. The mechanism may use explicit gate-to-evidence binding or another frozen-contract-compatible representation, but the reviewer does not prescribe or implement the repair.

### 5.5 Malformed promotion-schema types — CLOSED for the attacked fail-open class

The candidate now type-checks supplied optional promotion booleans:

- `requires_independent_attack`;
- `requires_calibration`;
- `evidence_provenance_complete`.

Malformed scalar/non-list `new_evidence_refs` is classified as controlled schema `INVALID_INPUT`, while an actual empty list preserves the E005/RC-002 semantic path.

C060-C062 and C064 natively pass these negative controls.

Required grade-gate refs that are absent/malformed cannot produce promotion PASS because their required non-empty-string checks fail closed.

Result: **PASS — prior FIN-F-005 fail-open class closed.**

### 5.6 C006 regression — CLOSED

Exact candidate C006 input contains:

- `authority_current=Research / R`;
- `authority_requested=Grade C`;
- prior evidence present;
- `new_evidence_refs=[]`.

The candidate checks new evidence before later provenance logic and explicitly special-cases the empty list to:

- `FAIL`;
- `MROS-S001-E005-NO_NEW_EVIDENCE_FOR_PROMOTION`;
- `RC-002`;
- `can_promote=false`.

The native 66-case transcript proves C006 matches that expectation at exact HEAD.

Result: **PASS — C006 regression closed.**

---

## 6. Broader Regression / Boundary Review

The 66-case native run also preserves expected fail-closed behavior for the previously covered classes, including:

- missing mandatory fields;
- invalid/obsolete authority grades;
- stage skipping;
- missing independent attack;
- missing calibration;
- missing evidence provenance;
- invalid knowledge/verdict/status enums;
- causal-time violations;
- confirmatory denominator laundering;
- legitimate preregistered unchanged denominator contracts;
- legitimate separated exploratory post-hoc analysis;
- runtime authority violation;
- non-falsifiable material claims;
- unsupported completion claims;
- unrecorded supersession;
- scope drift;
- malformed/naive timestamps;
- malformed authority types;
- `Rejected`/`Unknown` promotion bypasses;
- Grade B/A/A+ minimum required gate references.

No new runtime, strategy, broker, risk, ranking, execution, or M9 contamination is introduced by the candidate.

---

## 7. Finding Counts

- MINOR: **0**
- MAJOR: **1**
- CRITICAL: **0**
- UNKNOWN: **0**

Finding:

- `V2-F-001 / FIN-F-004` — MAJOR — genuinely new evidence is still not deterministically bound to the requested promotion gate, and higher-grade prior lineage can be asserted empty while still receiving PASS.

No CRITICAL is assigned because the S002 validator itself does not mutate program authority or runtime state. The defect remains a mandatory acceptance blocker because it can produce an incorrect `can_promote=true` governance classification.

---

## 8. Final Verdict

`S002_INDEPENDENT_RE_REVIEW_REPAIR_REQUIRED`

The native exact-head evidence is accepted for this review and mandatory UNKNOWN count is zero, but S002 does not qualify for either passing verdict because one MAJOR RC-002 / I-001 defect remains.

Therefore:

- S002 must **not** be accepted;
- S003 must remain `NOT_STARTED`;
- Review Board and Audit Board must remain unauthorized/un-calibrated for autonomous certification;
- runtime authority remains `NONE`;
- M9 remains `NOT_STARTED`.

This reviewer stops here and performs no repair.
