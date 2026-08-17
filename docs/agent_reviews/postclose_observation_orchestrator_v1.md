# Post-Close Observation Orchestrator V1 — Agent Review Evidence

## Agent Work Contract

Objective: add one detached, post-close, read-only orchestration entrypoint for the 2026-08-18 observation session. The orchestrator may reconcile producer subscription-truth artifacts and invoke the already-isolated kernel bundle sealer/ingestor. It must not modify or merge into the frozen live producer before market hours, must not start broker/feed/websocket processes, and must not grant execution or economic certification authority.

Frozen authorities are explicit constants:

- producer: `f0f5b3d3659415ab36662291e91b8f57fd8d1e07`
- subscription verifier: `21f95a8b5908a8f6b9a0d7bbf459877efed41262`
- kernel ingestion tool head: `10d2f68b08026a269e9c25095bebca683ada67e5`
- sealed kernel base: `46dd4f7df9b63486eb633a12baf25412cd4f761d`

## Scope Guard

Allowed scope is additive validation-only code, focused tests, CI, and this evidence record. Prohibited scope includes producer/feed/broker changes, order paths, authority changes, strategy promotion, live process launch, websocket subscription mutation, historical-to-prospective promotion, and missing-to-zero coercion.

The orchestrator requires exact clean Git worktrees for all three authorities, external runtime storage, regular non-symlink inputs, and write-once outputs. Optional absent lanes are recorded as `UNKNOWN`, not `PASS`.

## Grill Me Review

Adversarial questions:

1. Can a branch name such as `main` substitute for an exact SHA? No; exact 40-hex SHA checks are required.
2. Can a symlink substitute another evidence file? No; inputs and tool scripts are checked before resolution and must be regular files.
3. Can missing subscription snapshots be treated as zero divergence? No; the stage is `UNKNOWN_NOT_SUPPLIED`.
4. Can missing H1/CAS artifacts still yield kernel ingestion PASS? No; seal/ingestion are not run and remain UNKNOWN.
5. Can the runtime/report be written into the producer or validation repos? No; external-root boundaries fail closed.
6. Can a failing downstream verifier be ignored? No; any invoked stage nonzero return code raises and stops orchestration.
7. Does a successful orchestration create prospective evidence? No. It only records exact steps and bindings; `prospective_supported=false`.

## Hermes Review

Hermeticity review: orchestration does not import producer broker/feed modules. It invokes only three allow-listed script paths from exact clean worktrees. All evidence outputs are placed in the explicitly supplied external runtime root. Tool stdout/stderr are bounded in the report to avoid uncontrolled report growth.

The implementation deliberately does not call the PR790 market observer. That analytics lane remains a separate post-close `--once` action until its exact input/output and authority contract are independently bound into this orchestrator.

## GSD Review

The minimal high-information workflow is:

1. verify exact clean producer/tool authorities;
2. reconcile supplied subscription-truth snapshots if present;
3. seal supplied H1/CAS artifacts if present;
4. ingest the sealed bundle with the exact kernel verifier;
5. write one external write-once orchestration report.

No producer code is changed and no market-hours process is added.

## QA / Safety Review

Focused tests cover frozen authority constants, rejection of symbolic refs, invalid dates, symlink rejection, nonzero-stage fail-closed behavior, UNKNOWN preservation for missing optional stages, external runtime-root enforcement, and write-once report semantics.

Hard safety state remains:

- `broker_write_authority=false`
- `order_authority=false`
- `paper_authorized=false`
- `live_authorized=false`
- `execution_viable=false`
- `prospective_supported=false`
- `structural_edge_certified=false`

## High-Risk Path Review

High-risk paths are intentionally absent: there is no broker client construction, order mutation, subscription mutation, feed startup, websocket ownership, strategy execution, or capital authority. The only subprocesses are Git authority checks and explicitly allow-listed Python validation scripts.

The most important failure mode is false promotion caused by absent evidence. This is addressed by explicit `UNKNOWN_NOT_SUPPLIED` / `UNKNOWN_NOT_RUN` states and by allowing downstream validators to fail closed.

## Acceptance Proof

Acceptance requires focused compile/tests and the repository agent-review evidence gate to pass on the exact PR head. Broad repository CI is reported separately and must not be silently converted into a focused PASS.

A focused PASS means only `IMPLEMENTATION_VALID` for this orchestration helper. It does not establish Aug-18 live evidence because the actual Aug-18 artifacts do not yet exist at implementation time.

## Runtime Proof Required After Merge

This PR is not required to merge into the frozen live producer. For actual use, run it post-close from an isolated worktree and provide:

- exact clean producer worktree at the frozen SHA;
- exact clean subscription verifier worktree at its frozen SHA;
- exact clean kernel verifier worktree at its frozen SHA;
- observation date `2026-08-18`;
- external runtime root;
- actual producer-written subscription snapshots when available;
- actual H1/CAS artifacts with explicit kernel sealer states when available.

The resulting report and child artifacts must be hashed/preserved as session evidence.

## What This PR Does Not Prove

It does not prove tick freshness, complete exchange delivery, feed recovery, live process correctness, H1 prospective performance, CAS directional edge, PR815 live attachment, T24/T25/T26 certification, execution viability, profitability, or structural edge. It does not promote replay/historical/synthetic evidence to prospective evidence.

## Controlled Verdict Boundary

Allowed implementation verdict after focused validation: `POSTCLOSE_ORCHESTRATOR_IMPLEMENTATION_VALID=PASS`.

Disallowed without later evidence: `LIVE_VERIFIED`, `PROSPECTIVE_SUPPORTED`, `EXECUTION_VIABLE`, `HISTORICAL_EDGE_SUPPORTED`, or `STRUCTURAL_EDGE_CERTIFIED`.

## Human Approval

No live-market merge, broker authority change, order authority change, paper/live authorization change, or strategy promotion is requested. Human approval remains required for any separate action that would cross those boundaries.
