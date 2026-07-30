# Live Validation Plan

Do not start the final 60-minute repaired soak without explicit operator approval.

Next approved live validation should use the guarded launcher only:

```bash
RUN_ID="feed_freshness_repaired_$(date -u +%Y%m%dT%H%M%SZ)" \
  bash scripts/run_feed_freshness_instrumented_live.sh 2>&1 | tee "runtime/live_observation/${RUN_ID}.log"
```

Acceptance gates after startup warm-up:

- process alive
- runtime mode `LIVE`
- automatic execution disabled
- manual approval preserved
- physical transport connected
- subscribe callback-applied truth complete for the current desired inventory
- MODE_FULL callback-applied truth complete for the current desired inventory
- `partial_activity_detected` does not emit terminal `RECOVERY_BLOCKED`
- `transport_socket_connected` remains physical transport truth
- `execution_feed_ready` remains false when critical or candidate-local freshness is not proven
- three stable verification cycles can return the canonical state to `LIVE`

Reject the soak if any broker order placement, modification, cancellation, or automatic execution path is invoked.
