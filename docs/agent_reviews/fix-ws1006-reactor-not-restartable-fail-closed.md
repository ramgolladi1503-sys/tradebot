# Agent Review — Fix WS1006 ReactorNotRestartable Fail Closed

## Agent Work Contract
Fix only the live WS1006 / ReactorNotRestartable recovery storm by failing closed and requiring process restart when the websocket runtime reaches a terminal recovery state.

## Scope Guard
Allowed files: feed websocket lifecycle code and focused tests. No strategy, ranking, Phase2, candidate generation, broker/order, risk threshold, or UI behavior changes.

## High-Risk Path Review
This PR touches `core/kite_depth_ws.py`, a live feed/WebSocket path. The change is intentionally fail-closed: after terminal WS1006-style faults, the runtime marks recovery blocked and suppresses in-process reconnect attempts.

## Grill Me Review
- Does this place orders? No.
- Does this change ranking or strategy? No.
- Does this hide feed failure? No. It exposes `RECOVERY_BLOCKED` and process restart required.
- Does it weaken risk/SLO halt? No.

## Hermes Review
Runtime evidence must include `RECOVERY_BLOCKED`, `reconnect_blocked_reason`, and process-restart-required recovery action.

## GSD Review
The practical live issue was repeated `ReactorNotRestartable` thread storms after WS1006. This PR prevents repeated in-process restarts once the terminal state is detected.

## QA / Safety Review
Focused tests cover on_error/on_close WS1006, restart suppression, start suppression after recovery blocked, and websocket stability behavior.

## Acceptance Proof
Required commands:
- `PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py`
- `PYTHONPATH=. pytest -q tests/test_feed_runtime_states.py tests/test_kite_depth_restart.py`
- `PYTHONPATH=. pytest -q tests/test_kite_depth_ws_stability.py`
- `python scripts/validate_agent_review_evidence.py`
- `git diff --check`

## Runtime Proof Required After Merge
During live verification, WS1006 may occur, but repeated `ReactorNotRestartable` thread storms and repeated factory starts must not continue. Runtime should show `RECOVERY_BLOCKED` / process restart required.

## What This PR Does Not Prove
It does not prove trading edge, candidate quality, ranking quality, Phase2 profitability, or websocket reconnection success. It only proves fail-closed suppression of unsafe in-process restart storms.

## Human Approval
Human approval is required before merge and before any live verification.

## CE Evidence Contract Fields

mode: LIVE_AUDIT_ONLY
candidate_id: ws1006_reactor_fail_closed
decision: FAIL_CLOSED_PROCESS_RESTART_REQUIRED
reason: terminal_ws1006_fault_requires_process_restart
timestamp: 2026-06-03T10:15:10Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/fix-ws1006-reactor-not-restartable-fail-closed.md
