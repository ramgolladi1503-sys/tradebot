# Broker Write Guard Module Identity — GSD Stage 2

**Date:** 2026-09-30
**Source agent:** `gsd`
**Allowed actions:** `PLAN_PR`, `GENERATE_TESTS`, `GENERATE_PATCH`, `FIX_TEST_FAILURE`, `UPDATE_DOCS`
**Status:** Offline implementation and validation complete; production behavior remains unverified.

## GSD task contract

```text
source_agent: gsd
action: GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
title: Protect active broker-write boundary after module reloads
scope: Install guard spies on current imported module classes and assert stale parent-package attributes cannot redirect guard installation.
requested_paths: core/trade_truth/prospective_capture_engine.py; tests/test_trade_truth_prospective_repair.py
allowed_paths: the two requested paths and this evidence record
forbidden_paths: broker/API calls; order actions; core/execution_engine.py; live/paper authority; credentials; strategy thresholds; merge/push
expected_tests: 44 focused tests; full /opt/anaconda3/bin/pytest -vv -ra run
acceptance_proof: Exact active-class guard blocks before original method; stale class untouched; 44 focused tests and full suite pass; all protected data hashes unchanged.
```

## Files changed and rationale

| File | Change | Why |
|---|---|---|
| `core/trade_truth/prospective_capture_engine.py` | Resolve guarded modules with `importlib.import_module` and use the returned module objects. | Avoid patching stale package attributes after test/runtime module reloads. |
| `tests/test_trade_truth_prospective_repair.py` | Extend `test_broker_write_guards_active` with a stale package-attribute fixture and `finally` cleanup. | Prove the actual caller-visible `ExecutionEngine` class is guarded and no process-global spy leaks. |

## Verification evidence

- Controlled offline reproduction created distinct package-attribute and `sys.modules` module objects. Before the fix, guard installation modified the stale class (`module_a_is_guarded=False`, `module_b_is_guarded=True`); after resolving via `importlib`, the regression test verifies only the current class is intercepted.
- Focused command: `/opt/anaconda3/bin/pytest -q tests/test_trade_truth_prospective_repair.py tests/test_tradebuilder_canonical_observer_integration.py tests/test_torture_replay.py tests/test_four_strategy_dataset_manifest.py::test_real_candle_and_tick_truth_prove_current_field_classification` — **44 passed**, 3 warnings, 19.28s.
- Full command: `/opt/anaconda3/bin/pytest -vv -ra` — **8,482 passed, 9 skipped, 28 deselected**, 1,476 warnings, 827.31s, exit 0. Full log: `output/mros_live_runtime_truth_repair_v1_20260930T1458IST/WHOLE_REPO_REGRESSION_GREEN_20260930.log`.
- The selected tick parquet was hydrated only in this isolated worktree from the existing canonical local copy after its 7,604,505-byte size and SHA-256 `30e6b7372cd521c80831a0da478e2402ce884c20bc00e47d7ea07122473ebda7` matched the 132-byte LFS pointer OID. No network fetch occurred; the canonical checkout file hash remains the same.
- `read_only=true`; `is_order_action=false`; `broker_api_called=false`; `allowed_for_live_execution=false`; `append=false`. No order/broker action was attempted. No new config keys.

## Risks and rollout

This proves the narrow module-identity guard contract in tests. It does not change the existing broad exception handling for absent optional boundary modules and does not establish live behavior. Do not deploy or promote based only on this test result. Rollout remains blocked by incomplete candidate dependency authority, missing authoritative T-1 source-event provenance, and the absence of production verification.

## Agent Work Contract

- `source_agent`: Hermes design record or GSD scoped execution record as declared above.
- `action`: design/contracts/acceptance gates for Hermes; scoped implementation/tests/evidence for GSD.
- `scope`: offline MROS runtime truth and candidate-dependency safety only.
- `requested_paths`: the files explicitly named in this record and its linked implementation.
- `allowed_paths`: associated runtime-truth modules, tests, design notes, and the repair evidence package.
- `forbidden_paths`: credentials, environment files, live runtime data, broker write paths, order actions, and strategy thresholds.
- `expected_tests`: focused feed-health, symbol-safety, recovery, heritage, dependency-registry, or write-guard tests named in the evidence package.
- `acceptance_proof`: deterministic offline tests pass; unsafe or incomplete authority remains blocked.

## Scope Guard

This record covers offline implementation and verification only. It grants no order, broker, paper, live, credential, or strategy authority. Candidate declarations require exact source identity; missing facts remain UNKNOWN/BLOCKED.

## Grill Me Review

The principal risk is overstating synthetic, coarse-domain, or partial evidence as feed authority. The registry and consuming boundary must retain visible block reasons; tests must exercise the actual safety decision.

## Hermes Review

The contract separates candidate identity, required domain, canonical identity, freshness authority, execution scope, and unresolved evidence. A partial or unknown declaration cannot become eligible through caller-provided health alone.

## GSD Review

Execution stays within the declared files. Regression tests cover both accepted safe cases and fail-closed missing/mismatched authority. No live runtime wiring, strategy change, broker call, or order action is part of this work.

## QA / Safety Review

The current-tree whole-repository offline suite passed 8,493 tests (9 skipped, 28 deselected); the focused candidate/feed/symbol/heritage/T-1 suite passed 118 tests. These results prove test behavior only, not production runtime readiness.

## Acceptance Proof

See `output/mros_live_runtime_truth_repair_v1_20260930T1458IST/FINAL_CONTINUATION_VERDICT.md`, `TEST_RESULTS.md`, `MANIFEST.json`, and the adjacent SHA-256 checksum list. The candidate registry has 14 exact IDs, 23 unknown/unverified labels, and zero execution-eligible candidates.

## Runtime Proof Required After Merge

No runtime proof is asserted. Any future runtime validation requires a separately authorized, read-only, non-ordering procedure with exact process, source-event, identity, freshness, and artifact bindings. Live execution remains unauthorized.

## What This PR Does Not Prove

It does not prove complete candidate dependency coverage, T-1 provenance, production throughput, live process continuity, broker behavior, or execution readiness. Missing authority remains a blocker.

## Human Approval

This PR was opened under the user's explicit goal to reach a merge after fixes and green CI. That authorization does not grant live, paper, broker-write, order, or strategy-change authority. Merge remains gated on required CI and repository policy.

## High-Risk Path Review

Changed feed/WebSocket/runtime-safety paths were reviewed for fail-closed behavior. Changes add identity-bound admission/accounting and recovery proof requirements; they do not weaken freshness, risk, kill-switch, or order gates. Focused negative tests cover missing, stale, mismatched, and opaque authority. Production behavior remains unverified.
