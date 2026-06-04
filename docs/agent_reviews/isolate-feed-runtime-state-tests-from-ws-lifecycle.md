# Isolate Feed Runtime State Tests From WS Lifecycle

mode: REVIEW
candidate_id: PR-480-ISOLATE-FEED-RUNTIME-STATE-TESTS-FROM-WS-LIFECYCLE
decision: add_test_isolation_only
reason: `tests/test_feed_runtime_states.py` was leaving shared `core.kite_depth_ws` globals dirty, which made later websocket lifecycle tests depend on file order. This PR adds a test-only reset helper and a regression test so feed/runtime state tests no longer pollute WS lifecycle assertions.
timestamp: 2026-06-04T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/isolate-feed-runtime-state-tests-from-ws-lifecycle.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (test isolation only)
title: Isolate Feed Runtime State Tests From WS Lifecycle
scope: reset shared websocket runtime state between feed-runtime-state tests so later restart tests run from a clean WS lifecycle baseline
requested_paths:
  - tests/test_feed_runtime_states.py
  - tests/test_kite_depth_restart.py
  - docs/agent_reviews/isolate-feed-runtime-state-tests-from-ws-lifecycle.md
allowed_paths:
  - tests/test_feed_runtime_states.py
  - tests/test_kite_depth_restart.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/kite_depth_ws.py
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - strategies/*
  - config/*
  - dashboard/*
  - run_live.sh
expected_tests:
  - tests/test_feed_runtime_states.py
  - tests/test_kite_depth_restart.py
  - targeted polluted-order reproduction
  - agent review evidence validator
  - unified CE gates
acceptance_proof:
  - running `tests/test_feed_runtime_states.py` before the selected websocket lifecycle tests no longer changes their outcome
  - the cleanup is test-only and does not alter production websocket behavior
  - WS/reactor lifecycle guards remain intact and fail closed
  - safety flags remain read-only where evidence is involved
```

## Purpose

We need deterministic test isolation between feed/runtime evidence tests and websocket lifecycle tests. The current problem is not production behavior; it is shared test-state pollution in `core.kite_depth_ws` that makes restart assertions order-dependent.

## Files Changed

- `/Users/madhuram/tradebot/tests/test_feed_runtime_states.py`
  - Adds a test-only helper that resets the shared WS/runtime bookkeeping used by the module.
  - Adds a regression test proving the helper clears reconnect-blocked, reactor-terminal, disconnected, feed-timing, and restart bookkeeping.
- `/Users/madhuram/tradebot/tests/test_kite_depth_restart.py`
  - Expands the existing autouse reset so restart tests also begin from a clean WS lifecycle baseline after other test modules.
- `/Users/madhuram/tradebot/docs/agent_reviews/isolate-feed-runtime-state-tests-from-ws-lifecycle.md`
  - Records scope, safety review, and verification expectations.

## High-Risk Path Review

High-risk production paths were not modified.

Review outcome:
- No changes to `core.kite_depth_ws.py`.
- No changes to broker/order/execution/risk/strategy code.
- No runtime websocket behavior change.

Residual risk:
- The cleanup is intentionally test-only. If a future test mutates new shared `core.kite_depth_ws` globals, the fixture may need to be extended.

## Scope Guard

### In Scope

- Reset shared websocket runtime state between test cases.
- Prevent order-dependent leakage from feed/runtime tests into websocket lifecycle tests.
- Add regression coverage for the reset helper.

### Out of Scope

- Production websocket behavior
- Restart logic
- Reactor lifecycle safety
- Broker/order behavior
- Strategy, ranking, and Phase2 behavior

### Boundary Verification

- [x] No broker calls added
- [x] No order actions added
- [x] No strategy behavior changed
- [x] No thresholds changed
- [x] No WS/reactor guard weakened
- [x] No evidence contract changed

## Grill Me Review

### Risks Addressed

- Eliminates test-order pollution between `test_feed_runtime_states.py` and selected WS restart tests.
- Makes the failure mode observable via a direct regression test.

### Verdict

PASS — test isolation only.

## Hermes Review

### Contract / Architecture Check

- [x] Test-only reset helper is explicit and local to the test layer.
- [x] Cleanup covers the shared mutable WS lifecycle state that previous tests left dirty.
- [x] No production runtime state or behavior is altered.

### Verdict

PASS

## GSD Review

### Delivery Check

- [x] Regression test added for the reset helper.
- [x] Polluted-order sequence was re-run and now passes.
- [x] Broader WS/runtime test slice remains green.

### Verdict

PASS

## QA / Safety Review

Non-negotiables reaffirmed:
- No broker/order code touched.
- No live-order behavior changed.
- No feed freshness, reactor, or restart safety gate weakened.
- No strategy, ranking, or Phase2 behavior changed.

Evidence/runtime safety flags:
- Not applicable for this PR; this is test isolation only.

## Acceptance Proof

### Evidence Contract

This PR proves:
- feed/runtime tests no longer leave dirty WS lifecycle globals behind
- websocket lifecycle tests remain deterministic when run after feed/runtime tests
- the reset helper itself is regression-tested

### Commands Run

```bash
PYTHONPATH=. pytest -q tests/test_feed_runtime_states.py tests/test_kite_depth_restart.py::test_on_close_does_not_schedule_restart_when_reactor_blocked tests/test_kite_depth_restart.py::test_reactor_terminal_state_blocks_followup_start_restart_and_schedule -vv
PYTHONPATH=. pytest -q tests/test_feed_runtime_states.py::test_reset_depth_ws_test_state_clears_ws_lifecycle_pollution
PYTHONPATH=. pytest -q tests/test_feed_runtime_states.py tests/test_kite_depth_restart.py tests/test_kite_depth_ws_stability.py
python scripts/validate_agent_review_evidence.py --base-ref origin/main
git diff --check
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file <generated-file>
```

## Runtime Proof Required After Merge

No live runtime proof is required. This is a test-isolation change only.

## What This PR Does Not Prove

- This PR does not change production websocket restart behavior.
- This PR does not change broker/order behavior, strategy logic, ranking, or Phase2.
- This PR does not prove any live-trading improvement.

## Human Approval

This PR is intentionally limited to test isolation and documentation. Human approval is still required before any merge.
