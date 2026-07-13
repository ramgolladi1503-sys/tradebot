# TradeBot Feed Async Persistence Pressure Audit

Branch: `ram/feed-fd-diagnosis-main-sync`

Worktree: `/Users/madhuram/tradebot-feed-fd-diagnosis-main-sync`

Starting checkpoint: `eb6dcbea691953200d6ace44e15b134e0bb1bd8a`

Harness provenance:
- original harness commit: `69bd3e18a42f2d2f7902819c2332c4745feae88a`
- proof-gap commit: `df69d3318257cd8d451d078a943a4398d52cc343`

Input:
- file: `/Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet`
- SHA-256: `62410f680b0621c836e3b18e8a509126e3dfbcf40c61e3cc23d5c2bc30b95139`
- total rows: `2,778,666`
- first 100k raw timestamp range: `1783569405.7407` .. `1783569979.745924`
- first 100k UTC range: `2026-07-09 03:56:45.740700006+00:00` .. `2026-07-09 04:06:19.745923996+00:00`
- distinct tokens in first 100k rows: `129`
- missing timestamp count: `0`
- malformed timestamp count: `0`

Queue implementation:
- unbounded deque-backed write queue
- backlog threshold used by the harness: `100`
- pressure accounting:
  - `pending_writes = rows_enqueued - rows_committed`
  - invariant target: `0 <= rows_committed <= rows_dequeued <= rows_enqueued`
  - invariant target: `pending_writes >= queue_depth`

Pressure injection seam:
- replay-only hook installed by `scripts/run_feed_robustness_replay.py`
- replay-only suppression of immediate flush and read-path flushes is enabled only when the pressure profile is active
- pressure is disabled by default and was off in the no-pressure control

Commands executed:

```bash
cd /Users/madhuram/tradebot-feed-fd-diagnosis-main-sync
git branch --show-current
git rev-parse HEAD
git status --short --untracked-files=all
git log --oneline -5
git diff --check
/Users/madhuram/tradebot/.venv/bin/python scripts/run_feed_robustness_replay.py --help
```

No-pressure control:

```bash
PYTHONUNBUFFERED=1 /Users/madhuram/tradebot/.venv/bin/python -u scripts/run_feed_robustness_replay.py \
  --input /Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet \
  --output-dir .runtime/feed_robustness_audit/async-100k-pressure-control \
  --iterations 1 \
  --max-rows 100000 \
  --session-cycles 0 \
  --persistence-mode async_queue \
  --scenario normal_speed
```

No-pressure result:
- verdict: `PRESSURE_CONTROL_PASS`
- hard failures: `[]`
- rows requested / processed: `100000`
- worker start count: `1`
- worker join completed: `true`
- worker terminated: `true`
- worker failures: `0`
- rows enqueued: `100000`
- rows dequeued: `100000`
- committed rows: `100000`
- queue depth at shutdown: `0`
- pending writes at shutdown: `0`
- timestamp fidelity: passed
- unexpected timestamp fallbacks: `0`
- reconciliation deltas: `0 / 0 / 0`
- first semantic difference: `null`
- canonical semantic hash: `9eefbd54d8a88201c4398b9d43b2e8c07f01c77947c7bed5ceb3a6aff8d7cf9d`
- final-state hash: `f103a7d35c540fd19ce74f422cd409f4305c0042acfcf038927fff4bd931b5b5`
- feed-side EMFILE: not observed
- pressure hook invocation count: `0`
- committed pressure batch-size total: `0`
- requested injected delay: `0`
- observed injected delay: `0`
- stall count: `0`
- replay-only read-flush suppression: inactive
- replay-only immediate-flush suppression: inactive
- baseline FD: `92`
- final FD: `92`
- run RSS: `749731840` bytes (`715.0` MiB)
- resource sample ordering:
  - `pre_producer_sample` precedes queue growth
  - `post_join_sample` records after worker join
- `producer_completed` occurs before `shutdown_requested`

No-pressure artifact checksums:
- `run_manifest.json`: `c3a9846e4d226b105793f6cfc366ce0e1b169334a64e6ac5c936a7ec93c0a8f5`
- `feed_counters.json`: `8e7cea97f9a94ee9974067a65abb733f4a735ed0d5cbb3c34cc2a47a861dfa2a`
- `feed_verdict.json`: `b6eac8c00f7211946c6824e8fd40d277c058ced04daf2fcc8ea5cec37c52c7ad`
- `latency_report.json`: `54111545867a716b4788fcbb8b742e0dfe9c914c20b8ffb0a0e77a9366068980`
- `resource_snapshot.json`: `b0ccd17986f6702fa79da25e2105a14ab984ddeb1c3a084db95c9a3a143fb9af`
- `timestamp_fidelity.json`: `c8971b794ddf0aa07fd57e157428bf95023ceae961033471db1890b3973847a6`

Constant-delay run:

```bash
PYTHONUNBUFFERED=1 /Users/madhuram/tradebot/.venv/bin/python -u scripts/run_feed_robustness_replay.py \
  --input /Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet \
  --output-dir .runtime/feed_robustness_audit/async-100k-constant-delay \
  --iterations 1 \
  --max-rows 100000 \
  --session-cycles 0 \
  --persistence-mode async_queue \
  --pressure-profile constant_delay \
  --pressure-delay-before-each-commit-ms 2 \
  --scenario normal_speed
```

