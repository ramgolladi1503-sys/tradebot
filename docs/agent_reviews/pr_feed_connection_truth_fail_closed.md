# Agent Review: Feed Connection Truth Fail Closed Hotfix

mode: offline
candidate_id: PR-FEED-CONNECTION-TRUTH
decision: approve
reason: fix recovery execution race
timestamp: 2026-07-10T22:21:21+00:00
is_order_action: false
broker_api_called: false
source: GSD
## Agent Work Contract

Source Agent: GSD
Action: FIX_DEFECT
Title: Feed Connection Truth Fail Closed Hotfix
Scope: Fix immediate recovery-state execution race by forcing failure in execution gates during recovery states.
Expected Tests: `tests/capability_gap/test_feed_connection_truth_negative_controls.py`
Acceptance Proof: 100% pass on negative control tests and `test_gate_recovery_parity.py`.

## Scope Guard

This PR is strictly limited to fixing the race condition where stale pre-disconnect ticks are erroneously accepted during recovery or terminal failures. No changes are made to broader feed readiness, subscription restoration, or strategy behavior.

## Grill Me Review

Audited the gap in feed truth execution where the `FeedRecoveryCoordinator` is tracking failures, but the execution gates (`market_data_monitor.py` and `feed/gate.py`) only evaluate timestamp freshness. This PR addresses that critical risk.

## Hermes Review

The architecture of the execution gates requires an explicit check against the `FeedRecoveryState`. A shared helper `evaluate_recovery_block` was designed to consolidate this logic without bleeding concerns across components.

## GSD Review

Implemented the recovery state check in both the ML execution gate and the fallback execution gate. Added test isolation in `tests/conftest.py` and test verification in `tests/test_kite_depth_ws_stability.py` and other test files.

## QA / Safety Review

The fix ensures `VALIDATED` failing behavior in unsafe modes:
- `auth_required`
- `terminal_failure`
- `recovery_blocked`
- `recovery_in_progress`
The implementation has the right narrow structure without expanding into unvalidated full feed readiness.

## Acceptance Proof

The `test_gate_recovery_parity.py` parity test proves that both paths evaluate the recovery state identically, and all execution paths fail closed.

## High-Risk Path Review

High-risk paths modified:
- `core/kite_depth_ws.py`
- `core/market_data_monitor.py`
- `core/feed/gate.py`
These files were only modified to ensure that execution fails closed when the connection or feed recovery state is unhealthy. No changes were made to broker APIs, live execution rules, or strategy thresholds.

## Runtime Proof Required After Merge

After merging, we must verify in paper/live environments that WebSocket disconnects correctly halt execution, even if ticks appear fresh.

## What This PR Does Not Prove

This PR does NOT prove:
- subscription restoration proof
- post-reconnect message proof
- connection generation
- pre-disconnect tick invalidation
- explicit authoritative socket connection state
- complete final readiness integration

## Human Approval

Approved pending CI verification of the hotfix.
