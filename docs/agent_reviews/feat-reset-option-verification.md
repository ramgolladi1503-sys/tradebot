# PR Review: Reset Option Verification on Subscription Replay (MOD-5)

- mode: PAPER
- candidate_id: PR-7-reset-option-verification
- decision: ACCEPT
- reason: Fix RC-6 by resetting option verification state on every full subscription replay.
- timestamp: 2026-06-11
- is_order_action: false
- broker_api_called: false
- source: gsd_agent

## What changed?
1. In `core/kite_depth_ws.py`, added `_reset_option_feed_verification(reason=f"resubscribe_full:{reason}")` to `_resubscribe_full`.
2. This ensures that anytime we resubscribe to tokens (including soft resubscribes), the verification state resets from FAILED/OK to PENDING.

## Why does this move safety/stability/readiness forward?
Previously, if option verification failed (timeout), it got stuck in FAILED state. Even if a soft resubscribe succeeded, the feed remained invalid because verification wasn't restarted. By resetting it here, any successful token subscription replay forces a fresh tick verification window, allowing the feed to recover gracefully.

## What did not change?
- No real orders are placed.
- `MANUAL_APPROVAL_REQUIRED` remains 1.
- No live trading is enabled.

## Agent Work Contract
This PR implements MOD-5 from the Feed RCA. 

## Scope Guard
- `core/kite_depth_ws.py`: Logic updated to reset verification state.

## High-Risk Path Review
Verification is an audit mechanism. Resetting it does not bypass the audit; it simply re-triggers the verification window. The feed still must pass the verification to be marked `feed_ok`.

## Grill Me Review
If we don't reset verification on soft resubscribe, the system cannot recover from a transient timeout without a full hard reconnect. This change aligns the soft resubscribe path with the hard connect path regarding verification behavior.

## Hermes Review
Architecture boundaries are preserved. Verification state is internal to the feed.

## GSD Review
I successfully updated `_resubscribe_full` with the single function call.

## QA / Safety Review
* Feed gates remain active.
* It does not fake `feed_ok=True`. It clears the failure and forces it to wait for real ticks again.

## Acceptance Proof
`test_kite_depth_ws_stability.py` passes completely.

## Human Approval
Requires explicit human review before merge, per standard project protocol.
