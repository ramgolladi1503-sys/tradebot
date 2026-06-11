---
mode: LIVE
candidate_id: PR-556
decision: APPROVE
reason: fix_feed_reconnect_safety
timestamp: 2026-06-11T12:00:00Z
is_order_action: false
broker_api_called: false
source: AGENT_REVIEW
---

# PR #556 Feed Reconnect Logic Evidence

## Agent Work Contract
This PR implements the feed connection and websocket rewiring changes that were initially discussed but kept out of PR #555 to maintain its narrow lifecycle scope. These changes directly prevent `ReactorNotRestartable` crashes during live market disconnects.

## High-Risk Path Review
The files modified (`config.py`, `auth.py`, `kite_depth_ws.py`) are highly sensitive. We ensure safety by disabling internal `KiteTicker` reconnects and enforcing full subprocess isolation for the depth websocket. No order placement or risk gates were modified.

## Scope Guard
### Allowed Paths
- `config/config.py`
- `core/auth.py`
- `core/kite_depth_ws.py`
- `docs/agent_reviews/feed-reconnect-pr556.md`

### Forbidden Paths
- `core/orchestrator.py`
- strategy or ranking logic
- execution/order routing

## Grill Me Review
Is it safe to disable internal reconnects? Yes. Relying on Twisted's internal reconnects across threads caused the `ReactorNotRestartable` crashes. By relying on the orchestrator to fully restart the `KiteTicker` subprocess, we guarantee clean slate recovery.

## Hermes Review
Architectural decision is correct. Enforcing `DEPTH_WS_USE_SUBPROCESS=True` and completely bypassing `_soft_resubscribe_current` in favor of full subprocess tear downs aligns with the design philosophy. 

## GSD Review
Changes were carefully implemented. Removed the auto-reconnect flag in `auth.py`, set configuration toggles in `config.py`, and forced `FEED_LIFECYCLE_FATAL` restart in `kite_depth_ws.py` for WS 1006 disconnects.

## QA / Safety Review
- **Safety check**: Does this change broker order placement? No.
- **Safety check**: Does this weaken risk gates? No.
- **Safety check**: Does this touch ranking/UI? No.
No functional trading logic was modified.

## Acceptance Proof
1. `test_kite_depth_restart.py` unit tests pass.
2. `test_kite_auth_consistency.py` unit tests pass.

## Runtime Proof Required After Merge
A live run with a forced 1006 disconnection must show the feed subprocess terminating and automatically restarting cleanly via the orchestrator.

## What This PR Does Not Prove
This PR does not prove that all fake signals logic is resolved. It solely resolves the feed feed drop recovery crashes.

## Human Approval
Approved explicitly by user via chat to create a new PR for these changes.
