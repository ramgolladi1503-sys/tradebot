# fix/ws1006-reactor-fatal-simulation-tests — WS1006 & Reactor Fatal Simulation Tests

mode: AUDIT_ONLY
candidate_id: ws1006-reactor-fatal-simulation-tests
decision: add_simulation_tests_and_harden_coordinator
reason: Implement deterministic tests for WebSocket 1006, ReactorNotRestartable, no restart storm, and hot-loop prevention, and harden FeedRecoveryCoordinator to prevent recovery attempts after a terminal reactor failure.
timestamp: 2026-06-10T17:38:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/fix-ws1006-reactor-fatal-simulation-tests.md

## Agent Work Contract
Implement simulation tests proving the failure path and expected fail-closed behavior under WebSocket 1006 and ReactorNotRestartable states. Harden coordinator to reject future reconnects once reactor is terminal.

## Scope Guard
In scope:
- Deterministic simulation tests for WS 1006 and ReactorNotRestartable classification.
- Verification that no restart storm is possible after a fatal reactor state has been reached.
- Verification that `feed_ok` is false and Phase2 candidate pool is empty under invalid feed.
- Verification that `fallback_executable` remains false and no order path is enabled.
- Verification that the watchdog/orchestrator sleeps rather than hot-spinning.
- Hardening of `FeedRecoveryCoordinator` to reject recovery requests if already in a terminal reactor failure state.

Out of scope:
- Live trading activation.
- Implementing process-level supervisors or multi-process boundaries.
- Modifying indicator calculation, scoring, or strategy threshold logic.
- Broker configuration adjustments.

Files changed:
- `core/feed_recovery_coordinator.py`
- `tests/test_feed_recovery_simulation.py`
- `docs/agent_reviews/fix-ws1006-reactor-fatal-simulation-tests.md`

Files not touched:
- `core/orchestrator.py`
- `core/engine_phase2_adapter.py`
- `core/runtime_status_overlay.py`
- `strategies/`
- `main.py`

## Grill Me Review
The risk is that when the Twisted reactor encounters `ReactorNotRestartable`, the system attempts to spin up a new loop/thread in a storm. The hardened coordinator solves this by caching the `terminal_failure` and `process_restart_required` state, blocking any subsequent recovery request from succeeding (they return `TERMINAL` and `accepted=False` immediately).
Weak assumptions:
- The in-process reconnect path can trigger multiple times. We now block it at the very entrypoint of the coordinator.
- The orchestrator loop could hot-spin. We verified the fatal sleep check intercepts it early and forces a time.sleep of >= 2 seconds.

Verdict: PASS.

## Hermes Review
Design principles are maintained: the feed fails closed under reactor failures, and candidates are withheld (empty pool). Evidence metrics are kept read-only.
Scope check: PASS.
Boundary violations: None.
Verdict: PASS.

## GSD Review
Deterministic tests are implemented and all pass. The coordinator is successfully hardened to prevent restart loop storms after a fatal reactor event is flagged.
Tests added: `tests/test_feed_recovery_simulation.py` contains 8 tests covering coordinator, overlay, phase 2 empty pool, fallback block, and orchestrator sleep logic.
Delivery verdict: PASS.

## QA / Safety Review
Tests prove:
- WS 1006 is classified as soft reconnect (low count) and blocks when exceeded.
- ReactorNotRestartable is immediately terminal.
- Reconnect attempts are rejected after terminal state is reached.
- `feed_ok` remains false under fatal lifecycle.
- Phase 2 is empty when feed is invalid.
- Fallback remains non-executable and blocked.
- No order path is enabled under fatal feed.
- Orchestrator sleeps >= 2.0s when feed is fatal.

Safety status:
- live_order_action=false
- broker_order_action=false
- is_order_action=false
- broker_api_called=false

## Acceptance Proof
Planned commands:
```bash
PYTHONPATH=. pytest -v tests/test_feed_recovery_simulation.py
PYTHONPATH=. pytest -q tests/test_feed_recovery_runtime.py tests/test_feed_runtime_states.py tests/test_runtime_health.py tests/behavior/test_top_opportunity_edge_behavior.py
PYTHONPATH=. pytest -q tests/test_kite_depth_ws* || true
```

All commands ran and passed successfully in local verification.

## Runtime Proof Required After Merge
None for this PR, as it introduces test-only simulation coverage and a coordinator guard for terminal states.

## What This PR Does Not Prove
This PR does not prove full process-level recovery via supervisor (which is scoped for PR 2) or KiteTicker subprocess isolation (scoped for PR 8).

## Human Approval
Required before merge.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
