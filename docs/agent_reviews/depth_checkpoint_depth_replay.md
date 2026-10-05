# Depth Persistence and Tick Checkpoint Replay Review

## Agent Work Contract

```text
source_agent: gsd
action: GENERATE_TESTS
title: Prove tick checkpoint contention does not starve depth persistence
scope: Add one temporary-database mixed-writer regression and record replay evidence
requested_paths: tests/test_depth_persistence_batching.py, docs/agent_reviews/depth_checkpoint_depth_replay.md
allowed_paths: tests/test_depth_persistence_batching.py, docs/agent_reviews/depth_checkpoint_depth_replay.md
forbidden_paths: main.py, run_live.sh, config/, credentials.py, runtime/, logs/, core execution/feed/risk/broker/order/strategy modules
expected_tests: focused tick checkpoint and depth persistence tests; repository health gate
acceptance_proof: A pinned WAL reader leaves PASSIVE checkpoint incompleteness visible while tick commit and depth batch persistence complete with exact accounting.
```

## Scope Guard

This change adds a regression test and evidence only. It does not alter runtime behavior, queue limits, retry policy, sampling, risk gates, freshness gates, strategy thresholds, broker authority, or live configuration. Tests use a temporary SQLite database. No broker API or order action is called; `read_only=true` for the captured source; `is_order_action=false`; `broker_api_called=false`; `allowed_for_live_execution=false`; `append=false` for source evidence.

## Grill Me Review

- The replay is offline and cannot establish live tick delivery or live market-data freshness.
- The captured depth database contains only the retained payloads. Rejected depth records preserve rejection metadata, not the rejected full book payloads, so the rejected backlog cannot be reconstructed exactly.
- The earlier source session used producer SHA `ff250483...`, which predates merged PR #964. Current-code replay therefore evaluates the merged checkpoint behavior, not the exact original producer/runtime.
- Do not infer that checkpoint semantics alone caused the full original backlog; throughput and historical missing payloads remain distinct evidence gaps.

## Hermes Review

The acceptance contract is safety-preserving: tick inserts are committed once, a passive checkpoint's incomplete progress remains observable/degraded, and the independent depth writer drains the test batch with exact accounting while the reader pins WAL state. The test must fail on a blocking tick writer and must release its reader and worker resources on assertion failure. No production code change is justified unless this test or further current evidence demonstrates a defect.

## GSD Review

Only the two allowed files are changed. The integration test uses actual `tick_store._write_rows` and `DepthStore`, real SQLite WAL semantics, and a temporary database; it does not mock away the checkpoint or persistence decision.

## QA / Safety Review

- No credentials, environment files, production databases, logs, or live processes were changed.
- No broker API, order action, LIVE mode, execution gate, strategy, risk gate, or feed freshness gate was touched.
- `read_only=true`; `is_order_action=false`; `broker_api_called=false`; `allowed_for_live_execution=false`; `append=false` for source evidence.
- Source Parquet and SQLite artifacts were opened read-only. Replay writes used an ephemeral temporary SQLite database that was removed at process exit.

## Acceptance Proof

Read-only 2026-10-05 market-data replay on current merged `origin/main`:

- Tick input: 171,293 NIFTY and BANKNIFTY underlying rows; accepted 171,293; rejected 0.
- Tick shutdown: `COMPLETE_DRAIN`; enqueued/dequeued/committed 171,293; 13,396 batches; zero pending, queued, in-flight, rejected, or worker failures.
- Depth input/enqueued/persisted: 48,995; max queue 161; rejected/failures 0; final queue and in-flight 0; clean worker shutdown.
- Combined 220,288 events were replayed in event-time order at 50x acceleration (466.91 seconds wall time).
- Tick timestamp provenance was explicitly `UNKNOWN` from `market_data_parquet.ts`; replay does not assert exchange timestamp authority.
- `PYTHONPATH=. pytest -q tests/test_depth_persistence_batching.py tests/test_depth_store_accounting.py tests/test_tick_store_checkpoint_commit_truth.py` — 27 passed.
- `PYTHONPATH=. python3 -m core.health_gate --desk DEFAULT --strict` — passed; exit code 0, no issues.
- CI-equivalent command `PYTHONPATH=. pytest -q -o addopts='' -m "not integration and not feed_smoke and not feed_soak and not certification" --durations=25 --timeout=300 --timeout-method=thread` — 8,788 passed, 9 skipped, 8 failed, 28 deselected. Failures: one existing subprocess lock-owner test exceeded its 5-second timeout under this long local run; seven existing `test_strategy_live_shadow.py` cases invoke the literal `python` executable, unavailable in this environment (`python3` is installed). These failures are unrelated to the changed files. Repository CI uses Ubuntu/Python 3.12, so exact-head CI remains the required merge gate.
- `git diff --check` — passed.

The captured SQLite has 48,995 retained depth snapshots across 128 tokens, spanning epochs 1791172180.58494–1791172688.629923. This is only the retained opening segment, not full-session depth coverage. The Parquet tick artifact has 5,895,355 rows across 250 tokens; the replay intentionally selected only NIFTY and BANKNIFTY underlying tokens 256265 and 260105.

## Runtime Proof Required After Merge

During the next authorized live session, collect read-only telemetry for tick queue accounting, committed batches, checkpoint attempts/incomplete frames/degradation, depth enqueued/persisted/rejected/failure counters, queue high-water, worker health, and feed freshness/producer scope. Correlate exact producer SHA, runtime paths, and session timestamps. Do not restart the process or infer live health from the offline replay. Any live observation must preserve `read_only=true` and no broker/order authority.

## What This PR Does Not Prove

- That all PRs in the prior 10–15 PR stack are functioning in a live run.
- That the historical 183,085 rejected depth frames can be reconstructed or persisted; their full payloads were not retained.
- That current behavior matches the historical producer/runtime before PR #964.
- That all 123 subscribed option tokens or all six-and-a-half market hours have complete source coverage.
- That checkpoint behavior alone explains every historical tick/depth failure or resolves live market delivery.
- That any strategy has a trading edge, or that the system is ready for live execution.

## Human Approval

The user authorized the bounded offline replay and work on the recommended depth persistence issue, instructed that live processes not be restarted, and authorized opening/merging after health checks and CI are green. This change does not request or perform broker/order actions.
