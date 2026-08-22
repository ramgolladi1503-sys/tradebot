# TEP v1 — Master Plan

Status: DRAFT  
Version: 1.0.0-draft  
Authority: Phase-0 architecture candidate  
Implementation status: NOT_STARTED

## 1. Mission

The TradeBot Engineering Platform (TEP) is the governed engineering platform for autonomous and human-supervised work across the TradeBot ecosystem.

TEP separates platform governance, runtime orchestration, engineering services, external drivers, workers and applications so that automation can continue without a human acting as a message router while preserving explicit authority and evidence standards.

TEP does not certify profitability or structural edge by virtue of operating correctly.

## 2. Top-level architecture

TEP has six logical levels:

0. Enterprise governance
1. Platform contracts and registries
2. TBOS runtime kernel
3. Engineering/domain services
4. Drivers and workers
5. Applications and mission definitions

Dependencies flow downward through owned interfaces. Applications do not bypass service ownership to call drivers directly.

## 3. Foundational modules

TEP v1 defines twelve foundational module families:

1. Enterprise Core — governance, configuration, specification/mission/capability registries.
2. TBOS Runtime — durable execution kernel.
3. Mission Engine — declarative mission parsing, validation and lifecycle.
4. Engineering Services — GitHub, Git, CI, repair, merge, review, evidence and related services.
5. Driver Framework — external-system adapters.
6. Worker Framework — Codex and future replaceable execution workers.
7. Authority Framework — explicit capabilities and mutation authorization.
8. Knowledge Engine — provenance-bound engineering/research knowledge; no mutation authority.
9. Storage Framework — durable state, events, ledgers and content-addressed evidence references.
10. API Gateway — governed programmatic platform access.
11. Observability — health, telemetry, traces, task/mission status and evidence navigation.
12. Applications — TradeBot runtime, research, CAS, REC-MD, repository cleanup and other approved products.

Website/job workflows are not automatically in TEP v1 scope merely because they can be automated. Admission requires an explicit application specification and ownership rationale.

## 4. TBOS responsibility

TBOS is TEP's runtime subsystem, not the top-level platform.

TBOS owns:

- durable mission/task execution state;
- dependency-aware scheduling;
- event dispatch;
- worker dispatch and result intake;
- crash/resume orchestration;
- wait-state handling;
- supervisor lifecycle.

TBOS does not own GitHub semantics, CI policy, research validity, broker policy or application business logic.

## 5. Core execution model

Legal execution path:

Mission Definition → Mission Engine → Scheduler → Owning Service/Handler → Worker or Driver → Validator → Evidence/State Commit → Scheduler.

No prompt or worker response is itself durable platform state.

## 6. Mission model

A Mission is a versioned declarative objective composed of phases/tasks, dependencies, required capabilities, constraints, evidence requirements, retry/wait policies and completion conditions.

Mission definitions MUST be data, not opaque controller programs.

Initial reference missions:

- repository consolidation;
- CI convergence;
- governed read-only live preparation/observation;
- structural-edge research;
- CAS research;
- REC-MD research.

## 7. Capability model

Capabilities are explicit platform contracts such as:

- READ_REPOSITORY
- PUSH_BRANCH
- UPDATE_PR_METADATA
- MERGE_PR
- DELETE_WORKTREE
- START_READ_ONLY_OBSERVER
- BROKER_WRITE
- PLACE_ORDER

Capabilities declare prerequisites, authorities, owning service, validators and evidence requirements.

Capability availability is computed; it is not inferred from worker access.

## 8. Worker model

Workers are replaceable execution backends.

Initial worker: Codex.

A worker:

- receives bounded task contracts;
- may inspect/modify only authorized scope;
- returns structured result/evidence references;
- does not own mission state;
- does not grant itself authority;
- does not self-certify success.

## 9. Knowledge model

Knowledge records architecture decisions, provenance-bound facts, failure findings, PR relationships, research outcomes and operational lessons.

Knowledge MUST retain source/provenance and freshness semantics.

Knowledge may inform scheduling/design but cannot mutate runtime or grant authority.

## 10. Evidence model

Evidence is distinct from knowledge and state.

Evidence supporting a governed claim MUST be immutable/content-addressed after sealing and bind, where applicable:

- source SHA/version;
- mission/task;
- time/session;
- inputs/data authority;
- validator;
- result;
- limitations/caveats.

## 11. Research governance

TEP research support follows a governed discovery pipeline:

