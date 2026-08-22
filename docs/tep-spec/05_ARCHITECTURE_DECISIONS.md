# TEP v1 — Architecture Decisions

Status: DRAFT
Version: 1.0.0-draft

This document records Phase-0 decisions. Detailed ADR files may later split these entries without changing their IDs.

## ADR-001 — TEP above TBOS
Decision: TEP is the top-level platform; TBOS is its durable runtime kernel.
Rationale: scheduling/runtime mechanics must not own domain governance.
Rejected: expanding the weekend orchestrator into a universal monolith.

## ADR-002 — Modular monolith first
Decision: v1 is a modular monolith/process set on one trusted host with strict internal boundaries.
Rationale: current scale does not justify distributed-system complexity.
Rejected: Kubernetes/microservices as starting architecture.

## ADR-003 — Declarative mission definitions
Decision: missions are versioned declarative data validated against schemas.
Rationale: durable orchestration cannot depend on prompt transcripts or bespoke controller code.

## ADR-004 — Service-owned domain semantics
Decision: GitHub, CI, Git, merge, research, evidence and live-observation semantics live in owning services.
Rationale: prevents scheduler/worker policy leakage.

## ADR-005 — Replaceable workers
Decision: Codex is the initial worker, not platform authority.
Rationale: model/vendor replacement and independent validation must remain possible.

## ADR-006 — Explicit capability/authority model
Decision: all material mutations map to named capabilities with JIT authority evaluation.
Rationale: tool access must not imply authorization.

## ADR-007 — Durable event/state model
Decision: committed mission/task state and durable events are authoritative; worker/chat output is not.
Rationale: crash recovery and autonomous continuation require machine-readable state.

## ADR-008 — Evidence and knowledge are separate
Decision: evidence supports claims; knowledge stores reusable provenance-bound findings. Neither substitutes for runtime state.
Rationale: avoids mutable summaries becoming certification evidence.

## ADR-009 — GitHub remains source authority
Decision: TEP does not create a competing source-of-truth repository.
Rationale: preserve existing governance and integration semantics.

## ADR-010 — External large evidence by reference
Decision: large immutable datasets/evidence may live on TradeBotData/approved archive with hashes/manifests; control-plane stores references.
Rationale: repository/state database should not become a bulk-data archive.

## ADR-011 — Serial merge, parallel preparation
Decision: independent preparation/CI may be parallel; merges serialize against refreshed protected source authority.
Rationale: avoids stale readiness after main changes.

## ADR-012 — Successor PRs exceptional
Decision: update/repair an existing integration surface where safe. Current-main successor reconstruction requires explicit reason.
Rationale: uncontrolled successor creation worsens repository cleanup.

## ADR-013 — Persistent supervisor
Decision: TEP requires a singleton persistent supervisor with heartbeat and restart/resume.
Rationale: autonomous workflows cannot depend on an interactive terminal.

## ADR-014 — launchd is deployment mechanism, not architecture
Decision: macOS launchd may supervise v1 processes but core runtime contracts remain launchd-independent.
Rationale: avoid coupling platform semantics to one service manager.

## ADR-015 — Local transactional state store first
Decision: use a transactional local database for control-plane state in v1; exact engine selection remains an implementation ADR after repository compatibility review.
Rationale: atomic state and crash recovery are required; premature database choice is unnecessary.

## ADR-016 — Append-preserved evidence
Decision: sealed evidence is immutable/content-addressed. Corrections supersede rather than overwrite.

## ADR-017 — Typed blocker model
Decision: repairable, waiting, human-only, live-evidence, invalidated and terminal states are first-class.
Rationale: generic BLOCKED caused autonomous dead ends.

## ADR-018 — CI waits are worker-free
Decision: CI polling/event waits do not invoke Codex unless a terminal failure has been classified as candidate-repairable.
Rationale: saves tokens and prevents speculative repair during normal CI latency.

## ADR-019 — Baseline failure convergence
Decision: common baseline/environment failures are classified separately from candidate defects; one bounded baseline repair may serve multiple lanes.

## ADR-020 — Research certification outside scheduler
Decision: TBOS schedules research validators but cannot itself certify structural edge.
Rationale: producer/orchestrator self-certification is insufficient independence.

## ADR-021 — Live observation separate from execution
Decision: read-only live observation is a distinct service/capability family from broker/order execution.
Rationale: operational evidence should not accidentally widen trading authority.

## ADR-022 — Dynamic session subscription contract
Decision: instrument families/unions are derived from dated launch plans and runtime overlap, not hardcoded totals.
Rationale: observed family sizes change by session.

## ADR-023 — Runtime output isolation
Decision: runtime/evidence outputs cannot be written into frozen source checkouts except explicitly declared test fixtures.
Rationale: source authority contamination occurred in prior live operation.

## ADR-024 — Market-calendar lifecycle
Decision: read-only market observers support calendar-aware startup/shutdown and graceful drain.
Rationale: post-market persistence is an operational defect even when it is not proven causal for durability failures.

## ADR-025 — Complexity admission gate
Decision: new service/module/dependency requires ownership, necessity, failure/recovery, evidence and removal rationale.
Rationale: TEP must reduce rather than institutionalize coordination complexity.

## Unresolved implementation ADRs

The following are intentionally not frozen yet:

- exact local transactional database engine;
- exact schema serialization format beyond versioned machine-readable contracts;
- whether internal components share one process or a small supervised process set initially;
- exact API transport for local applications;
- long-term secret provider.

These are implementation decisions, not excuses to begin coding before Phase-0 freeze.