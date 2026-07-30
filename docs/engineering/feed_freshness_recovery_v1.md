# Feed Freshness Recovery V1

This repair addresses a false terminal latch in feed recovery. The validated LIVE startup proved complete callback-applied subscription and MODE_FULL truth for the current 73-token inventory, followed by continued tick flow. The failure was not the six historical zero-tick contracts; those tokens were not requested in this inventory and are classified as `SUBSCRIBE_NOT_REQUESTED`.

The repaired runtime separates physical transport truth from execution readiness:

- `transport_socket_connected` records physical WebSocket connection state.
- `subscription_truth_complete` and `mode_full_truth_complete` record callback-applied registry truth.
- `critical_feed_fresh`, `core_feed_fresh_ratio`, and `depth_feed_fresh_ratio` record market-data freshness.
- `execution_feed_ready` remains fail-closed unless transport, registry truth, and required freshness all pass.
- `canonical_feed_state` can represent `DEGRADED_LOCAL` and `VERIFYING_RECOVERY` without falsely forcing `ws_connected=false`.

`partial_activity_detected` no longer sets `reconnect_blocked_reason=partial_recovery`. It enters bounded local verification and returns to `LIVE` only after stable cycles pass. Terminal `RECOVERY_BLOCKED` remains available for genuinely unrecoverable states such as reactor failure, WS1006 process-restart-required, authentication failure, or exhausted recovery.

Runtime defaults:

- `TOKEN_RECOVERY_MAX_ATTEMPTS=3`
- `TOKEN_RECOVERY_COOLDOWN_SEC=10`
- `TOKEN_RECOVERY_VERIFY_TIMEOUT_SEC=15`
- `RECOVERY_STABLE_CYCLES=3`
- `CORE_FEED_FRESH_QUORUM=0.95`

Safety boundary: this change does not alter strategy thresholds, order placement, broker credentials, or automatic execution. Candidate-local freshness gates remain authoritative.