observation → hypothesis → falsifiable specification → data suitability → implementation → leak audit → development test → negative controls → OOS/WFA → realistic costs → robustness → multiple-testing controls → independent verification → prospective evidence when required → certification.

Failed hypotheses are retained as evidence. Search pressure is tracked.

## 12. Live governance

Default for engineering/research/readiness missions:

- broker_write_authority=false
- order_authority=false
- paper_authorized=false
- live_authorized=false

Fresh live evidence is distinct from replay, mocks, historical sessions and unit tests.

## 13. Repository governance

GitHub is source-code authority for governed repository integration.

Large immutable datasets/evidence may live outside GitHub with content/provenance manifests.

Current-main integration policy:

candidate → exact authority refresh → repair/update/reconstruct only if justified → CI/review → JIT merge gate → serial merge → refresh main → invalidate stale downstream readiness.

Successor PRs are exceptional, not default.

## 14. Storage direction

TEP v1 begins with local durable storage suitable for a single-machine control plane, with schemas designed for migration.

Technology selection is deferred to ADR review; no database choice is frozen by this master plan.

Required logical stores:

- mission/task state;
- event ledger;
- authority decisions;
- worker executions;
- evidence index;
- knowledge index;
- capability registry;
- configuration/version registry.

## 15. Supervisor direction

A persistent supervisor is required for autonomous continuation, singleton enforcement, heartbeat, crash recovery and scheduled/event-driven wakeups.

macOS launchd is a current deployment constraint but requires ADR justification before becoming a permanent platform dependency.

## 16. Observability

TEP MUST expose enough state to answer:

- What missions exist?
- What is running?
- What is waiting and why?
- What is blocked and is it repairable?
- Which worker is acting?
- What authority was used?
- What changed?
- What evidence supports the result?
- What requires a human?

A UI is not required for kernel correctness; APIs/state views precede UI.

## 17. Human role

Humans are product/governance authorities, not routine routers.

Human escalation is reserved for true decisions such as architectural approval, authority grants, risk acceptance, irreducible review, credentials, or other explicitly human-only contracts.

## 18. Phase-0 constitution package

Before implementation, the following MUST reach FROZEN together:

- SPEC-000 Specification Governance
- SPEC-001 Specification Writing Standard
- SPEC-002 Engineering Laws
- 00_MASTER_PLAN
- 01_VISION
- 02_GUIDING_PRINCIPLES
- 03_GLOSSARY
- 04_SYSTEM_ARCHITECTURE
- 05_ARCHITECTURE_DECISIONS
- 06_IMPLEMENTATION_ROADMAP
- 07_MODULE_DEPENDENCY_GRAPH
- 08_ACCEPTANCE_CRITERIA
- 09_IMPLEMENTATION_RULES

## 19. Planned implementation milestones

M0 — Constitution/specification freeze.  
M1 — Kernel contracts and executable state/mission core.  
M2 — Storage, event and authority foundations.  
M3 — Worker/driver framework and Codex worker.  
M4 — Git/GitHub/CI engineering services.  
M5 — Evidence/knowledge and convergence services.  
M6 — Repository consolidation reference mission.  
M7 — Read-only live preparation/observation reference mission.  
M8 — Research/CAS/REC-MD mission integration.  
M9 — API/observability/product hardening.  
M10 — Independent validation, migration and controlled production adoption.

Milestones require detailed entry/exit criteria in 06_IMPLEMENTATION_ROADMAP before implementation.

## 20. Explicit non-goals for v1

TEP v1 does not require:

- distributed multi-host scheduling;
- Kubernetes;
- microservices;
- automatic live trading;
- autonomous capital allocation;
- strategy certification by the orchestrator;
- replacing GitHub/Git/CI;
- replacing domain research validators;
- supporting every unrelated personal automation workflow.

These exclusions control complexity.

## 21. Drift control

No implementation begins solely because a capability sounds useful.

Every implementation must trace to a frozen requirement and owner. New modules require explicit complexity justification. Duplicate ownership is prohibited.

## 22. Phase-0 exit gate

Phase 0 passes only when:

- all constitution documents exist;
- terms and ownership are consistent;
- top-level dependencies are acyclic by design;
- authority/mutation boundaries are explicit;
- failure/recovery principles are explicit;
- implementation milestones are bounded;
- unresolved architecture questions are listed rather than guessed;
- no production implementation is represented as approved merely because the specification exists.

Until then:

`TEP_IMPLEMENTATION_AUTHORIZED=false`.