# Agent Work Contract

mode: evidence
candidate_id: blocked
decision: suppress_reconnect_storm
reason: reactor_not_restartable
timestamp: 2026-06-03T00:00:00Z
is_order_action: false
broker_api_called: false
source: core.kite_depth_ws

source_agent: Codex
action: GENERATE_PATCH
title: Fix WebSocket recovery reactor-not-restartable thread storm
scope: Suppress repeat restart scheduling when the depth websocket recovery state is already blocked by `reactor_not_restartable`.
requested_paths:
- core/kite_depth_ws.py
- tests/test_kite_depth_restart.py
- docs/agent_reviews/fix-ws-recovery-reactor-not-restartable-thread-storm.md
allowed_paths:
- core/kite_depth_ws.py
- tests/test_kite_depth_restart.py
- docs/agent_reviews/fix-ws-recovery-reactor-not-restartable-thread-storm.md
forbidden_paths:
- core/broker*
- core/order*
- strategies/
- config/
- runtime/
- logs/
expected_tests:
- PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py -k "reactor or reconnect or restart or close or error"
- PYTHONPATH=. pytest -q tests/test_feed_runtime_states.py tests/test_kite_depth_restart.py
- python scripts/validate_agent_review_evidence.py
- git diff --check
acceptance_proof: Suppression paths emit `RECOVERY_BLOCKED` snapshots, no restart thread is created after the block is set, and the live reconnect loop remains fail-closed.

## Scope Guard

- Evidence-only recovery suppression for websocket restart storms.
- No broker calls.
- No order actions.
- No strategy changes.
- No ranking or Phase2 changes.
- No threshold changes.

## Grill Me Review

### Risks

- A blocked recovery path could still schedule another restart thread.
- A blocked snapshot could omit the blocked reason or recovery action.
- A suppression helper could accidentally clear the blocked state during normal operation.

### Findings

- `_schedule_restart_depth_ws` returns early when recovery is blocked.
- `restart_depth_ws` and `start_depth_ws` both persist a blocked snapshot with the blocked reason and recovery action.
- The blocked state remains sticky until a fresh process start or an explicit reset path.

### Verdict

PASS — restart suppression is explicit and fail-closed.

## Hermes Review

### Contract / Architecture Check

- [x] Recovery-blocked state is explicit.
- [x] Snapshot fields are structured and versioned by the existing feed runtime schema.
- [x] The same blocked reason is surfaced in logs and persisted runtime state.
- [x] The fix is localized to websocket recovery control flow.

### Boundary Check

- [x] No broker adapter touched.
- [x] No execution engine touched.
- [x] No strategy logic touched.
- [x] No UI touched.

## GSD Review

### Implementation Summary

- Added a shared recovery-blocked suppression helper.
- Guarded restart scheduling before background thread creation.
- Guarded the internal reconnect callback paths before scheduling.
- Added deterministic tests for blocked restart suppression and blocked snapshot fields.

### Test Coverage

- `test_schedule_restart_depth_ws_suppresses_when_reactor_blocked`
- `test_on_error_does_not_schedule_restart_when_reactor_blocked`
- `test_on_close_does_not_schedule_restart_when_reactor_blocked`
- `test_recovery_blocked_snapshot_contains_process_restart_required`

## QA / Safety Review

- [x] No order actions introduced.
- [x] No live orders enabled.
- [x] No broker API calls introduced.
- [x] Failure remains closed when recovery is blocked.
- [x] No candidate counts are faked.

## High-Risk Path Review

- `core/kite_depth_ws.py` is the only high-risk runtime path changed.
- The change only suppresses repeat recovery scheduling after `reactor_not_restartable` is already recorded.
- The fix does not change broker access, order actions, feed freshness thresholds, or strategy selection.
- The runtime state remains fail-closed with `RECOVERY_BLOCKED` when the blocked reason is set.

## Acceptance Proof

- `FEED_RECONNECT_SUPPRESSED_RECOVERY_BLOCKED` is emitted with the blocked reason and `process_restart_required`.
- Snapshot fields include `ws_connected=false`, `runtime_state=RECOVERY_BLOCKED`, `last_error`, `reconnect_blocked_reason`, `recovery_action`, `ws_reconnect_allowed=false`, `ws_reconnect_attempted=false`, and `restart_suppressed=true`.
- Reactor-not-restartable detection is explicitly flagged.

## Runtime Proof Required After Merge

- Fresh live verification must confirm the reconnect loop stays suppressed after `reactor_not_restartable` is observed.
- A live session must show the blocked snapshot and no repeated restart scheduling.

## What This PR Does Not Prove

- It does not prove the underlying websocket disconnect is eliminated.
- It does not prove market data recovery is healthy.
- It does not prove any trading edge.
- It does not alter strategy selection, ranking, or Phase2 behavior.

## Human Approval

- This change is approved for a narrow recovery-suppression fix and evidence-only runtime reporting.


## Agent Work Contract

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
