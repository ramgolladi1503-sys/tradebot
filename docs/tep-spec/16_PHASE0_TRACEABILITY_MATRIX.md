# TEP v1 — Phase-0 Traceability Matrix

Status: DRAFT
Version: 1.0.0-draft
Normative: Yes

This document repairs RC2-F001. It is the canonical architectural traceability index. M1+ extends the final three columns with implementation/test/evidence IDs.

| Requirement | ADR / law / rule basis | Interface / state / capability contract | Phase-0 terminal? |
|---|---|---|---|
| REQ-GOV-001 | SPEC-000, IR-001, IR-035 | specification freeze contract | yes — implementation deferred |
| REQ-GOV-002 | LAW-010, IR-031/032 | controlled verdict semantics | yes |
| REQ-GOV-003 | ADR-004, LAW-004/006 | ownership/dependency contracts | yes |
| REQ-MISSION-001 | ADR-003, IR-026 | IF-MISSION-001 | yes |
| REQ-MISSION-002 | ADR-003 | IF-MISSION-001 + mission states | yes |
| REQ-TASK-001 | ADR-003, IR-008/010 | task states + IF-TASK-001 | yes |
| REQ-STATE-001 | ADR-007, IR-006/023 | task/mission state tables + IF-EVENT-001 | yes |
| REQ-STATE-002 | ADR-007, IR-031 | prohibited transitions | yes |
| REQ-STATE-003 | ADR-007 | crash boundary 2 + IF-TASK-001 | yes |
| REQ-SCHED-001 | ADR-001/004 | IF-SCHED-001 | yes |
| REQ-SCHED-002 | ADR-011/013, IR-023 | IF-SCHED-001 | yes |
| REQ-SCHED-003 | ADR-018, IR-011 | IF-CI-001 | yes |
| REQ-EVENT-001 | ADR-007 | IF-EVENT-001 | yes |
| REQ-AUTH-001 | ADR-006, LAW-001, IR-007 | IF-AUTH-001 + capability catalogue | yes |
| REQ-AUTH-002 | ADR-006, LAW-014 | capability catalogue | yes |
| REQ-AUTH-003 | ADR-006, LAW-012, IR-007 | IF-AUTH-001 + mutation capabilities | yes |
| REQ-CAP-001 | ADR-006 | capability catalogue | yes |
| REQ-WORKER-001 | ADR-005, IR-008 | IF-WORKER-001 | yes |
| REQ-WORKER-002 | ADR-005, LAW-022, IR-009/030 | IF-VALIDATE-001 | yes |
| REQ-WORKER-003 | ADR-005, IR-008/010 | IF-WORKER-001 | yes |
| REQ-DRIVER-001 | ADR-004, LAW-006 | boundary dependency rules | yes |
| REQ-GIT-001 | ADR-009, IR-001/007 | IF-GIT-001; PUSH_BRANCH/CREATE_BRANCH | yes |
| REQ-GH-001 | ADR-004/009 | IF-GH-001; PR metadata capabilities | yes |
| REQ-CI-001 | ADR-018/019, IR-012 | IF-CI-001 | yes |
| REQ-CI-002 | ADR-019, LAW-020, IR-013 | IF-CI-001 | yes |
| REQ-MERGE-001 | ADR-011, IR-007 | IF-MERGE-001; MERGE_PR | yes |
| REQ-MERGE-002 | ADR-011, IR-034 | IF-MERGE-001 | yes |
| REQ-MERGE-003 | ADR-012, IR-005 | CREATE_PR capability | yes |
| REQ-CLEAN-001 | LAW-018, IR-022 | IF-CLEAN-001; deletion capabilities | yes |
| REQ-EVID-001 | ADR-008/010/016, IR-030/032 | IF-EVID-001; SEAL_EVIDENCE | yes |
| REQ-EVID-002 | ADR-016 | IF-EVID-001 | yes |
| REQ-KNOW-001 | ADR-008, LAW-007 | IF-KNOW-001 | yes |
| REQ-OBS-001 | ADR-013/014, IR-023/024/025 | scheduler/state status contracts | yes |
| REQ-LIVE-001 | ADR-021, IR-017 | IF-LIVE-001; START_READ_ONLY_OBSERVER | yes |
| REQ-LIVE-002 | ADR-022, IR-016 | IF-LIVE-001 | yes |
| REQ-LIVE-003 | ADR-023, IR-015 | IF-LIVE-001 | yes |
| REQ-LIVE-004 | ADR-024 | IF-LIVE-001/observer stop | yes |
| REQ-RES-001 | ADR-020, IR-018 | IF-RES-001; ACCESS_PROTECTED_HOLDOUT | yes |
| REQ-RES-002 | ADR-020, IR-019 | research governance/failure registry | yes |
| REQ-RES-003 | ADR-020, IR-020 | IF-RES-001 | yes |
| REQ-RES-004 | ADR-020, IR-021/030 | IF-RES-001; CERTIFY_STRUCTURAL_EDGE | yes |
| REQ-MIG-001 | IR-002/033 | migration dispositions | yes |
| REQ-HUMAN-001 | IR-031 | human authority taxonomy/escalation contract | yes |
| REQ-ARCH-001 | ADR-002/004/025, IR-028/029 | mechanical architecture boundary checks | yes |
| REQ-CONFIG-001 | IR-026 | configuration registry boundary | yes |
| REQ-SECRET-001 | ADR-029, IR-027 | secret/driver boundary | yes |

## Normative identifier coverage

All `REQ-*` identifiers in `10_REQUIREMENT_CATALOGUE.md` MUST appear exactly once as primary rows above. ADR identifiers are covered through `14_ADR_COMPLIANCE_AND_OPEN_DECISIONS.md`. Interface IDs are covered by `13_BOUNDARY_INTERFACE_CONTRACTS.md`.

All `IR-001` through `IR-035` are normative. An IR need not create a separate REQ when it refines an existing requirement; it MUST appear in at least one traceability row or be explicitly classified below.

### Cross-cutting IR classifications

- IR-003 dirty checkout restriction → REQ-GIT-001 / REQ-CLEAN-001.
- IR-004 bounded changes → REQ-WORKER-003 / REQ-ARCH-001.
- IR-006 no force push by default → REQ-GIT-001 / REQ-AUTH-002.
- IR-014 protected paths → REQ-CLEAN-001 / REQ-AUTH-001.
- IR-025 cancellation governance → REQ-OBS-001 / REQ-STATE-001.
- IR-028 dependency updates → REQ-ARCH-001.
- IR-029 layered tests → REQ-ARCH-001 plus each M1+ requirement evidence chain.
- IR-033 rollback before rollout → REQ-MIG-001.
- IR-035 phase gates → REQ-GOV-001.

No LAW or IR may be silently dropped at implementation. M1 MUST introduce a mechanical traceability validator that fails on missing/duplicate REQ IDs, orphaned normative LAW/IR IDs, unknown ADR/IF references, or a required implementation/test/evidence link missing for the current milestone.

## Deferred implementation chain

Every Phase-0 row terminates at architecture because production implementation does not yet exist. This is explicit, not a PASS for implementation. At M1+, the chain becomes:

`REQ → ADR/LAW/IR → IF/state/capability → implementation symbol/module → test ID → immutable evidence ref`.

A Phase-0 architectural PASS cannot be reused as an implementation PASS.