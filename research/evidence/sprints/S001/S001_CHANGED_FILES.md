# S001 — Repair Changed-File Manifest

Program: MROS
Milestone: M1 — Research Governance
Work Package: WP001 — Research Constitution
Sprint: S001
Branch: `research/mros-program-v1`
Original independently reviewed HEAD: `004486fb185e052b3dee8d9f43cc838ea92bfc7e`
Original independent review commit: `88d099bcc7a63470acb1c99a06a606746e14ea27`
Repair candidate parent HEAD before this manifest: `17235f1677d0332e6b11b797fdfd55703f5d426e`
Status: SEALED_SCOPE_FOR_INDEPENDENT_RE_REVIEW

## Git comparison

Repository comparison was performed from the original reviewed HEAD `004486fb185e052b3dee8d9f43cc838ea92bfc7e` to `research/mros-program-v1` after the primary repair/state commits.

Result at sealing time:

- status: `ahead`
- commits ahead: 7
- commits behind: 0
- total commits in comparison: 7

## Changed paths through repair candidate parent HEAD

| Path | Change | Purpose |
|---|---|---|
| `research/constitution/RESEARCH_CONSTITUTION.md` | modified | Close F-001 / RC-009 post-hoc observation/trade/metric-denominator loophole. |
| `research/evidence/sprints/S001/S001_INDEPENDENT_REVIEW.md` | added | Preserve genuinely independent first review and repair verdict. |
| `research/evidence/sprints/S001/S001_INTERFACE_CONTRACT.md` | added | Close F-002 by freezing S001 component/API/schema responsibilities, controlled vocabularies, statuses, error codes and fail-closed semantics without implementing S002. |
| `research/evidence/sprints/S001/S001_ACCEPTANCE_TRACE.md` | added | Close F-003 by mapping S001 design/QA/evidence obligations to verifiable artifacts and commands. |
| `scripts/mros/validate_s001_contract.py` | added | Provide deterministic offline/non-runtime validation command for the frozen S001 contract. |
| `research/program/SPRINT_LEDGER.jsonl` | modified | Record repair-ready state while keeping S001 decision `IN_PROGRESS`. |
| `research/program/MROS_PROGRAM_STATE.yaml` | modified | Keep S001 at `REVIEW_REQUIRED`, mark repair candidate ready for independent re-review, and keep M2–M9 unstarted. |

This manifest itself is an additional S001 evidence path created after the comparison and must be included by the independent reviewer when fixing the exact re-review HEAD.

## Explicitly unchanged behavior domains

The repair does not intentionally modify:

- TradeBot runtime;
- broker connectivity;
- order placement/modification/cancellation;
- strategy emissions;
- production risk behavior;
- MEG;
- PR806 research implementation;
- market-data ingestion;
- live execution;
- M2+ implementation.

The independent reviewer must verify this scope statement against the repaired HEAD rather than trusting this prose.

## Repair commits already recorded

- `e5f1a71fcdff8f217201b515119302fee58a0163` — RC-009 repair.
- `850e2dd91a83463e4e4cba03107cd283fd4f8f25` — interface/status/error contract.
- `ba7a0b8254521c6a633de015b39c96dfccf058b9` — acceptance trace.
- `32a5f987509153a7c9edb88bdcda63add2fd6b55` — deterministic validator.
- `cf2c76a1743fd3fed6a7455ddf0d3e7ca703022b` — sprint-ledger repair state.
- `17235f1677d0332e6b11b797fdfd55703f5d426e` — program-state re-review gate.

## Review boundary

The next independent reviewer must review the final repaired branch HEAD including this manifest and the S001 evidence manifest. S001 remains blocked until that reviewer returns a passing verdict with no unresolved MAJOR/CRITICAL findings.
