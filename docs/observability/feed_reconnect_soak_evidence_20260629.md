# Feed Reconnect Soak Evidence (2026-06-29)

## Context
Following the RCA on the `1006` Kite connection error crashing the tradebot, we improved the WebSocket event handlers to utilize Kite's native `auto_reconnect`, implemented stricter feed truth gating, and added deep orchestrator `feed_ok` safeguards.

## Soak Criteria
The system must gracefully handle the following transitions without crashing the Twisted reactor, and correctly surface health constraints up to the candidate generator:
1. `LIVE_FRESH` (normal operation).
2. Broker socket drop (`1006`).
3. Internal transition to `RECONNECTING`.
4. Successful connection establishment (`on_reconnect` -> `ws_reconnect_success`).
5. Complete resubscription of the active token list.
6. Arrival of fresh ticks restoring the feed to `LIVE_FRESH`.

## Evidence (Live Read-Only Soak)

### Out-of-Hours (Stale Blocking Proof)
Running a live soak out of market hours perfectly confirmed the primary safeguard:
```
feed_unhealthy_prebuild_skip symbol=NIFTY execution_mode=LIVE reasons=feed_stale:FEED_RUNTIME_NOT_OK
PHASE2: No input candidates for phase2 raw_count=0
```
This behavior confirms that when the feed receives no active ticks, the system identifies the feed as stale and halts candidate processing entirely.

### Test Coverage Proof
`tests/test_feed_reconnect_safety.py` was executed and tests the following invariants:
1. `test_kite_1006_close_does_not_terminate_orchestrator`: Confirms a `1006` error defers to native reconnects and no longer forces an uncontrollable `restart_depth_ws`.
2. `test_manual_twisted_restart_not_attempted_after_1006`: Confirms `on_error` avoids manual restarts.
3. `test_native_reconnect_changes_state_to_reconnecting`: Simulates a reconnect success and confirms `RUNTIME_STATE` resolves back to `RUNNING`.
4. `test_on_reconnect_resubscribes_all_tokens`: Asserts that `KiteTicker.subscribe` is fully invoked upon reconnection.
5. `test_connected_but_no_ticks_becomes_stale`: Confirms the watchdog overrides the state to `STALE` if `ws_tick_age_sec` exceeds limits, even if the socket remains connected.
6. `test_feed_ok_false_when_option_ticks_are_stale`: Confirms the `FeedTruthContract` explicitly returns `entries_allowed=False` under stale ticks.
7. `test_fallback_recovered_quote_never_becomes_execution_ok_true`: Confirms the orchestrator builder correctly skips execution pathways on compromised data.
8. `test_all_candidate_generation_paths_respect_feed_ok_false`: Explicitly verifies that phase 2 and trade builder loops are entirely locked when `feed_ok=False`.

All tests pass.

### Market-Hours Observation Plan
The final verification requires observing the bot during active market hours to witness a true sequence of:
`LIVE_FRESH -> simulated/drop/actual 1006 -> RECONNECTING -> resubscribe -> fresh ticks -> LIVE_FRESH`

**Current Classification**: `PARTIAL_FIX_SAFE_DEGRADE_PROVEN_RECONNECT_RECOVERY_UNPROVEN`
(Will be upgraded once market-hours simulation logs are acquired.)
