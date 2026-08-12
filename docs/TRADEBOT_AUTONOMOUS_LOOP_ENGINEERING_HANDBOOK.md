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

## Batched certification execution

Repository-wide CI is expensive and must not be confused with task-local validation. The governed execution policy is `research/governance/autonomous_loop/PROGRAM_CERTIFICATION_EXECUTION_POLICY.yaml`.

For normal task development, every task still runs the focused, adversarial, integration and relevant regression evidence needed to reach `REGRESSION_VALID`. Reaching `REGRESSION_VALID` may release the next dependency for **provisional implementation only** through the build scheduler. It does not mean the prerequisite is sealed, independently verified, CI-green, live-valid or finally certified.

The strict dependency scheduler is unchanged for final completion. A downstream task cannot be `SEALED` while any strict dependency remains incomplete. If an upstream task later enters `REPAIR_REQUIRED`, `BLOCKED`, or another non-complete state, any downstream work built provisionally remains unsealed and must not be represented as certified.

Broad repository CI and combined exact-SHA independent verification are run at architecture checkpoints rather than after every task:

- CP1: T01-T03
- CP2: T04-T11
- CP3: T12-T20
- CP4: T21-T26
- CP5: T27-T35
- dynamic-final checkpoint: governed T36+ tasks created from evidence only

CI evidence may be reused across tasks in the same checkpoint only when it is bound to the same exact checkpoint candidate SHA, that candidate contains the full claimed changed surface, and the task-specific focused/adversarial evidence is also exact-SHA-bound to that candidate. Any subsequent code change invalidates earlier exact-SHA CI evidence for final sealing unless the final candidate is re-certified.

This batching rule reduces repeated CI cost; it does **not** lower any seal gate. The final program still requires full repository regression, exact-SHA independent verification, zero unresolved MAJOR/CRITICAL findings, zero mandatory UNKNOWNs, and green program CI.

## Dynamic task law

Dynamic task IDs begin at T36 and increase monotonically. Every dynamic task must:

1. use an approved reason code;
2. prove that an existing locked guarantee would remain unsafe or unproven without the task;
3. identify the creating task and evidence;
4. define dependencies, allowed/prohibited scope, tests, exit gates and stop conditions;
5. answer the six rationale questions;
6. update `TASK_REGISTRY.yaml` and `TASK_ADDITION_LOG.md` before implementation.

A failing assertion that is already inside the current task scope is not by itself justification for a new task. T36 and T37 must not be fabricated merely because the release hold currently extends through T37; they must exist only if evidence independently justifies them under this law.

## Truth boundaries

The loop never converts UNKNOWN to PASS, MISSING to ZERO, unit-test PASS to live PASS, historical PASS to forward PASS, correlation to causation, or backtest edge to tradable edge.

Operational correctness, economic edge, execution viability, prospective support and structural-edge certification remain separate claims.

## Continuity authority

Chat is not the orchestration authority. `research/governance/autonomous_loop/TASK_REGISTRY.yaml` is the machine-readable continuity state. Exact SHAs, evidence paths, findings, blockers and next actions belong in repository artifacts.

`PROGRAM_CERTIFICATION_EXECUTION_POLICY.yaml` governs when broad CI is run. `PROGRAM_RELEASE_POLICY.yaml` governs program-level merge eligibility. Neither grants execution authority.

## Initial external attachment

T01 references GitHub PR #815 as an external implementation vehicle. The autonomous-loop framework is independent of PR815 and must be validated on its own branch/PR before it is treated as certified governance authority.

The framework itself is not to be merged to `main` merely because framework certification passes. Program release remains held by `PROGRAM_RELEASE_POLICY.yaml`; current policy requires the governed range through T37 to be present and sealed, exact-SHA program verification and CI to pass, and explicit human main-merge authority. This does not authorize inventing T36/T37 to satisfy the numeric hold.
