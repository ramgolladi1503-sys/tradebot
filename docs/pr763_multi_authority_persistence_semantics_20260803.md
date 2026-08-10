# PR #763 Multi-Authority Persistence Semantics

## Canonical truth

The Kite callback remains authoritative for bounded parsing, token and
timestamp normalization, feed freshness state, latest tick/depth caches, and
observation packet state. These values are updated in memory before any
durable write is attempted.

## Durable truth

Tick rows, depth/trade rows, runtime snapshots, and campaign evidence are
eventual durable truth. They must be written by their existing worker or an
explicit bounded worker queue. The callback must not wait for SQLite or file
completion, and persistence degradation must remain distinct from feed truth.

## Cutover inventory

`CALLBACK_PERSISTENCE_CUTOVER_SET`

| ID | Edge | Authority | Disposition | Replacement |
| --- | --- | --- | --- | --- |
| TICK-01 | `tick_store.insert_tick` durable row | market ticks | `MOVE_TO_EXISTING_WORKER` | existing tick-store FIFO worker |
| TICK-02 | `tick_store.get_max_tick_epoch` SQLite read | market ticks | `REPLACE_WITH_IN_MEMORY_READ` | monotonic in-memory tick maximum |
| DEPTH-01 | `trade_store.insert_depth_snapshot` | depth | `MOVE_TO_EXISTING_WORKER` | bounded depth persistence worker/queue |
| RUNTIME-01 | `runtime_store.write_runtime_snapshot` | runtime state | `MOVE_TO_EXISTING_WORKER` | preloaded in-memory runtime snapshot plus worker |
| CONTROL-01 | observation registry file reads | control plane | `PRELOAD_BEFORE_CONNECTION` | immutable in-memory registry snapshot |
| CONTROL-02 | runtime-state file reads | control plane | `PRELOAD_BEFORE_CONNECTION` | atomic in-memory state snapshot |
| EVENT-01 | `events.write_json_atomic` from callback-reachable runtime state | campaign/runtime evidence | `MOVE_TO_EXISTING_WORKER` | bounded runtime persistence worker |

The callback persistence authorities in this inventory have explicit worker
ownership or in-memory replacement. The cutover is proven offline only for
the focused tests listed in the implementation report; it is not a live
acceptance claim.

## Read-after-write

Immediate consumers use the in-memory tick/depth/runtime snapshots. SQLite is
used for restart recovery and durable audit, never as a callback-time barrier.
Persistence lag is observable through worker counters and does not grant
execution authority.
