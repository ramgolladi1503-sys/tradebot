# Stress results

Status: **PARTIAL — OFFLINE 855-REQUEST PRODUCER GATE, 855-IDENTITY RUNTIME SQLITE DRAIN, 855-TOKEN DEPTH ADMISSION, AND 855-ROW DEPTH SQLITE DRAIN PASS; PRODUCTION STRESS NOT RUN**.

The producer-gate test `test_runtime_snapshot_producer_gate_bounds_855_instrument_callback_burst` submits 855 same-identity tick snapshot requests inside the configured interval; one is admitted for assembly and 854 are coalesced, then a later request at interval expiry is admitted. This invokes the producer admission contract, not `on_ticks` with 855 real tokens. The offline test `test_feed_runtime_queue_handles_855_distinct_identities_without_rejection` fills 855 queue identities, submits a second latest-state update per identity, and asserts 855 enqueued, 855 coalesced, and zero rejected. A separate test uses 855 identities and the actual runtime SQLite writer against a temporary database; it verifies 855 rows persisted, zero rejected, zero failures, and empty queue after drain. Artifact side outputs are mocked. The depth test `test_855_token_depth_burst_accounts_sampled_updates_without_queue_rejection` submits two updates for 855 tokens and asserts 855 enqueued sample windows, 855 coalesced updates, and zero queue rejection; it does not drain the depth sink. These deterministic fixtures are not end-to-end callback or live 855-instrument workload evidence. The forced queue-saturation test separately establishes rejection visibility. The following remain unestablished:

- 855-identity live-equivalent callback workload and zero runtime errors;
- zero `FEED_RUNTIME_STORE_WRITE_ERROR` / `RUNTIME_QUEUE_FULL` under real callback load;
- production depth burst throughput/loss rate;
- runtime cost under actual 855-token WebSocket callbacks;
- real 855-token `on_ticks` callback workload and production throughput. A source-level regression confirms the existing watchdog timer emits snapshots independently after its wait; this does not measure runtime cost.

Synthetic unit cases do not establish live performance or certify production overload resolution. No broker/live process was used.

## Additional sampled-depth sink drain

The depth 855-token fixture now also drains through the actual `DepthStore` asynchronous batch writer into a temporary SQLite database and queries the resulting rows. Result: **855 input, 855 accepted/enqueued, 855 persisted, 0 queue rejects, 0 pre-enqueue rejects, 0 write failures**, empty queue, and both accounting invariants true. The test also checks that explicit `DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC=0.0` is reported as `sampling_interval_ms=0`. This strengthens offline sink evidence. It is still not production throughput or a real WebSocket callback stress result.


## Actual 855-row callback burst replay

The offline test `test_on_ticks_855_row_batches_preserve_tick_depth_observation_when_snapshot_coalesces` invokes the actual `on_ticks` callback twice with 855 synthetic rows each. It observes 1,710 tick insertions and 1,710 depth-store update calls, with one runtime snapshot assembly/publication and one coalesced request. Artifact, forensic, and raw store effects are stubbed to isolate callback/admission ordering.

The focused websocket/depth/recovery selection passed **209 tests, 0 failed, 0 skipped, 3 warnings, 41.18s**. This is an offline callback regression only. It does not prove production throughput, real socket timing, raw-event durability, or absence of live workload overload.

## Continuation reconciliation (2026-09-30)

No new stress workload was run in this evidence-only continuation. The existing actual-callback replay remains two synthetic 855-row `on_ticks` invocations (1,710 tick/depth update calls), with external persistence sinks stubbed. The 855-identity and 855-token SQLite sink drains remain temporary-database offline tests. There is no production-load, real socket, or live-runtime throughput result. See `FINAL_CONTINUATION_VERDICT.md`.
