# False Latch Trigger Analysis

The false terminal transition was in `core/kite_depth_ws.py::_maybe_trigger_silent_reconnect`.

Before repair, the predicate was:

```text
action.reason == partial_activity_detected
```

That branch called `_set_reconnect_blocked_reason("partial_recovery")`. `_set_reconnect_blocked_reason` mapped non-WS1006 and non-reactor reasons to `_RUNTIME_STATE="RECOVERY_BLOCKED"`. Snapshot normalization then treated any reconnect-blocked reason as terminal, rewrote the runtime state to `RECOVERY_BLOCKED`, and forced `ws_connected=false`.

The captured startup showed this was not a genuine terminal transport failure:

- Subscribe callback-applied count: `73`
- MODE_FULL callback-applied count: `73`
- Unique persisted tick tokens: `73`
- Unique persisted depth tokens: `70`
- Tick callbacks continued after the latch

The stale set was ordinary partial activity, not proof that the physical socket was dead or that the reactor was unrecoverable. The six historically named tokens were not stale subscribed tokens in this run; they were `SUBSCRIBE_NOT_REQUESTED`.

Repair:

- `partial_activity_detected` now enters `DEGRADED_LOCAL` or `VERIFYING_RECOVERY`.
- It emits a recovery verification object with transport, registry, critical freshness, core quorum, and stable-cycle evidence.
- It does not set `_RECONNECT_BLOCKED_REASON`.
- It does not request a process restart.
- It returns to `LIVE` only after the configured stable-cycle requirement passes.

Terminal `RECOVERY_BLOCKED` remains reserved for unrecoverable paths such as reactor-not-restartable, WS1006 process-restart-required, authentication blocks, or explicit recovery exhaustion.
