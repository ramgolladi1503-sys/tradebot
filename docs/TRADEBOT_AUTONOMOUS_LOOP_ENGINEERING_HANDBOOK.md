# TradeBot Autonomous Loop Engineering Handbook

## Authority and mission

This repository implementation operationalizes the locked three-index + global-context architecture through a governed task registry. T01-T35 are immutable initial task identifiers. T36+ may be created only when repository evidence exposes a materially necessary prerequisite, integration seam, safety/governance gap, data dependency, observability requirement, test-isolation requirement, independent-review finding, end-to-end gap, regression gap, live-validation gap, migration or compatibility requirement.

The loop optimizes for a coherent, reproducible, recoverable, causal, fail-closed and independently verifiable system. It does not optimize for task count, green-test count or preserving sunk-cost implementations.

## Safety boundary

The autonomous-loop framework itself has no execution authority:

- broker_write_authority=false
- order_authority=false
- paper_authorized=false
- live_authorized=false

It must not change TradeBuilder, ranking, strategy selection, risk limits, broker/order paths, execution behavior or frozen-model economics merely to progress tasks.

## Per-task progression

The legal progression is:

`PENDING -> SPEC_FROZEN -> IMPLEMENTING -> IMPLEMENTATION_VALID -> ADVERSARIAL_VALID -> INTEGRATION_VALID -> REGRESSION_VALID -> INDEPENDENTLY_VERIFIED -> CI_GREEN -> SEALED`

Fail-closed states include `REPAIR_REQUIRED`, `BLOCKED`, `BLOCKED_LIVE_WINDOW`, `BLOCKED_DATA`, `BLOCKED_AUTH`, `INVALIDATED`, `NO_STRUCTURAL_EDGE_FOUND` and `SUPERSEDED`.

No task is sealed with unresolved MAJOR/CRITICAL findings, mandatory UNKNOWNs, missing exact candidate SHA, missing focused/adversarial/integration/regression evidence, missing required independent verification, or missing required CI evidence.

## Batched certification policy

Repository-wide CI is intentionally checkpoint-batched. `ci.required: true` remains a seal requirement; it does not require launching the full repository suite after every small implementation step.

The machine-readable policy is `research/governance/autonomous_loop/CERTIFICATION_POLICY.yaml`.

During each task, the loop must run the highest-information local gates available for that task: focused tests, adversarial tests, task-relevant integration tests, compile/static validation, scope guards and execution-authority guards. Any failure in those gates blocks progression immediately; batching is not permission to stack work on a known-bad task.

Broad regression and repository CI are run at architecture checkpoints:

- C01: T01-T03 — prospective evidence foundation plus frozen NIFTY preservation.
- C02: T04-T11 — BANKNIFTY and SENSEX specification, discovery, freeze/no-edge and independent certification.
- C03: T12-T20 — global evidence, causal snapshot, after-close state, scoring, reporting, ledgers and daily orchestration.
- C04: T21-T26 — repository certification, shadow/prospective program and structural-edge/trading-authority decisions.
- C05: T27-T35 — Global Context V2 and the separate intraday-regime research path.
- C06: evidence-justified T36+ tasks, including T36/T37 only when repository evidence actually requires them.

A single broad CI/regression result may support multiple tasks only when those tasks are bound to the same exact candidate SHA and the test scope covers the combined changed surface. Passing CI on an earlier SHA cannot be reused after implementation changes.

Before final program completion, one exact-final-SHA whole-repository certification is mandatory: focused suites, adversarial suites, integration, full regression, repository CI, architecture invariants, execution-isolation checks and independent exact-SHA verification.

No framework or task-chain merge to `main` is automatic. Even a fully certified candidate remains unmerged until the user explicitly authorizes the final main merge.

## Dynamic task law

Dynamic task IDs begin at T36 and increase monotonically. Every dynamic task must:

1. use an approved reason code;
2. prove that an existing locked guarantee would remain unsafe or unproven without the task;
3. identify the creating task and evidence;
4. define dependencies, allowed/prohibited scope, tests, exit gates and stop conditions;
5. answer the six rationale questions;
6. update `TASK_REGISTRY.yaml` and `TASK_ADDITION_LOG.md` before implementation.

A failing assertion that is already inside the current task scope is not by itself justification for a new task.

## Truth boundaries

The loop never converts UNKNOWN to PASS, MISSING to ZERO, unit-test PASS to live PASS, historical PASS to forward PASS, correlation to causation, or backtest edge to tradable edge.

Operational correctness, economic edge, execution viability, prospective support and structural-edge certification remain separate claims.

## Continuity authority

Chat is not the orchestration authority. `research/governance/autonomous_loop/TASK_REGISTRY.yaml` is the machine-readable continuity state. Exact SHAs, evidence paths, findings, blockers and next actions belong in repository artifacts. `CERTIFICATION_POLICY.yaml` governs when broad CI is required versus when task-local gates are sufficient for continued implementation.

## Initial external attachment

T01 references GitHub PR #815 as an external implementation vehicle. The autonomous-loop framework is independent of PR815 and must be validated on its own branch/PR before T01 is advanced through it.
