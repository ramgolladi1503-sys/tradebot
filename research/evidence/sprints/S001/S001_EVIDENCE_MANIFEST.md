# S001 — Evidence Manifest

Evidence identity: `S001-EVIDENCE-LOCAL-001`
Program: MROS
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Sprint: S001
Branch: `research/mros-program-v1`
Authority Grade: Research / R
Status: `SEALED_FOR_INDEPENDENT_RE_REVIEW_WITH_EXECUTION_CHECK_PENDING`

> This is a sprint-local evidence identity. WP003 owns the canonical MROS evidence registry. Migration to a canonical registry ID must preserve this local identity and provenance.

## Scope

This manifest seals the S001 contract-freeze repair package produced in response to the first independent review. It does **not** accept S001 and does **not** authorize S002.

## Baseline / review provenance

- Original independently reviewed HEAD: `004486fb185e052b3dee8d9f43cc838ea92bfc7e`
- First independent review commit: `88d099bcc7a63470acb1c99a06a606746e14ea27`
- First review artifact: `research/evidence/sprints/S001/S001_INDEPENDENT_REVIEW.md`
- First review verdict: `S001_INDEPENDENT_REVIEW_REPAIR_REQUIRED`
- Finding counts: 1 MINOR / 4 MAJOR / 0 CRITICAL / 0 UNKNOWN

## Repair evidence

| Evidence | Path / commit | Purpose | Status |
|---|---|---|---|
| Constitution repair | `research/constitution/RESEARCH_CONSTITUTION.md`; commit `e5f1a71fcdff8f217201b515119302fee58a0163` | F-001: close post-hoc denominator / observation / trade / metric-reframing loophole | READY_FOR_REVIEW |
| Frozen machine-checkable contract | `research/evidence/sprints/S001/S001_INTERFACE_CONTRACT.md`; commit `850e2dd91a83463e4e4cba03107cd283fd4f8f25` | F-002: freeze interface, controlled vocabularies, statuses, error codes, invariants, fail-closed semantics | READY_FOR_REVIEW |
| Acceptance trace | `research/evidence/sprints/S001/S001_ACCEPTANCE_TRACE.md`; commit `ba7a0b8254521c6a633de015b39c96dfccf058b9` | F-003: complete S001 criterion→verification mapping | READY_FOR_REVIEW |
| Deterministic validator | `scripts/mros/validate_s001_contract.py`; commit `32a5f987509153a7c9edb88bdcda63add2fd6b55` | F-004: provide reproducible offline/non-runtime verification command | READY_FOR_EXECUTION |
| Sprint ledger state | `research/program/SPRINT_LEDGER.jsonl`; commit `cf2c76a1743fd3fed6a7455ddf0d3e7ca703022b` | Preserve `IN_PROGRESS` while recording repair-ready state | PASS |
| Program state | `research/program/MROS_PROGRAM_STATE.yaml`; commit `17235f1677d0332e6b11b797fdfd55703f5d426e` | Preserve S001 `REVIEW_REQUIRED`; keep M2–M9 unstarted | PASS |
| Changed-file manifest | `research/evidence/sprints/S001/S001_CHANGED_FILES.md`; commit `0e30f9439b3fd8c21cce80bd6d06b7e7e98ea56f` | Bound repair scope and support out-of-scope review | PASS |

## Actual repository checks performed by the primary session

The primary session used the connected repository API to perform the following checks against `research/mros-program-v1`:

1. Fetched and inspected the committed first independent review.
2. Fetched and inspected the current Research Constitution.
3. Fetched and inspected the frozen S001 interface contract.
4. Fetched and inspected the S001 acceptance trace.
5. Fetched and inspected `MROS_PROGRAM_STATE.yaml`.
6. Compared the original reviewed HEAD `004486fb185e052b3dee8d9f43cc838ea92bfc7e` to the repaired program branch.
7. Confirmed the compare result was ahead-only and the changed paths through the repair/state parent were governance/program/evidence/validator paths rather than TradeBot runtime/broker/execution paths.

These repository inspections are evidence of file presence/scope. They are **not** represented as execution of the Python validator.

## Required executable validation

The frozen targeted command is:

```bash
python scripts/mros/validate_s001_contract.py
```

Expected execution properties:

- standard-library Python only;
- offline;
- no broker/network/market-data access;
- no runtime mutation;
- non-zero exit on missing RC rules, denominator safeguards, controlled vocabularies/error codes, acceptance trace items, or incorrect program-state boundary;
- deterministic PASS/FAIL checklist.

### Current execution status

`PENDING_ON_REPAIRED_REVIEW_HEAD`

The current primary ChatGPT connector session can read/write the repository but does not provide repository code execution. Therefore it has **not** fabricated a command output.

The independent re-review session must execute the command on the exact repaired HEAD and commit the resulting output as:

`research/evidence/sprints/S001/S001_VALIDATION_OUTPUT.txt`

If the command fails, the reviewer must return repair required rather than editing the implementation to obtain PASS.

## Required independent re-review

A reviewer/session distinct from the primary S001 implementation agent must:

1. pin the exact repaired HEAD;
2. run `python scripts/mros/validate_s001_contract.py`;
3. commit the exact stdout/stderr/exit status to `S001_VALIDATION_OUTPUT.txt`;
4. re-attack RC-009 using post-hoc trade/observation/metric-denominator cases;
5. review the frozen interface/status/error contract;
6. review all S001 acceptance-trace rows;
7. verify changed paths do not create M2/runtime behavior;
8. classify all findings;
9. issue exactly one repaired-HEAD re-review verdict.

S001 cannot be accepted while this independent execution/re-review is pending.

## Assumptions

- The repository-adopted MROS Engineering Manual v1.0 remains authoritative.
- `DEC-2026-0001` and `DEC-2026-0002` remain active.
- No concurrent writer changes the branch between evidence sealing and independent reviewer HEAD pinning without that change being included in the review.

## Unknowns

- Whether the deterministic validator passes on the final repaired HEAD remains UNKNOWN until executed in a repository-capable session.
- Whether the repaired RC-009/interface/trace fully close all first-review MAJOR findings remains UNKNOWN until independent re-review.
- WP001 historical-example and cross-reviewer consistency criteria belong to later WP001 sprints and remain unproven.

## Destroyers / failure conditions

This repair package must not be accepted if any of the following occurs:

- validator exits non-zero;
- RC-009 still permits outcome-aware post-hoc denominator/exclusion reframing as confirmatory evidence;
- interface semantics permit unknown/invalid input to become PASS;
- obsolete A0–A5 grades regain active authority;
- independent attack can be self-satisfied;
- causal-time violations can support evidence;
- runtime output can establish research authority;
- any S001 acceptance obligation remains unmapped or unverifiable;
- MAJOR or CRITICAL independent finding remains;
- repaired HEAD contains unreviewed runtime/strategy/broker/risk behavior changes.

## Current sprint decision

`IN_PROGRESS / REVIEW_REQUIRED`

No S001 acceptance decision has been issued.

## Next action

Independent re-review of the exact final repaired branch HEAD. If and only if that review passes with no unresolved MAJOR/CRITICAL findings and executable validation passes, the primary MROS agent may record S001 acceptance and advance to S002 automatically.
