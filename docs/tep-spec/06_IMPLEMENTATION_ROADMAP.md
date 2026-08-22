# TEP v1 — Implementation Roadmap

Status: DRAFT
Version: 1.0.0-draft

No milestone authorizes broker/order/live trading authority.

## M0 — Constitution Freeze

Deliver: SPEC-000/001/002 and 00–09 Phase-0 package.

Exit:
- cross-document consistency review PASS;
- unresolved questions explicitly recorded;
- no duplicate ownership;
- implementation rules and acceptance gates frozen.

Until exit: TEP_IMPLEMENTATION_AUTHORIZED=false.

## M1 — Kernel Contracts

Deliver:
- canonical schemas for MissionDefinition, MissionInstance, TaskInstance, WorkerExecution, AuthorityDecision, EventRecord, EvidenceRecord;
- mission parser/validator;
- deterministic task dependency evaluator;
- state transition library.

Tests:
- schema/version compatibility;
- illegal transition rejection;
- deterministic graph validation;
- UNKNOWN/MISSING truth preservation.

No external mutations.

## M2 — Durable State, Events and Supervisor

Deliver:
- transactional state store;
- atomic state/event commits;
- leases;
- persistent supervisor;
- heartbeat/singleton;
- crash/restart recovery;
- durable waits/timers.

Exit evidence includes injected failures at pre-execution, post-execution/pre-validation and post-mutation/pre-state-commit boundaries.

## M3 — Authority, Driver and Worker Frameworks

Deliver:
- capability registry;
- authority evaluator;
- execution envelopes;
- driver interfaces;
- Codex worker adapter;
- token/resource budgets;
- protected-scope enforcement.

Exit requires adversarial tests proving workers cannot grant themselves authority or escape scope.

## M4 — Git/GitHub/CI Services

Deliver:
- repository authority refresh;
- PR/ref/diff service;
- CI watcher/classifier;
- worker-free waits;
- current-main reconstruction support;
- conflict handling contract;
- review gate;
- JIT merge gate;
- serial merge invalidation.

Reference test corpus includes independent PRs, stacked PRs, partial overlaps, stale bases, conflicts, baseline CI failures, candidate CI failures and external CI failures.

## M5 — Evidence, Knowledge and Repair Convergence

Deliver:
- evidence sealing/index;
- provenance knowledge store;
- blocker router;
- candidate vs baseline failure classifier;
- bounded repair tasks;
- failure registry;
- successor/predecessor relationship model.

Exit requires proving that repeated baseline failures do not spawn per-PR speculative repairs.

## M6 — Repository Consolidation Reference Mission

Deliver a declarative mission capable of:
- inventorying PR/worktree/ref state;
- preserving unique authority;
- running independent repair lanes safely in parallel;
- waiting for CI without workers;
- serially merging only JIT-green candidates;
- closing/superseding only with explicit evidence;
- producing safe-delete candidates only after all preservation predicates pass.

Initial rollout is read-only, then bounded GitHub writes, then bounded cleanup authority in separate gates.

## M7 — Read-Only Live Observation Reference Mission

Deliver:
- dated launch plan;
- dynamic subscription derivation;
- read-only feed ownership;
- runtime-output isolation;
- durability instrumentation;
- external-storage failure semantics;
- market-calendar auto-shutdown;
- graceful drain and evidence seal.

Exit does not imply trading execution viability or economic edge.

## M8 — Research/CAS/REC-MD Integration

Deliver mission templates and validators for governed structural-edge discovery, CAS and REC-MD while preserving each program's existing evidence authority.

Required:
- frozen hypotheses;
- leakage audits;
- dev/OOS separation;
- negative controls;
- cost/robustness gates;
- search-pressure ledger;
- failure registry;
- independent certification boundary.

## M9 — API and Observability

Deliver stable read APIs, bounded mutation APIs, mission/task/event/evidence views, blocker navigation and operator controls.

No UI may bypass the same authority/service paths used by automation.

## M10 — Migration and Production Adoption

Deliver:
- compatibility/migration tooling from validated existing orchestrator artifacts where provenance is proven;
- independent model/engineering validation;
- rollback procedure;
- operator runbook;
- disaster recovery test;
- controlled deprecation of replaced scripts.

Existing working infrastructure is not deleted merely because TEP exists.

## Parallelization policy

Within a milestone, independent components may proceed in parallel only when contracts are frozen enough to avoid incompatible implementations. Cross-milestone parallel work is permitted for documentation/test fixtures but not when it bypasses an unmet foundational exit gate.

## Stop conditions

Implementation stops and returns BLOCKED when:
- frozen contract is contradictory;
- required authority is absent;
- unique evidence could be damaged;
- implementation would require weakening a validator;
- a source authority cannot be established;
- required live evidence is unavailable.

A stop condition does not authorize architectural improvisation.