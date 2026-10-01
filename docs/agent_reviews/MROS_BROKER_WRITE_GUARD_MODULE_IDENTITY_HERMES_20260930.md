# Broker Write Guard Module Identity — Hermes Stage 1

**Date:** 2026-09-30
**Source agent:** `hermes`
**Allowed actions:** `DESIGN_ARCHITECTURE`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`, `UPDATE_DOCS`
**Status:** Scoped offline repair contract; no broker or order authority.

## Source-agent task contract

```text
source_agent: hermes
action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS
title: Bind broker write guards to the module object callers actually import
scope: Prevent stale parent-package attributes from causing guard installation on a different ExecutionEngine class than the one in sys.modules.
requested_paths: core/trade_truth/prospective_capture_engine.py; tests/test_trade_truth_prospective_repair.py
allowed_paths: core/trade_truth/prospective_capture_engine.py; tests/test_trade_truth_prospective_repair.py; this design/verification evidence
forbidden_paths: core/execution_engine.py; core/broker/**; core/order/**; credentials; environment files; live runtime; broker APIs; order actions; strategy thresholds
expected_tests: Reproduce stale core.execution_engine package attribute; verify the active sys.modules class receives the security spy; verify one observed blocked call and restoration; run the full offline suite.
acceptance_proof: The current imported class raises the security exception before the original broker-write method runs; CALL_COUNTS increments once; stale class remains untouched; no broker or order call occurs; focused and full suites pass.
```

## Forensic basis

The completed whole-repository run had one aggregate-only failure in `test_broker_write_guards_active`: the test received a `TypeError` from the original keyword-only broker-writing call, indicating that the guard spy had been attached to a different class object. A controlled offline reproduction created two module objects for `core.execution_engine`, left the parent package attribute pointing to the stale object, and restored the active module object in `sys.modules`. The old installer patched the stale class while callers resolved the active class.

## Contract and design

- Resolve `core.execution_engine`, `core.broker.mock_broker`, and `core.kite_client` through `importlib.import_module` and install guards on the class object returned by that import.
- Preserve existing guard functions, counters, exception text, reset semantics, and candidate/read-only behavior.
- The spy must raise before the original write method is entered. This is test instrumentation; it does not authorize, simulate, or call a broker.
- A stale parent-package attribute must not receive the guard or determine which class is protected.
- Preserve the current exception handling around unavailable optional boundary imports; this repair does not claim to solve absent-boundary policy.

## Acceptance gates

1. Test with `core.execution_engine` package attribute deliberately bound to a different stale class while `sys.modules` contains the active module.
2. Assert a call through the active class reaches the guard and raises `RuntimeError("SECURITY BREACH: ...")` before the original keyword-only method.
3. Assert exactly one execution-engine boundary count and no change to the stale class.
4. Reset guards in `finally`; verify no spy leaks beyond the test.
5. Run focused guard/observer/torture/data tests, then the full offline repository suite.
6. Preserve `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, and `append=false`.

## Risks and limits

This fix addresses module-object identity only. Existing broad exception handling for unavailable boundary imports remains and must not be reported as a general fail-closed import guarantee. The full suite and synthetic tests provide offline code evidence, not production behavior or live readiness.

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
