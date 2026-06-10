# PR Review: Watchdog Monitoring Mode (MOD-8)

- mode: PAPER
- candidate_id: PR-6-watchdog-monitoring
- decision: ACCEPT
- reason: Prevent watchdog thread from exiting on FEED_LIFECYCLE_FATAL
- timestamp: 2026-06-11
- is_order_action: false
- broker_api_called: false
- source: gsd_agent

## What changed?
1. In `core/kite_depth_ws.py`, updated the `_watchdog` loop to prevent breaking out when `_reconnect_recovery_blocked_active()` is True.
2. The watchdog now enters a monitoring sub-loop `while not (_WATCHDOG_STOP is None or _WATCHDOG_STOP.is_set()):` when the feed state is blocked, emitting `watchdog:monitoring_fatal` snapshots and sleeping for 5 seconds.
3. If the blocked state ever clears, it continues the main watchdog loop.

## Why does this move safety/stability/readiness forward?
When a fatal event occurred (e.g., ReactorNotRestartable), the watchdog was previously exiting permanently. This meant it completely stopped monitoring the feed and stopped emitting status files. By keeping the watchdog alive in a monitoring state, we ensure that the system continues to output metrics and respects any future recovery that might clear the blocked state.

## What did not change?
- No real orders are placed.
- `MANUAL_APPROVAL_REQUIRED` remains 1.
- No live trading is enabled.

## Agent Work Contract
This PR implements MOD-8 from the Feed RCA, preventing the watchdog thread from dying when recovery is blocked.

## Scope Guard
- `core/kite_depth_ws.py`: Logic updated to enter monitoring sub-loop instead of `break`.

## High-Risk Path Review
The watchdog thread runs parallel to the twisted reactor. By not exiting the loop, it continues to call `_emit_reconnect_recovery_blocked_snapshot`. It does not attempt any new executions, broker calls, or unapproved restarts. 

## Grill Me Review
If the watchdog exits, the orchestrator loses the ability to see updated snapshots. Keeping it alive in a 5s-sleep loop is a much safer pattern. It also allows the system to recover seamlessly if another process supervisor resets the blocked flag.

## Hermes Review
Architecture boundaries are preserved.

## GSD Review
I replaced the `break` calls with a monitoring sub-loop correctly.

## QA / Safety Review
* Feed gates remain active.
* Watchdog still respects `_WATCHDOG_STOP`.

## Acceptance Proof
`test_kite_depth_ws_stability.py` passes completely.

## Runtime Proof Required After Merge
The production logs must show `watchdog:monitoring_fatal` emitted repeatedly if the system encounters a FATAL state.

## What This PR Does Not Prove
It does not prove that the process will automatically restart. That requires a supervisor script (MOD-10).

## Human Approval
Requires explicit human review before merge, per standard project protocol.
