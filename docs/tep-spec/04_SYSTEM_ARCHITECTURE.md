# TEP v1 — System Architecture

Status: DRAFT
Version: 1.0.0-draft
Normative: Yes

## 1. Architectural objective

TEP is a governed modular control plane for durable engineering, research, repository and read-only market-observation missions. It removes the human from routine routing while preserving explicit ownership, authority, validation and evidence boundaries.

## 2. Layer model

### L0 — Enterprise Governance
Owns constitutional specifications, global safety invariants, product policy and architecture governance.

### L1 — Platform Contracts
Owns canonical schemas and registries for missions, capabilities, authorities, configuration, events, evidence and knowledge.

### L2 — TBOS Runtime Kernel
Owns durable mission/task lifecycle, dependency scheduling, dispatch, event processing, wait states, retry budgets, crash recovery, supervisor heartbeat and singleton behavior.

### L3 — Services
Own domain semantics: Git, GitHub, CI, repair, review, merge, cleanup, evidence, research governance and live-observation preparation.

### L4 — Drivers and Workers
Drivers adapt external systems. Workers execute bounded reasoning/coding tasks. Neither owns global policy.

### L5 — Applications
TradeBot, REC-MD, CAS and repository-consolidation applications define domain missions through platform contracts.

## 3. Dependency rule

Dependencies flow from higher logical consumers toward lower owned interfaces. Cross-layer shortcuts are prohibited when they bypass an owning service.

Application → Mission Engine → TBOS → Service → Worker/Driver.

Results return through validator/evidence/state interfaces, not through informal prompt chaining.

## 4. Core components

### 4.1 Mission Registry
Stores versioned mission definitions and schema versions.

### 4.2 Mission Engine
Validates mission definitions, resolves capability references, creates durable mission/task instances and evaluates mission completion contracts.

### 4.3 Scheduler
Computes runnable tasks from durable state, dependencies, waits, authority prerequisites and concurrency rules. Scheduler performs no domain mutation.

### 4.4 Event Router
Consumes durable events and wakes relevant scheduler/service handlers. Events are idempotently consumed.

### 4.5 State Store
Provides transactional durable state for missions/tasks/leases/attempts/waits. State writes are atomic at defined transaction boundaries.

### 4.6 Authority Service
Evaluates capability-specific authority at execution and irreversible mutation boundaries. It records decisions and expiry/scope.

### 4.7 Capability Registry
Defines named capabilities, owning services, prerequisites, validators and authority requirements.

### 4.8 Worker Manager
Selects/dispatches replaceable workers and records execution envelopes, resource budgets and structured results.

### 4.9 Driver Manager
Provides governed adapters for GitHub, Git, CI, filesystem, broker/read-only feeds and future external systems.

### 4.10 Evidence Service
Indexes, seals and verifies evidence references. It does not convert evidence into broader claims than the validator contract allows.

### 4.11 Knowledge Service
Stores provenance-bound reusable findings, relationships and failure knowledge. Knowledge is advisory and non-mutating.

### 4.12 Observability Service
Exposes mission/task state, blockers, waits, worker activity, authority decisions, events and evidence navigation.

## 5. Runtime entities

### MissionInstance
Required fields include mission_id, definition_id/version/hash, lifecycle_state, created_at, authority_context_ref, source_authority bindings, completion status and evidence refs.

### TaskInstance
Required fields include task_id, mission_id, task_definition_id, dependencies, capability, owner_service, lifecycle_state, attempt_count, retry_budget, lease, worker_execution_ref, wait_condition, result/evidence refs and terminal classification.

### WorkerExecution
Binds task fingerprint, worker identity/type, input contract hash, allowed scope, resource/token budget, start/end, exit status, structured result and artifacts.

### AuthorityDecision
Binds capability, subject/actor, target scope, mission/task, decision, constraints, issued_at, expiry when applicable and evidence/provenance.

### EvidenceRecord
Binds claim type, producer, validator, source/data authority, immutable artifact reference/hash, limitations and sealing state.

## 6. Task lifecycle

Canonical task states:

PENDING → RUNNABLE → LEASED → EXECUTING → VALIDATING → {SUCCEEDED | WAITING | REPAIRABLE | BLOCKED_HUMAN | BLOCKED_LIVE_EVIDENCE | INVALIDATED | FAILED_TERMINAL}

WAITING and REPAIRABLE are non-terminal.

