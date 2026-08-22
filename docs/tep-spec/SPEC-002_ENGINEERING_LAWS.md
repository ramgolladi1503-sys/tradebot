# SPEC-002 — TEP Engineering Laws

Status: DRAFT  
Version: 1.0.0-draft  
Normative: Yes

## 1. Purpose

These are constitutional invariants for the TradeBot Engineering Platform. Subsystem specifications and implementations MUST conform unless this document is formally amended under SPEC-000.

## LAW-001 — Authority precedes mutation

No mutation may execute without explicit capability-specific authority valid at the mutation boundary.

## LAW-002 — Evidence precedes certification

A state or capability may not be certified from intent, configuration, mocks, summaries or adjacent evidence when its contract requires direct evidence.

## LAW-003 — State has one authoritative owner

A component MUST NOT silently own or rewrite another component's authoritative state.

## LAW-004 — Schedulers schedule; workers execute

Schedulers MUST NOT perform task business logic. Workers MUST NOT determine global scheduling policy.

## LAW-005 — Applications do not bypass services

Applications MUST NOT call external drivers directly when a platform service owns that capability.

## LAW-006 — Drivers contain no business policy

Drivers adapt external systems. Domain policy belongs in services or mission definitions.

## LAW-007 — Knowledge cannot mutate runtime

The Knowledge Engine is advisory/read authority. Knowledge retrieval alone MUST NOT grant mutation authority.

## LAW-008 — Durable work is resumable

Long-running or externally mutating work MUST have durable state sufficient for safe restart/resume.

## LAW-009 — Mutation is attributable

Every external or durable mutation MUST identify mission, task, actor/worker, authority, target, before-state when obtainable, result and evidence reference.

## LAW-010 — UNKNOWN remains UNKNOWN

Missing, unknown, stale, unavailable and zero are distinct states. No component may coerce uncertainty into success.

## LAW-011 — Tests do not impersonate reality

Unit, synthetic, mock, replay and historical tests MUST NOT be represented as fresh live or prospective evidence.

## LAW-012 — Current authority is rechecked at irreversible boundaries

Before merge, destructive cleanup, live authority change or comparable irreversible action, relevant authority and dependency state MUST be refreshed just-in-time.

## LAW-013 — Evidence is append-preserved

Evidence used for governance/certification MUST be immutable or content-addressed after sealing. Corrections create new evidence and explicit supersession; they do not silently rewrite history.

## LAW-014 — No hidden authority inheritance

GitHub metadata, push, merge, destructive cleanup, broker write, order, paper and live authorities are independent unless a frozen specification explicitly composes them.

## LAW-015 — No strategy loyalty

Engineering effort, prior success, sunk cost or naming does not grant research validity. Economic claims require their own governed evidence.

## LAW-016 — Gross edge is not tradable edge

Research services MUST keep gross signal evidence separate from costs, slippage, liquidity, impact, latency, fills, capacity and operational viability.

## LAW-017 — Search pressure is evidence context

Broad autonomous research MUST track multiple-testing/search pressure. The best result among many trials is not automatically structural edge.

## LAW-018 — Preserve before destructive cleanup

A path, branch, worktree or artifact is not deletable until unique commits, untracked data, runtime role, credentials/evidence references and unresolved mappings are proven absent or preserved elsewhere.

## LAW-019 — Baseline defects are repaired once

When materially independent candidates reproduce the same failure and evidence supports a shared baseline defect, the platform SHOULD route to one bounded baseline repair rather than duplicate candidate-specific workarounds.

## LAW-020 — CI must not be weakened to obtain green

Required checks, tests, reviewers or validators MUST NOT be disabled, bypassed or rewritten merely to obtain PASS.

## LAW-021 — Mission definitions are declarative policy

Mission definitions express goals, dependencies, constraints and completion contracts. They MUST NOT embed opaque execution code that bypasses scheduler/service governance.

## LAW-022 — Workers are replaceable and non-authoritative

A worker may propose or execute scoped changes. Worker output is not authoritative until validated by the owning service and evidence contract.

## LAW-023 — Blockers are typed

The platform MUST distinguish repairable blockers, wait states, true human decisions, live-evidence requirements and invalidated work. Generic BLOCKED MUST NOT be the final classification when a more precise state is knowable.

## LAW-024 — Waiting work does not freeze independent work

A task waiting for CI, external service, review or market session MUST NOT block independent runnable tasks unless a dependency explicitly requires it.

## LAW-025 — Merges serialize against refreshed source authority

Concurrent analysis and CI are allowed. Repository integration merges MUST serialize against a refreshed protected source authority and invalidate stale downstream readiness as required.

## LAW-026 — Successor creation is exceptional

Repair or update an existing PR/branch when safe. A successor is justified only by explicit preservation, lineage, authority or reconstruction requirements; successor proliferation is not a default repair strategy.

## LAW-027 — Live trading authority defaults false

Research, readiness, observation and engineering missions default to broker_write_authority=false, order_authority=false, paper_authorized=false and live_authorized=false.

## LAW-028 — Operational success does not prove economic success

Stable feeds, successful observation, clean shutdown, correct evidence capture or implementation validity MUST NOT be promoted to profitability or structural-edge claims.

## LAW-029 — Specification outranks implementation convenience

If implementation conflicts with a frozen specification, implementation is non-conforming until the specification is formally changed or the implementation is corrected.

## LAW-030 — Complexity requires justification

New services, interfaces, dependencies, persistent state and authority surfaces require an explicit complexity rationale and ownership. Duplicate responsibility is prohibited.

## Acceptance

These laws become FROZEN only with the Phase-0 constitution package. Any exception requires a versioned amendment under SPEC-000; local code comments, prompts or agent instructions cannot waive them.