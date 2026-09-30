# Queue and depth accounting

## Runtime snapshots

The bounded runtime store coalesces a pending latest-state snapshot only when session/boot/feed epochs and event/source and safety-relevant state identity match. Distinct sources and state transitions occupy distinct queue identities. Status reports requested, coalesced, enqueued, persisted, rejected, pending, in-flight, queue depth/high-water, writer lag, failures, and accounting remainder.

Focused tests cover same-identity latest-state replacement, distinct identities/transitions, forced queue saturation, an 855-identity writer drain, and a producer-side gate before expensive DB/depth/status collection. Each tick callback still performs a lightweight admission check. Same safety identity requests inside the configured interval coalesce; runtime, transport, auth, restart, recovery, disconnect, and option-verification identity changes pass immediately. Non-tick lifecycle publications always pass. The queue writer reuses the producer cadence decision, avoiding a second cadence window. A separate timer scheduler was not implemented. Defect B is **PARTIALLY VALIDATED**.

The 855-identity drain uses the actual SQLite writer path and a temporary database, with unrelated artifact side outputs mocked. It proves fixture sink persistence and accounting, not production workload throughput. The 855-request producer replay admitted one assembly and coalesced 854 same-identity requests, with a later request admitted at cadence expiry; this is synthetic gate evidence, not execution of 855 real WebSocket callbacks. The latest expanded combined regression, including recovery, T-1, feed-state, sidecar, and depth sink tests, passed 474 tests. The all-repository run recorded option-backtest failures, then stalled at 68% in a background-writer latency test and was interrupted; see `WHOLE_REPO_REGRESSION.log` and `TEST_RESULTS.md`.

## Depth

Capture is explicitly `SAMPLED_DEPTH`, using existing `DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC` semantics. Accounting distinguishes raw updates, accepted samples, persisted samples, sampled/coalesced updates, rejection, pending/in-flight, and failures. Duplicate count is intentionally `null` with status `UNAVAILABLE_NO_STABLE_EVENT_ID`; it is not fabricated as zero. Original queue/prune/post-shutdown/concurrency/writer-failure tests remain present and passed. Forced saturation and sampling tests passed.

No raw/lossless completeness claim is made. Production depth throughput under 855-token load is UNKNOWN.

An 855-token sampled-depth test now drains 855 records through the real SQLite batch writer into a temporary DB and verifies all 855 rows plus zero rejection/failure. The configured zero sampling interval is preserved in reported metrics. This upgrades the prior admission-only depth replay to an offline sink-drain check; production throughput remains UNKNOWN.
