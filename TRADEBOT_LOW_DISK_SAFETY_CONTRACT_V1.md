# TradeBot Low-Disk Safety Contract V1

This contract is additive and fail-closed. `required_free_bytes` is the measured
preserved-runtime baseline plus the measured byte rate multiplied by the exact
remaining session budget, plus separately measured transient and shutdown
reserves. No deletion, cleanup, risk-gate bypass, broker write, or order action
is permitted.

Evidence basis: preserved runtime root
`/Volumes/TradeBotData/preserved-stalled-runtime-20260825T110749+0530`,
105,265,039 bytes across 8.619190410839186 hours, yielding
3,392.463470158 bytes/second. The market window is 09:15–15:30 IST (22,500 s).

The bounded exporter probe measured 120,190 bytes of transient/output
amplification and an isolated 1,000-row persistence drain measured 106,496
bytes of shutdown-side growth. The explicit
`PARTIAL_SESSION_BASELINE_PLUS_BOUNDED_EXPORT_AND_SHUTDOWN_PROBES` state is not
eligible for production readiness because it is not complete-session evidence.
Missing or unreadable
filesystem measurements return `UNKNOWN`; insufficient free space returns
`BLOCKED`.
