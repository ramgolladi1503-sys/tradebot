# Feed Reconnect and Safe Degradation Review

## Agent Work Contract
Implemented safe-degradation of feed health and wired native Kite reconnect.

## Scope Guard
No live orders are placed. No risk gates disabled.

## Grill Me Review
Verified that feed degraded state explicitly blocks candidate generation.

## Hermes Review
Architecture uses standard Kite on_reconnect callback rather than manual Twisted restarts.

## GSD Review
Patch implemented according to plan. Tests created and passing.

## High-Risk Path Review
Modified `core/kite_depth_ws.py` (high risk). Ensure no execution logic changed.
Native reconnect delegated, manual twisted restarts suppressed.

## QA / Safety Review
Verified stale feed correctly translates to `entries_allowed=False`.

## Acceptance Proof
All offline/local tests pass. `test_feed_reconnect_safety.py` added.

## Runtime Proof Required After Merge
A separate market-hours evidence task will prove:
LIVE_FRESH -> 1006/drop -> RECONNECTING -> on_reconnect -> resubscribe -> fresh ticks -> LIVE_FRESH

## What This PR Does Not Prove
Does not prove full reconnect recovery in a live market environment.
Does not claim feed is fully stable.

## Human Approval
Approved as a safety patch by user.

## Evidence Auditor Fields
mode: LIVE
candidate_id: N/A
decision: safe-degradation implemented
reason: prevent bot crash on WS drop
timestamp: 2026-06-29T11:00:00+05:30
is_order_action: false
broker_api_called: false
source: agent
