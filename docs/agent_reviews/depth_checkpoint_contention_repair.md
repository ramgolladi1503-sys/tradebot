# Tick Checkpoint Contention Repair

## Agent Work Contract

- `source_agent`: `grill_me -> hermes -> gsd`
- `action`: `AUDIT_RISK`, `DEFINE_CONTRACT`, `CREATE_ACCEPTANCE_GATES`, `GENERATE_TESTS`, `GENERATE_PATCH`, `FIX_TEST_FAILURE`, `UPDATE_DOCS`
- `title`: Remove blocking tick WAL checkpoint stalls without weakening durability
- `scope`: Replace per-batch blocking SQLite `TRUNCATE` checkpointing in the tick writer with a nonblocking checkpoint attempt; report incomplete progress as degraded after preserving the committed-row result.
- `requested_paths`: `core/tick_store.py`, `tests/test_tick_store_checkpoint_commit_truth.py`, `docs/agent_reviews/depth_checkpoint_contention_repair.md`
- `allowed_paths`: the requested paths only
- `forbidden_paths`: broker/order APIs, credentials, environment files, live runtime settings, process restarts, strategies, risk/kill-switch/freshness gates, and unrelated files
- `expected_tests`: tick commit/checkpoint truth tests, SQLite WAL bound tests, focused tick/depth persistence tests, and exact-head hosted CI
- `acceptance_proof`: a held SQLite reader does not block the tick writer; committed tick rows remain acknowledged exactly once; incomplete checkpoint progress is visible and keeps persistence degraded; ordinary writes stay within the declared WAL bound.

## Stage 0: Grill Me Risk Review

The 2026-10-05 incident evidence shows sustained depth queue saturation, not a proven exclusive cause. The preserved session recorded 183,085 `QUEUE_REJECTED` rows at queue depth 65,536 from 09:33:49 to 15:30:02 IST, 47,245 persisted depth rows, 65,536 queued rows, and 250 in flight at shutdown. The session did not preserve the effective SQLite path, depth batch size override, or depth batch latency; therefore this change must not claim to explain the entire depth service-rate deficit.

The same session recorded 80 tick checkpoint failures after durable inserts. Current tick code runs `PRAGMA wal_checkpoint(TRUNCATE)` after every tick batch while the connection busy timeout is 30 seconds. An isolated temporary SQLite reproduction with a pinned reader measured a 10.7-second `TRUNCATE` wait at a 10-second timeout; `PASSIVE` returned in 0.156 ms. This confirms a blocking maintenance path that serializes against repository writers and can starve depth persistence when a reader prevents truncation. It is a confirmed defect and a credible contributor, but its exact share of the live depth backlog remains unmeasured.

Do not enlarge the queue or report accounting correctness as a throughput fix. Do not change the durability gate to make checkpoint failures disappear. Keep the committed tick result authoritative even when post-commit maintenance is incomplete.

## Stage 1: Hermes Contract and Acceptance

- `read_only=true` for incident evidence; no session file is modified.
- `is_order_action=false`; no broker API or order API is called.
- `allowed_for_live_execution=false`; no live setting or process is changed.
- Tick batch insert commit remains the durability boundary. A later checkpoint result cannot cause the batch to be replayed.
- Checkpoint maintenance must not wait for readers. An incomplete checkpoint is still recorded as `SQLITE_WAL_CHECKPOINT_BUSY` and marks persistence degraded.
- The WAL byte limit and `journal_size_limit` remain unchanged.
- Tests use temporary SQLite databases only and prove the held-reader, commit-once, and degraded-state behavior.

## Stage 2: GSD Execution

Implementation will be limited to the three requested paths above. No new configuration key is introduced. If the regression test passes, run the focused tick/checkpoint/WAL/depth persistence tests and then rely on exact-head CI for broader integration validation.

## Stage 3: Goal / Continuous Verification

CI can prove the code contract, not live throughput. The historical observer PID 37306 is absent and its shutdown artifact is terminally failed; do not restart it or rewrite its evidence. After a separately authorized future session, read-only acceptance should capture effective DB path identity, effective batch size, producer rate, per-batch service time, checkpoint frame progress, lock wait, queue high-water mark, rejections, and exact shutdown reconciliation. Until then, full production depth throughput remains unverified.

## Validation Results

- Focused tick/checkpoint/WAL/depth suite: 46 passed.
- An isolated temporary SQLite reproduction with a pinned reader and 5,000 appended rows measured `wal_checkpoint(TRUNCATE)` at 10,736.838 ms (10-second connection timeout) and `wal_checkpoint(PASSIVE)` at 0.156 ms. The reader prevented full checkpoint progress in both cases; this reproduction isolates the checkpoint-mode wait and does not reproduce the whole market session.
- The new regression test uses a temporary database, pins a reader snapshot, and verifies the tick writer returns in under two seconds, keeps the durable row count exact, records incomplete WAL frame progress, and leaves the persistence degradation visible.
- New runtime diagnostics in the shutdown `tick_state`: checkpoint mode, attempts, incomplete/error counts, cumulative and maximum duration, and maximum pending frames. These are diagnostic only and do not authorize execution.
- No new configuration keys. The existing 65,536-byte WAL size/journal limit and the `wal_autocheckpoint=1` setting are unchanged.
- `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`; no live process or broker/order path was touched.

## Remaining Limits

This fixes the confirmed blocking checkpoint path, but does not prove it accounted for the whole 2026-10-05 depth backlog. The incident lacks effective database-path and batch-size provenance and depth batch latency. The historical process has stopped, so post-merge production throughput requires a future separately authorized read-only session. No depth queue capacity increase or strategy behavior change is included.