A completed execution may be resumed at VALIDATING after a crash if valid execution evidence exists; the worker MUST NOT be rerun solely because validation did not finish.

## 7. Mission lifecycle

CREATED → VALIDATING → READY → RUNNING → {WAITING | BLOCKED | COMPLETED | FAILED | CANCELLED}

A mission is COMPLETED only when its frozen completion contract evaluates true from durable task/evidence state.

## 8. Concurrency model

Safe independent analysis, repair preparation and CI waiting may run concurrently.

Mutations sharing a serialization key MUST serialize. Initial keys include:

- repository protected source integration;
- same branch/ref mutation;
- same PR metadata mutation;
- same filesystem destructive target;
- same live observer singleton;
- broker/order authority surfaces.

Repository merges serialize against refreshed main.

## 9. Leases and crash recovery

Execution leases prevent duplicate active ownership. Leases expire/recover after supervisor failure. Before rerunning a task, TBOS checks committed mutation/evidence markers to prevent duplicate side effects.

Every externally mutating handler requires an idempotency strategy.

## 10. Wait model

WAITING is durable and event/time driven. Examples:

- WAITING_CI
- WAITING_REVIEW
- WAITING_MARKET_SESSION
- WAITING_EXTERNAL_SERVICE
- WAITING_RATE_LIMIT

Waiting tasks consume no worker tokens. Independent tasks remain schedulable.

## 11. Blocker routing

Handlers classify failures into candidate defect, baseline defect, environment, infrastructure, external service, authority, evidence/data, invariant violation or unknown.

Repairable blockers route to bounded repair tasks. Repeated independent reproduction may create a baseline repair task. Human escalation occurs only when policy identifies a true decision boundary.

## 12. Repository integration architecture

GitHub Service owns PR semantics. Git Service owns repository/ref/diff mechanics. CI Service owns check/run interpretation. Review Service owns review-contract evaluation. Merge Service composes these but cannot bypass them.

Canonical integration flow:

refresh authority → establish candidate fingerprint → resolve base/conflicts → validate local bounded scope → push if authorized → attach/update PR when required → wait CI without worker → classify failures → repair/retry → review gate → JIT authority/head/base recheck → merge serially → refresh main → invalidate affected stale candidates.

Creating a successor PR is not a default step.

## 13. Research architecture

Research Mission Service coordinates hypothesis lifecycle but does not self-certify edge. Data, leakage, negative-control, OOS/WFA, cost, robustness, multiple-testing and prospective validators remain separate gates with evidence records.

Failed hypotheses are retained in a failure registry with specification/provenance sufficient to prevent accidental duplicate search.

## 14. Live observation architecture

Live Observation Service is distinct from trading execution. Default authorities remain false for broker writes/orders/paper/live trading. Read-only observation requires explicit dated launch-plan/subscription contracts rather than permanent instrument-count constants.

Runtime outputs MUST be written to designated runtime/evidence storage, not frozen source checkouts.

Market-calendar shutdown and graceful drain are owned runtime capabilities.

## 15. Security boundary

Credentials are references to protected secret providers/locations and MUST NOT be copied into mission definitions, logs, evidence bodies or worker prompts unless a driver contract explicitly requires a secure mediated value.

Workers receive minimum necessary scope.

## 16. Storage boundary

Source code authority remains GitHub. Large datasets/runtime evidence may remain external with immutable hashes/manifests. TEP stores references and provenance rather than duplicating all large data into the control-plane state store.

## 17. API boundary

Every mutating API operation maps to a named capability and authority check. Read APIs expose state/evidence without granting mutation capability.

## 18. Deployment boundary

TEP v1 targets a single trusted Mac/control host with external TradeBotData storage where appropriate. Distributed execution is deferred. The architecture MUST avoid assumptions that make later process separation impossible.

## 19. Prohibited architectures

TEP v1 MUST NOT become:

- a single giant Python controller containing every domain rule;
- a prompt-history database masquerading as state;
- a worker that directly mutates GitHub/broker/filesystem outside services;
- a scheduler that embeds CI/research/trading business policy;
- a collection of per-PR special-case handlers;
- a certification system that trusts its own producer without independent validation.

## 20. Architecture acceptance

This architecture is review-ready when module ownership is unambiguous, dependency direction is enforceable, task recovery/idempotency are specified, mutation authority is service-mediated, and reference missions can be mapped without bypasses.