Constant-delay result:
- verdict: `ASYNC_PERSISTENCE_PRESSURE_PASS_CONSTANT_DELAY`
- hard failures: `[]`
- worker start count: `1`
- worker join completed: `true`
- worker terminated: `true`
- worker failures: `0`
- rows enqueued: `100000`
- rows dequeued: `100000`
- committed rows: `100000`
- queue depth high-water from `queue_depth_timeline.jsonl`: `6100`
- worker-state `queue_depth_high_water` snapshot: `6100`
- queue depth at shutdown: `0`
- pending writes at shutdown: `0`
- producer completion queue depth: `0`
- producer completion pending writes: `0`
- backlog drain duration: `1816338208` ns
- worker join duration field (`tick_store.shutdown_persistence_worker()` + final flush accounting): `1816338292` ns
- pressure hook invocation count: `158`
- committed batches: `158`
- hook batch size total: `100000`
- requested injected delay: `316` ms
- observed injected delay: `447.795584` ms
- queue high-water and maximum pending writes from timeline-derived accounting: `6100`
- timestamp fidelity: passed
- unexpected timestamp fallbacks: `0`
- reconciliation deltas: `0 / 0 / 0`
- first semantic difference: `null`
- canonical semantic hash: unchanged from control
- final-state hash: unchanged from control
- feed-side EMFILE: not observed
- baseline FD: `69`
- final FD: `69`
- run RSS: `695828480` bytes (`663.59375` MiB)
- backlog-drift duration: `1664673375` ns
- producer completion pending writes: `0`
- producer completion queue depth: `0`
- producer-completion ordering: `producer_completed < shutdown_requested < worker_join_completed`

Constant-delay artifact checksums:
- `run_manifest.json`: `15d039ca1bec630c9d99b88f0542cc59104817dac0ed6c460b06af3f66e92603`
- `feed_counters.json`: `2240340ff496d41e578207a0addbca642487e0c59e883a42de022e6837a040d8`
- `feed_verdict.json`: `b6eac8c00f7211946c6824e8fd40d277c058ced04daf2fcc8ea5cec37c52c7ad`
- `latency_report.json`: `d151617ef87fe033fe890cc91dcecf21646c538909b0d1e2e79665bce38c72bd`
- `resource_snapshot.json`: `b0ccd17986f6702fa79da25e2105a14ab984ddeb1c3a084db95c9a3a143fb9af`
- `timestamp_fidelity.json`: `c8971b794ddf0aa07fd57e157428bf95023ceae961033471db1890b3973847a6`
- `pressure_profile.json`: `3c20eff87a838feeaac38473dcd91fd8c8d94ee84b81d1fe50e0374ac52dd5f9`
- `worker_lifecycle.json`: `e1893eb11d7c869bf98d9ecf1952944c90d1136a02360ad7c3fcc2e80ef7d192`
- `drain_report.json`: `1d5b3090c23a9c11dec2a504d5b58ff6d295b6d1ff83fe5c9e35f8f9f7c57f6d`

Intermittent-stall run:
- verdict: `ASYNC_PERSISTENCE_PRESSURE_FAIL`
- hard failures: `["normal_speed"]`
- rows enqueued: `100000`
- rows dequeued: `61953`
- committed rows: `60953`
- queue depth at shutdown: `38047`
- pending writes at shutdown: `39047`
- queue high-water: `52411`
- maximum pending writes: `53347`
- stall activation count: `6`
- worker commit hook count: `62`
- committed batches: `62`
- hook batch size total: `60953`
- requested injected delay: `12000` ms
- observed injected delay: `12079.432252` ms
- worker join completed: `false`
- worker terminated: `false`
- worker failures: `0`
- published_equals_persisted_plus_pending_at_shutdown: `true` when interpreted as `committed_rows + pending_writes_at_shutdown = rows_enqueued`
- no loss / reorder / semantic divergence: not established because queue drain did not complete
- shutdown path: `tick_store.shutdown_persistence_worker()` returned after the fixed 2.0 s join timeout in `_shutdown_flush_thread()`
- no feed-side EMFILE: not observed

Strict verdict:
- no-pressure control: `PRESSURE_CONTROL_PASS`
- constant-delay pressure proof: `ASYNC_PERSISTENCE_PRESSURE_PASS_CONSTANT_DELAY`
- intermittent-stall pressure proof: `ASYNC_PERSISTENCE_PRESSURE_FAIL`
- overall verdict: `ASYNC_PERSISTENCE_PRESSURE_FAIL`

Maximum claim supported:

> Under the tested deterministic constant-delay profile, the asynchronous feed persistence worker accumulated a measurable backlog, preserved ordering and semantic output, drained all pending writes, and terminated cleanly within the measured memory and descriptor bounds.

The intermittent-stall profile did not complete worker shutdown within the 2.0 s join window, leaving pending writes and an unterminated worker at the end of the run. No feed-side EMFILE was observed.

Not claimed:
- live websocket behavior
- reconnect behavior
- provider completeness
- full-capture soak
- production readiness
- strategy/ranking freshness
