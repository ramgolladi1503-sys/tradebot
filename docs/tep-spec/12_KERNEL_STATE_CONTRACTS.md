# TEP v1 — Kernel State Contracts

Status: DRAFT
Version: 1.0.0-draft
Normative: Yes

Repairs Phase-0 finding F-005. Detailed storage representation is deferred; lifecycle semantics are not.

## Task states

| State | Entry condition | Legal exits | Recovery/evidence |
|---|---|---|---|
| PENDING | task instantiated; dependencies unresolved | RUNNABLE, INVALIDATED | durable definition/fingerprint |
| RUNNABLE | dependencies satisfied; no wait/block; capability potentially available | LEASED, INVALIDATED, BLOCKED_HUMAN, BLOCKED_LIVE_EVIDENCE | scheduler decision event |
| LEASED | exclusive execution lease acquired | EXECUTING, RUNNABLE, INVALIDATED | lease owner/expiry |
| EXECUTING | bounded handler/worker started | VALIDATING, WAITING, REPAIRABLE, FAILED_TERMINAL | WorkerExecution/handler execution ref |
| VALIDATING | execution result exists and requires contract validation | SUCCEEDED, WAITING, REPAIRABLE, BLOCKED_HUMAN, BLOCKED_LIVE_EVIDENCE, FAILED_TERMINAL, INVALIDATED | validator result; completed execution reused after restart |
| WAITING | known external/time/event prerequisite not yet satisfied | RUNNABLE, VALIDATING, INVALIDATED, FAILED_TERMINAL | typed wait condition + wake criteria |
| REPAIRABLE | evidence supports bounded automated repair | RUNNABLE, WAITING, BLOCKED_HUMAN, FAILED_TERMINAL, INVALIDATED | blocker classification + repair budget |
| BLOCKED_HUMAN | frozen policy requires irreducible human decision | RUNNABLE, INVALIDATED, FAILED_TERMINAL | canonical escalation payload + decision record |
| BLOCKED_LIVE_EVIDENCE | exact contract requires future/fresh live evidence | RUNNABLE, WAITING, INVALIDATED | required session/producer/validator contract |
| SUCCEEDED | validator proves task completion contract | INVALIDATED only if dependency/authority contract explicitly permits post-success invalidation before mission commit | result/evidence refs |
| INVALIDATED | fingerprint/dependency/authority/source drift makes prior readiness/result unusable | PENDING or RUNNABLE only through explicit re-materialization policy | invalidation cause + old/new authority |
| FAILED_TERMINAL | non-repairable failure or exhausted governed budget | none except explicit mission revision/retry operation creating new attempt/task generation | failure evidence |

### Prohibited task transitions

Examples explicitly prohibited:

- PENDING → SUCCEEDED without execution/validation evidence;
- WAITING → SUCCEEDED solely because time elapsed;
- REPAIRABLE → SUCCEEDED without repaired result validation;
- BLOCKED_LIVE_EVIDENCE → SUCCEEDED from historical/mock evidence when fresh live is required;
- FAILED_TERMINAL → RUNNABLE by silent counter reset;
- INVALIDATED → SUCCEEDED using the invalidated fingerprint.

## Mission states

| State | Entry condition | Legal exits | Evidence |
|---|---|---|---|
| CREATED | MissionInstance persisted | VALIDATING, CANCELLED | definition/hash |
| VALIDATING | mission schema/dependency/capability validation active | READY, FAILED, CANCELLED | validation report |
| READY | definition valid and admission prerequisites met | RUNNING, CANCELLED | admission decision |
| RUNNING | scheduler may progress tasks | WAITING, BLOCKED, COMPLETED, FAILED, CANCELLED | task/event ledger |
| WAITING | no runnable task; at least one non-terminal wait exists | RUNNING, BLOCKED, FAILED, CANCELLED | derived wait set |
| BLOCKED | no runnable path and at least one policy blocker requires external/human/live resolution | RUNNING, FAILED, CANCELLED | blocker set |
| COMPLETED | frozen mission completion expression true from durable validated state | none | completion evaluation + evidence bundle |
| FAILED | mission terminal failure expression true | none except new mission/version | failure bundle |
| CANCELLED | governed cancellation committed | none except new mission/version | cancellation record |

Mission WAITING/BLOCKED are derived states; an independent runnable task forces RUNNING rather than global freeze.

## Attempt semantics

An attempt is immutable after terminal execution result commit. Retry creates a new attempt number under the same TaskInstance or a new task generation according to task policy. Retry budgets cannot be reset silently.

## Crash boundaries

1. Crash before execution commit: lease recovery may rerun if no valid mutation/execution marker exists.
2. Crash after worker completion but before validation: reuse committed WorkerExecution; resume VALIDATING without rerunning worker.
3. Crash after external mutation but before state commit: handler MUST reconcile idempotency key/target before retry and either adopt the completed mutation or fail closed.
4. Corrupt/missing required evidence: do not infer success; route evidence failure/UNKNOWN.

## Invalidation

Invalidation records dependency type, old fingerprint, new authority, affected tasks and whether prior evidence remains historically valid. Invalidation does not delete historical evidence.

## Concurrency

A TaskInstance has at most one active execution lease. Serialization keys prevent simultaneous conflicting mutations. Duplicate event delivery must not create duplicate attempts or side effects.