# Issues 7–11 Campaign Review

## Agent Work Contract

`source_agent: hermes + gsd`; actions: `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `MAP_WORKFLOW`, `CREATE_ACCEPTANCE_GATES`, `PLAN_PR`, `GENERATE_TESTS`, `GENERATE_PATCH`, `FIX_TEST_FAILURE`, `UPDATE_DOCS`. Scope is the offline Issues 7–11 reliability repair and its evidence bundle in this PR. No order, broker, paper/live authority, credentials, or production data mutation is permitted.

## Scope Guard

Changed high-risk paths are `config/feed_runtime_reliability.py`, `core/feed_health_truth.py`, `core/feed_hold_gate.py`, and `core/orchestrator.py`. Changes preserve global feed, freshness, recovery, risk and kill-switch gates; there is no broker/order API call, strategy-threshold change, token-universe change, or live-mode change. The config addition `FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC` bounds persisted feed-truth age (default 3 seconds); missing or invalid authority fails closed. PR #936 is excluded. PR818 is outside this review's local acceptance evidence, per the user's instruction.

## Grill Me Review

The change set is unusually broad (174 files) and includes substantial evidence and planning material alongside code. The main review risks are that offline proof can be mistaken for live parity, evidence artifacts can drift, and unresolved lineage/identity boundaries can be overclaimed. The PR body and `FINAL_VERDICT.json` retain those limits as open/unknown. The merge-base is current `main` at PR preparation; PR #957 overlaps feed/token readiness and still needs independent disposition.

## Hermes Review

Hermes contracts define fail-closed behavior for missing/stale data, identity mismatches, incomplete persistence, and candidate dependency uncertainty. Shared transport/recovery and execution authority remain outside candidate-level selective-unhold behavior. Per-issue architecture contracts are in the adjacent `issues_7_11_hermes_*.md` files.

## GSD Review

GSD plans scope the implementation, regression coverage, and mutation attacks. The PR worktree focused regression passed 459 tests; 15 checked-in harnesses passed and killed 27/27 targeted mutants. The broader 8,740-pass run was from the campaign source worktree, not this PR SHA, and is not exact-head evidence. Hosted CI is authoritative for this commit.

## QA / Safety Review

Offline tests and mutation probes cover the repaired contracts. They do not establish live runtime parity, service restart behavior, complete historical source lineage, or all external writers. No broker/order actions were exercised. The safety-relevant health gate that calls `MockBroker.place_order` was intentionally not run locally. Preserve this distinction in all status claims.

## High-Risk Path Review

High-risk feed/orchestrator paths were changed narrowly to classify persisted feed truth and preserve fail-closed ranking holds. Reviewed invariants: stale or invalid snapshots hold; freshness age is bounded; global/transport blockers remain effective; unknown candidate identity does not grant selective unholding; ranking remains read-only. Exact behavior proof is in the focused feed-truth/ranking tests listed in the PR body. This review does not certify live execution.

## Acceptance Proof

Locally: 459 focused tests passed; all 15 Issues 7–11 harnesses passed; 27/27 targeted mutants were killed; compileall completed with pre-existing SyntaxWarnings. `FINAL_VERDICT.json` correctly remains false for offline campaign verification and live verification. The pending hosted checks must finish on the exact PR head before CI status can be called green.

## Runtime Proof Required After Merge

Separately authorized read-only evidence is still required for actual runtime startup/restart, persisted state across process boundaries, captured-source parity, feed snapshot freshness under live timing, and exact dynamic candidate identity/dependency health. No live or paper promotion is implied by this PR.

## What This PR Does Not Prove

It does not prove full prompt-wide issue closure, T-1/CAS authoritative lineage, managed-service restart parity, external-writer/captured parity, dynamic candidate isolation, original transport/auth root cause, or live correctness. It does not certify a trading edge or permit execution.

## Human Approval

This is a draft PR for human review. Human review is required before any promotion, live/runtime validation beyond read-only observation, or merge. No such approval is represented here.
