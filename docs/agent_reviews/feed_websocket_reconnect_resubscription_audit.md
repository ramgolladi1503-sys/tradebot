# Feed Websocket Reconnect and Resubscription Audit

## Date
2026-07-14

## Summary
This audit reviews the implementation of websocket feed robustness mechanisms, explicitly covering disconnects, reconnect concurrency, resubscription, tick freshness validation, and the corrected out-of-order payload tracking.

## Verified History and Regressions

We explicitly retract the previous incorrect claim that the three persistence failures were inherited.

Starting commit:
501e4ca0714a5432f001f11a2da51ba7155b0242

Previous failing Antigravity tip:
f6995787e8170bb8c26714513aaebd6438a0031c

Corrected tip:
ec79fad47143003b49c7a604c0555ab97f21798f

At starting commit 501e4ca:
the three persistence tests passed

At f6995787:
combined result was 3 failed, 87 passed

At ec79fad4:
full required combined result was 90 passed

The three regressions fixed in the corrected tip were:
test_pressure_profile_records_real_async_persistence_and_shutdown_drain
test_pressure_accounting_reports_max_pending_writes_and_batch_size
test_pressure_hook_context_includes_batch_size

## Exact Root Cause
_LAST_MSG_TS_BY_TOKEN was incorrectly used for both:
1. local receipt/freshness tracking
2. provider payload out-of-order rejection

Deterministic replay payload timestamps were older than local receipt times, so valid replay ticks were incorrectly rejected.

## Correction
_LAST_PAYLOAD_TS_BY_TOKEN now stores provider payload high-water timestamps used only for duplicate/out-of-order rejection.

_LAST_MSG_TS_BY_TOKEN remains local receipt/freshness state.

Replay runs clear websocket tracking state at the beginning of each isolated _run_once execution because each replay profile represents a fresh simulated websocket session.

## Verified Behavior
older provider event:
rejected without mutating newer token state

exact duplicate:
rejected according to the deterministic duplicate policy

valid provider event behind local receipt time:
accepted when newer than the prior provider payload timestamp

rejected-only payload:
does not advance _LAST_WS_TICK_EPOCH

mixed payload:
accepts valid events and rejects stale events independently

## Final Verdicts
WEBSOCKET_DISCONNECT_HANDLED
WEBSOCKET_RECONNECT_SINGLE_OWNER_PASS
WEBSOCKET_RESUBSCRIPTION_COMPLETE_PASS
POST_RECONNECT_FRESHNESS_PASS
POST_RECONNECT_PARTIAL_RECOVERY_BLOCKED
OUT_OF_ORDER_TICK_REJECTION
20_CYCLE_RECONNECT_LOGIC_SIMULATION_PASS
RECONNECT_RESOURCE_PROOF_INCONCLUSIVE

## Open Items
live-provider reconnect proof remains open
full-session live soak remains open
provider completeness remains open
ranking freshness remains separate
execution freshness remains separate
overall production readiness is not proven


## Agent Work Contract

N/A

## Scope Guard

N/A

## Grill Me Review

N/A

## Hermes Review

N/A

## GSD Review

N/A

## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

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
