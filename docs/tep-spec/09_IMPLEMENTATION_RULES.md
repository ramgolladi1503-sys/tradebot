# TEP v1 — Implementation Rules

Status: DRAFT
Version: 1.0.0-draft
Normative: Yes

## IR-001 — Bind implementation to exact authority
Every substantial implementation task MUST record repository, branch/worktree and starting SHA. Drift is detected before mutation.

## IR-002 — Reuse before rebuild
Before creating a component, inspect repository/evidence for validated equivalent implementation. Reuse or migrate when provenance and contract compatibility are proven.

## IR-003 — No dirty canonical checkout as integration authority
A heavily dirty/unknown-provenance checkout may be archaeology evidence but MUST NOT silently become merge/release authority.

## IR-004 — Small bounded changes
Each implementation unit MUST have explicit allowed files/modules, prohibited scope, tests and exit verdicts. Unrelated cleanup is prohibited.

## IR-005 — No unnecessary PR creation
Use an existing safe PR/branch when the mission is to repair it. Create a successor only when the mission explicitly establishes why updating the predecessor is unsafe or semantically wrong.

## IR-006 — No force push by default
Force-push capability is separate and disabled unless a frozen task explicitly requires and authorizes it.

## IR-007 — JIT mutation checks
Immediately before irreversible mutation, refresh exact target/head/base/authority/dependencies and reject stale execution fingerprints.

## IR-008 — Structured worker contracts
Workers receive task objective, exact authority, allowed/prohibited scope, expected outputs, validation commands/contracts, evidence requirements and stop conditions. Raw global history is not the default worker input.

## IR-009 — Worker results are proposals until validated
A worker saying PASS or COMPLETE has no platform effect until the owning validator commits the corresponding state transition.

## IR-010 — Retry budgets are typed
Syntax/test/candidate repair, environment retry, CI rerun and external-service retry have separate bounded policies. Exhaustion produces a typed blocker, not an infinite loop.

## IR-011 — CI waits are passive
Do not invoke workers merely because CI is pending. Wake on terminal state or bounded timeout requiring classification.

## IR-012 — Baseline comparison before candidate repair
When a failure may be baseline/environmental, reproduce or compare against the relevant baseline before modifying candidate source when feasible.

## IR-013 — Validators cannot be weakened to pass
Do not delete/skip required tests, lower thresholds, fabricate fixtures/evidence or hardcode PASS/zero counters to satisfy gates.

## IR-014 — Protected paths
Credentials, sealed evidence, unique runtime data, active research authorities and designated canonical/protected checkouts require explicit capability and preservation checks before mutation.

## IR-015 — Runtime/source isolation
Production/read-only runtime artifacts go to configured runtime/evidence roots. Source checkouts are not runtime data stores.

## IR-016 — Dynamic launch contracts
Session-specific instrument/subscription sets are derived from versioned launch plans and observed overlap; historical totals are evidence, not constants.

## IR-017 — Live freshness
Fresh live proof binds exact candidate SHA/session/producer/validator. Prior sessions, replay and unit tests cannot satisfy a fresh-live gate unless the contract explicitly says historical evidence is acceptable.

## IR-018 — Research freeze before outcome access
Where selection bias matters, hypothesis/specification and development/holdout boundaries MUST be frozen before accessing protected outcome/holdout data.

## IR-019 — Failed research is retained
A rejected hypothesis is recorded with mechanism/spec/data/test/verdict sufficient to prevent blind retesting. New attempts require materially new rationale/spec/data.

## IR-020 — Search pressure accounting
Autonomous research records number/families of tested candidates and strengthens selection-aware validation as search breadth increases.

## IR-021 — Realistic execution costs
Economic certification uses applicable spread, slippage, fees, taxes, impact, liquidity, latency, fills, capacity and expiry mechanics. Gross backtest results are not net edge.

## IR-022 — Destructive cleanup is last
Cleanup candidates are produced after repository/PR/evidence decisions. Age, directory count or disk pressure alone cannot prove safe deletion.

## IR-023 — Observability required
Every long-running task exposes state, last progress time, blocker/wait reason, attempt budget and evidence/result refs. Silent background work is non-conforming.

## IR-024 — Heartbeat is not progress
Supervisor heartbeat proves liveness only. Mission/task progress requires state/event evidence.

## IR-025 — Cancellation is governed
Cancellation records who/what requested it, affected tasks, mutation boundary state and recovery implications. Killing a process is not equivalent to clean cancellation.

## IR-026 — Configuration is versioned
Mission-relevant configuration is hashed/versioned and referenced by executions/evidence. Mutable ambient configuration must not make results irreproducible.

## IR-027 — Secrets are mediated
Secrets are not persisted in prompts/state/evidence. Drivers receive mediated credentials using the minimum necessary scope.

## IR-028 — Dependency updates are explicit
Adding external libraries/services requires compatibility, security, operational and removal rationale. Do not introduce infrastructure to solve a local coding convenience.

## IR-029 — Tests follow contract layers
At minimum: unit tests for pure contracts, integration tests for service/driver boundaries, failure-injection for durable/mutating paths, and reference-mission tests for orchestration.

## IR-030 — Independent verification for critical claims
Critical authority, live, merge, destructive cleanup and structural-edge certification require validation independent of the producer/worker that performed the action when feasible.

## IR-031 — Controlled verdict vocabulary
Implementations MUST use explicit verdicts such as PASS, FAIL, BLOCKED, WAITING, INVALIDATED, NOT_APPLICABLE, UNKNOWN and domain-specific governed certification states. Ambiguous success prose is insufficient state.

## IR-032 — No hidden fallback success
Fallback/degraded modes must be explicit in state/evidence. A degraded path cannot emit the same certification as the primary path unless the frozen contract explicitly allows it.

## IR-033 — Rollback before rollout
Any migration that can replace/delete existing validated infrastructure requires rollback and preservation strategy before activation.

## IR-034 — One integration lane per semantic unit
Related stacked/overlapping PRs are modeled as dependency/integration components rather than blindly treated as independent merge candidates.

## IR-035 — Phase gates are real
Do not implement later-milestone production behavior simply because scaffolding makes it convenient. Crossing a milestone gate requires its specified evidence.

## Authority defaults

`11_CAPABILITY_AUTHORITY_CATALOGUE.md` is the single normative source for capability names, owners, default authorization state, required authority, JIT checks and evidence. Implementations MUST NOT maintain a second hand-written authority-default list from this document.

Unless the canonical catalogue and a frozen scoped mission decision explicitly allow a capability, governed mutation is DENY. Tool possession, credentials, historical authorization or omission from an example never imply authorization.

## Implementation release gate

Production implementation may begin only after the Phase-0 package is frozen at an exact SHA and an implementation task explicitly binds to that authority. The existence of this document alone does not authorize implementation.