# Overall status aggregation matrix

| Required subsystem state | Overall |
|---|---|
| All ten explicitly HEALTHY | HEALTHY |
| Required state absent or unknown | UNKNOWN |
| Websocket or runtime queue degraded | OPERATIONAL_DEGRADED |
| Heritage blocked | BLOCKED |
| Broker/order/paper/live authority contradiction or explicit unsafe state | UNSAFE (highest precedence) |

Focused truth-table tests passed. Legacy sidecar callers without complete subsystem truth now report UNKNOWN, not HEALTHY. The reporter's required subsystem list is explicit in code and output under `SUBSYSTEM_STATES`.
