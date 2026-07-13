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

## Shutdown-contract remediation refresh

Implementation checkpoint:
- commit: `c3c2e888a57e0a12588c1e25687943290ac4b072`
- message: `fix: make tick persistence shutdown drain-aware`
- isolation commit for the evidence tree: `81246ff1a8271f6c8f6e4b0d0f9a4bfdf3c1a8a5`
- note: the 100k evidence was generated from the same tree contents before the isolation-only diff was committed

Daemon policy:
- retained daemon worker temporarily
- rationale: the worker is still shut down explicitly and must never be reported as complete while alive
- observed on the committed implementation: `worker_daemon = true`

Explicit shutdown lifecycle:
- `RUNNING`
- `STOP_ACCEPTING_WRITES`
- `DRAINING`
- `INCOMPLETE_DRAIN_TIMEOUT`
- `COMPLETE_DRAIN`
- `WORKER_FAILURE`

Retryable timeout behavior:
- initial timeout is preserved in `initial_shutdown_result`
- cleanup completion is preserved in `cleanup_shutdown_result`
- retry uses the same worker and queue
- writes remain closed after shutdown begins

Exact implementation flags and fields:
- shutdown deadline flag: `--persistence-shutdown-deadline-seconds`
- shutdown status fields: `shutdown_status`, `deadline_seconds`, `deadline_expired`
- immutable timeout snapshot fields: `timeout_monotonic_ns`, `lifecycle_state`, `rows_enqueued`, `rows_dequeued`, `rows_committed`, `committed_batches`, `queue_depth`, `in_flight_rows`, `pending_writes`, `writes_rejected_after_shutdown`, `worker_alive`, `worker_failures`
- worker identity fields: `worker_daemon`, `worker_join_completed`, `worker_terminated`

Verified input envelope refresh:
- file SHA-256: `62410f680b0621c836e3b18e8a509126e3dfbcf40c61e3cc23d5c2bc30b95139`
- total rows: `2,778,666`
- first 100k raw timestamp range: `1783569405.7407` .. `1783569979.745924`
- first 100k UTC range: `2026-07-09 03:56:45.740700006+00:00` .. `2026-07-09 04:06:19.745923996+00:00`
- distinct tokens in first 100k rows: `129`
- missing timestamp count: `0`
- malformed timestamp count: `0`

Control evidence refresh:

```bash
PYTHONUNBUFFERED=1 /Users/madhuram/tradebot/.venv/bin/python -u scripts/run_feed_robustness_replay.py \
  --input /Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet \
  --output-dir .runtime/feed_robustness_audit/async-100k-shutdown-control \
  --iterations 1 \
  --max-rows 100000 \
  --session-cycles 0 \
  --persistence-mode async_queue \
  --pressure-profile none \
  --scenario normal_speed
```

No-pressure result:
- verdict: `CONDITIONALLY_STABLE`
- hard failures: `[]`
- rows requested / processed: `100000`
- rows enqueued / dequeued / committed: `100000 / 100000 / 100000`
- queue depth / in-flight / pending at shutdown: `0 / 0 / 0`
- worker start count: `1`
- worker join completed: `true`
- worker terminated: `true`
- worker alive: `false`
- worker failures: `0`
- writes rejected after shutdown: `0`
- deadline expired: `false`
- shutdown status: `COMPLETE_DRAIN`
- timestamp fidelity: passed
- unexpected timestamp fallbacks: `0`
- reconciliation deltas: `0 / 0 / 0`
- first semantic difference: `null`
- canonical semantic hash: `9eefbd54d8a88201c4398b9d43b2e8c07f01c77947c7bed5ceb3a6aff8d7cf9d`
- final-state hash: `f103a7d35c540fd19ce74f422cd409f4305c0042acfcf038927fff4bd931b5b5`
- queue-depth high-water: `1`
- pressure hooks: none
- stalls: none
- baseline FD / final FD: `64 / 64`
- RSS: `714571776` bytes (`681.46875` MiB)

No-pressure artifact checksums:
- `run_manifest.json`: `188d8fb2e5c88140da334570f0eaaa2449a69ed00c080d60a577ed613fef0a02`
- `feed_counters.json`: `dce91ef15789c50959d6668e84aebe38a1d7c88b8ac69c386ab5dcd3d5369233`
- `feed_verdict.json`: `b6eac8c00f7211946c6824e8fd40d277c058ced04daf2fcc8ea5cec37c52c7ad`
- `latency_report.json`: `6146263a119bf678f007faab0847a7c2fb69e3dce69f805bb88cff281fd6577d`
- `resource_snapshot.json`: `c587860e7763ccd544da728cacc9f8b00431fb469611563808a3196569a0dd39`
- `timestamp_fidelity.json`: `c8971b794ddf0aa07fd57e157428bf95023ceae961033471db1890b3973847a6`

Short-deadline intermittent negative control:

```bash
# same runner inputs as the control, but with pressure_profile=intermittent_stall
# and an initial 2.0 second shutdown deadline; cleanup used a second shutdown call
# in-process with a longer deadline to preserve the same worker.
```

