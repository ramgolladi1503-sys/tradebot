# Code Ownership Table

| File | Function | Line Range | Responsibility | Observed Behaviour |
|---|---|---:|---|---|
| `core/kite_depth_ws.py` | `_set_reconnect_blocked_reason` | 1580-1596 | Latches reconnect-blocked runtime state and records the blocking reason. | Sets `partial_recovery` / fatal restart reasons and moves runtime into `RECOVERY_BLOCKED` or `FEED_LIFECYCLE_FATAL`. |
| `core/kite_depth_ws.py` | `_clear_reconnect_blocked_reason` | 1773-1778 | Clears the reconnect latch and related suppression flags. | Only clears when an explicit recovery-clear path runs. |
| `core/kite_depth_ws.py` | `_apply_subscription_delta` | 1917-1991 | Applies subscribe/unsubscribe deltas and tracks queued versus applied mutations. | Queued mutations are not marked applied; pending tokens are retained until application. |
| `core/kite_depth_ws.py` | `_normalize_recovery_blocked_snapshot_state` | 1994-2018 | Canonicalizes snapshot state when a reconnect block exists. | Forces `RECOVERY_BLOCKED` and `ws_connected=false` once a block reason is present. |
| `core/kite_depth_ws.py` | `_tick_feed_restart_verification` | 2657-2772 | Verifies restart recovery and clears the reconnect latch when proof succeeds. | Clears the block only after restart verification passes. |
| `core/kite_depth_ws.py` | `_option_runtime_state` | 2918-3036 | Computes subscribed counts, tick freshness, and per-symbol blockers. | Reports `NO_LIVE_OPTION_FEED` when option age exceeds SLA or blocker registry says so. |
| `core/kite_depth_ws.py` | `_maybe_trigger_silent_reconnect` | 4585-4625 | Converts partial activity into reconnect blocking and decides whether to clear it. | Sets `partial_recovery` on partial activity and only clears it when `stale_tokens == 0`. |
| `core/feed/runtime_store.py` | `canonicalize_feed_runtime_snapshot_truth` | 1-260 | Produces canonical feed runtime truth from raw snapshot data. | Downstream truth stays dead if the snapshot carries a reconnect block reason. |
| `core/feed_truth_state.py` | `classify_feed_truth_state` | 95-260 | Classifies feed truth as LIVE, DEAD, DEGRADED, etc. | Treats `ws_connected=False` as DEAD before freshness recovery can be considered. |
| `core/feed_health_truth.py` | `classify_feed_health_truth` | 188-260 | Reconciles websocket, runtime, and per-symbol health into feed truth. | Marks the feed unhealthy when websocket/runtime state is unsafe or symbols remain blocked. |
| `core/feed/ws_mutation_queue.py` | `safe_subscribe_full_mode_observed` | 178-346 | Performs generation-gated subscribe/full-mode mutation and emits requested, queued, applied, failed, and old-generation events. | Reactor-scheduled work remains queued at return; stale callbacks cannot invoke the socket or mutate the applied registry callback. |
| `core/kite_depth_ws.py` | `start_depth_ws` callback wiring | 5532-6760 | Owns socket generation and runtime callback wiring. | Starts a monotonically increasing generation, rejects old connect/reconnect/error/close/tick callbacks, and emits a registry snapshot after connect replay. |
