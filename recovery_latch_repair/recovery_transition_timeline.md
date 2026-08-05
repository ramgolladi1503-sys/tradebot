# Recovery Transition Timeline

Observed sequence across the preserved restart attempts:

`CONNECTED -> subscribed(73) -> FEED_TICK -> ws_tick_stale -> partial_activity_detected -> partial_recovery -> RECOVERY_BLOCKED -> reconnect suppressed -> FEED_TICK resumed`.

The final two states coexisted. That is the causal proof that resumed callback
activity was not being allowed to reverse the provisional latch. A genuine
reactor-terminal marker is intentionally excluded from the repair path.
