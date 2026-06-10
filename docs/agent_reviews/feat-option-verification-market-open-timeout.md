# PR Review: Increase Option Verification Timeout (MOD-6)

- mode: PAPER
- candidate_id: PR-5-option-timeout
- decision: ACCEPT
- reason: Dynamically extend option verification timeout at market open
- timestamp: 2026-06-11
- is_order_action: false
- broker_api_called: false
- source: gsd_agent

## What changed?
1. Added `FEED_OPTION_VERIFY_TIMEOUT_SEC`, `FEED_RESTART_VERIFY_TIMEOUT_SEC`, and `FEED_OPTION_VERIFY_TIMEOUT_MARKET_OPEN_SEC` to `config/config.py` with default values of `45.0` and `90.0` (for market open).
2. Updated `_option_feed_verification_timeout_sec()` in `core/kite_depth_ws.py` to use `45.0` as base, and dynamically check `is_market_open_ist()` to extend the timeout to `90.0` seconds during the first 15 minutes of market open (9:15-9:30).
3. Updated `_restart_verification_timeout_sec()` in `core/kite_depth_ws.py` to use `45.0` seconds.

## Why does this move safety/stability/readiness forward?
At 9:15–9:30 IST market open, Kite's option ticks can have latency. A 15-second verification window was causing the verification to expire before ticks arrived, permanently blocking `feed_ok` and starving Phase2 of candidates. By bumping the timeout to 45 seconds (90 at open), we handle the latency while preserving verification logic.

## What did not change?
- No real orders are placed.
- `feed_ok` logic itself is not bypassed; it just waits longer.
- `MANUAL_APPROVAL_REQUIRED` remains 1.
- No live trading is enabled.

## What tests prove it?
- Existing `test_option_feed_verification_logs_failed_when_ticks_never_arrive` is updated to verify the new longer timeout duration and still ensures `FAILED` state if the timeout completes without ticks.

## What could still fail?
- If Kite has latency > 90 seconds at market open, the verification will still timeout and enter a `FAILED` state.

## Agent Work Contract
This PR implements MOD-6 from the Feed RCA, extending the option verification timeout at market open to account for higher latencies from Kite.

## Scope Guard
- `config/config.py`: Added timeout constants.
- `core/kite_depth_ws.py`: Logic updated to use constants and dynamic timeout.
- `tests/test_kite_depth_ws_stability.py`: Tests updated to assert against the new timeout.

## High-Risk Path Review
The timeout determines when `feed_ok` can transition from blocked to active. By waiting longer, we delay the transition to active, which is a fail-safe behavior. No risk boundaries were relaxed.

## Grill Me Review
The dynamic timeout specifically targets the 9:15-9:30 window when Kite ticks are known to be delayed. The previous 15s timeout was triggering a permanent FAILED state too eagerly.

## Hermes Review
Architecture boundaries are preserved. The logic correctly reads time locally and does not add new coupling to the orchestrator.

## GSD Review
I implemented the timeout extensions correctly using `is_market_open_ist` to dynamically scale up the tolerance for initial tick delays.

## QA / Safety Review
* Feed gates remain active.
* Failsafe behavior is preserved (timeout still eventually forces a failure).

## Acceptance Proof
`test_option_feed_verification_logs_failed_when_ticks_never_arrive` verifies that the `FAILED` state is still reached correctly, just after the new, longer timeout limit.

## Runtime Proof Required After Merge
The production logs must show `FEED_OPTION_VERIFY_OK` at market open rather than `FEED_OPTION_VERIFY_FAILED`.

## What This PR Does Not Prove
It does not prove that Kite's market open tick latency won't eventually exceed 90 seconds.

## Human Approval
Requires explicit human review before merge, per standard project protocol.
