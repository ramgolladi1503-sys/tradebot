# TEP v1 — M1 Implementation Contract

Status: IMPLEMENTATION CANDIDATE

Frozen Phase-0 authority: `9cdc21b2270d924daaf860443e57f39df4b0cc93`.

## Authorized scope
M1 only: canonical in-memory contracts for MissionDefinition, MissionInstance, TaskInstance, WorkerExecution, AuthorityDecision, EventRecord and EvidenceRecord; mission validation; deterministic dependency evaluation; state-transition validation; UNKNOWN/MISSING/ZERO/PASS preservation.

## Explicitly prohibited
No durable state store, supervisor, leases, timers, worker execution, Git/GitHub/CI mutation service, broker access, order action, paper/live execution, protected holdout access, structural-edge certification, cleanup, or M2+ implementation.

## Evidence contract
M1 may be classified IMPLEMENTATION_VALID only after exact-head tests prove schema/version handling, illegal-transition rejection, deterministic graph validation, cycle/unknown dependency rejection and truth-value distinction. Repository CI status must be reported separately; absence of CI is not PASS.

## Safety defaults
`broker_write_authority=false`; `order_authority=false`; `paper_authorized=false`; `live_authorized=false`.
