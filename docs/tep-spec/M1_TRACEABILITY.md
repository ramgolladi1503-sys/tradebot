# TEP v1 — M1 Traceability

Frozen Phase-0 SHA: `9cdc21b2270d924daaf860443e57f39df4b0cc93`.

| Requirement | Implementation | Tests |
|---|---|---|
| REQ-MISSION-001 | `tep.kernel.MissionDefinition`, `validate_mission` | schema, identity, graph tests |
| REQ-TASK-001 | `tep.kernel.TaskDefinition` | dependency validation tests |
| REQ-STATE-002 | `TASK_TRANSITIONS`, `MISSION_TRANSITIONS`, `require_transition` | illegal/terminal transition tests |
| REQ-SCHED-001 | `compute_runnable` | deterministic runnable-order test |
| REQ-GOV-002 | `TruthValue` | distinct UNKNOWN/MISSING/ZERO/PASS test |
| REQ-EVID-001 | `EvidenceRecord` schema only | required-field record test |
| REQ-AUTH-001 | `AuthorityDecision` schema only | DENY record preservation test |

Durability, authority evaluation, external mutation, event persistence and execution are deliberately deferred to later milestones. These rows do not claim those requirements complete beyond the M1 schema/kernel slice.