Short-deadline result:
- initial shutdown status: `INCOMPLETE_DRAIN_TIMEOUT`
- cleanup shutdown status: `COMPLETE_DRAIN`
- negative-control classification: `INTERMITTENT_STALL_EXPECTED_TIMEOUT_CLASSIFIED`
- initial timeout preserved in `initial_shutdown_result`: yes
- cleanup preserved in `cleanup_shutdown_result`: yes
- initial rows enqueued / dequeued / committed: `100000 / 50667 / 49667`
- initial queue depth / in-flight / pending: `49333 / 1000 / 50333`
- initial worker alive / terminated: `true / false`
- initial worker failures: `0`
- initial writes rejected after shutdown: `0`
- cleanup rows enqueued / dequeued / committed: `100000 / 100000 / 100000`
- cleanup queue depth / in-flight / pending: `0 / 0 / 0`
- cleanup worker alive / terminated: `false / true`
- cleanup worker failures: `0`
- cleanup writes rejected after shutdown: `0`
- immutable timeout snapshot scope:
  - state at deadline expiry only: `rows_enqueued=100000`, `rows_dequeued=50667`, `rows_committed=49667`, `queue_depth=49333`, `in_flight_rows=1000`, `pending_writes=50333`
  - `committed_batches` at deadline expiry: `51`
  - `stall_activation_count` at deadline expiry: `6`
  - `worker_commit_hook_count` at deadline expiry: `51`
  - `hook_batch_size_total` at deadline expiry: `49667`
- historical archived run values kept separate for comparison only:
  - `committed_batches=62`
  - `hook_batch_size_total=60953`
  - `stall_activation_count=6`
  - `requested injected delay=12000 ms`
  - `observed injected delay=12079.432252 ms`
- queue high-water at deadline expiry: `49333`
- max pending writes at deadline expiry: `50333`
- FD note: the current evidence captures `final FD=13` before the post-cleanup descriptor-close sample was recorded; this does not prove recovery and remains a reporting gap until a post-cleanup sample is added.
- initial RSS: `724418560` bytes (`690.859375` MiB)

Sufficient-deadline intermittent result:
- verdict: `CONDITIONALLY_STABLE`
- shutdown status: `COMPLETE_DRAIN`
- deadline expired: `false`
- rows enqueued / dequeued / committed: `100000 / 100000 / 100000`
- queue depth / in-flight / pending at shutdown: `0 / 0 / 0`
- worker alive / terminated: `false / true`
- worker failures: `0`
- writes rejected after shutdown: `0`
- stall activation count: `9`
- pressure hook invocation count: `101`
- committed batches: `101`
- hook batch-size total: `100000`
- queue high-water: `69987`
- maximum pending writes: `69987`
- timestamp fidelity: passed
- unexpected timestamp fallbacks: `0`
- reconciliation deltas: `0 / 0 / 0`
- first semantic difference: `null`
- canonical semantic hash: matched control
- final-state hash: matched control
- baseline FD / final FD: `8 / 8`
- RSS: `685735936` bytes (`653.96875` MiB)

Sufficient-deadline artifact checksums:
- `run_manifest.json`: `ccc3e0ab75aabc8b67009c65992de43f087d4e24c3e76bfb67efc40c3ad44eb9`
- `feed_counters.json`: `ab4932a43619a304b6a6a330f4d8349291f5125a74fe52199f1cd1c5873ada7e`
- `feed_verdict.json`: `b6eac8c00f7211946c6824e8fd40d277c058ced04daf2fcc8ea5cec37c52c7ad`
- `latency_report.json`: `b28c0311279e7fe4c47f6e5c8bcab2fedf2e8f11ea329c2b598a7f7215e06175`
- `resource_snapshot.json`: `1054cb41420c0af51078fdab6b3fe3abc1f25bbed387863826709d73c15094f7`
- `pressure_profile.json`: `02d460ef8df50808f25ef575e4c8ae055f8043ededeb1b6157c32c75ec99559d`
- `timestamp_fidelity.json`: `c8971b794ddf0aa07fd57e157428bf95023ceae961033471db1890b3973847a6`

Strict final pressure-recovery verdict:
- `100K_ASYNC_PERSISTENCE_PRESSURE_RECOVERY_PASS`

Maximum claim supported by the refreshed evidence:

> Under the tested 100,000-row intermittent-stall profile, the async persistence worker explicitly reports insufficient shutdown deadlines, preserves immutable timeout evidence, continues draining the same worker under a longer cleanup deadline, and—with a sufficient deadline—drains all queued and in-flight writes, preserves ordering and semantic output, and terminates cleanly within the measured memory and descriptor bounds.

Remaining limitations:
- this evidence does not prove live websocket recovery
- this evidence does not prove provider completeness
- this evidence does not prove full-session soak
- this evidence does not prove full-capture scale
- this evidence does not prove ranking freshness
- this evidence does not prove execution freshness
- this evidence does not prove overall production readiness
