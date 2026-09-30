# Baseline

Captured 2026-09-30 14:58 IST before implementation edits.

- Repair base: `e2e95aae201271db9cb7abe11b43d462bea3bd57`.
- `origin/main` and the ReleaseStore `current.json` history event both identify this as the current certified live SHA. Git history confirms PR #938 (`7114619ca`) and PR #939 (the base commit) are included.
- Active live worktree: `/Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1`, same SHA, initial `git status --porcelain=v1` count 0.
- Repair worktree: `/Users/madhuram/.codex/worktrees/mros-live-runtime-truth-v1/tradebot`, created clean at the base, branch `fix/mros-live-runtime-truth-reliability-v1`.

Offline baseline command:

```bash
/opt/anaconda3/bin/pytest -q tests/test_edge43_feed_health_truth.py tests/test_pr_feed_04_feed_recovery_warmup_gate.py tests/test_candidate_executability_evidence.py tests/test_kite_depth_ws_stability.py tests/test_kite_depth_ws_observation_on_ticks.py tests/test_kite_depth_ws_market_event_graph_lifecycle.py tests/test_kite_depth_ws_watchdog_scope.py tests/core/test_runtime_snapshot_producer.py tests/test_runtime_snapshot_producer_metrics.py tests/test_runtime_snapshot_producer_tail.py tests/core/test_runtime_snapshot_store.py tests/core/test_tick_store_db_truth.py tests/test_tick_store.py tests/test_tick_store_nonblocking_decision_path.py tests/test_ws_tick_ingestion_updates_tick_store.py tests/test_feed_truth_contract.py tests/test_market_event_graph_live_ohlc_buffer.py tests/test_market_event_graph_live_ohlc_buffer_deterministic_test.py tests/test_market_event_graph_runtime_observer.py tests/test_market_event_graph_live_runtime_bridge.py tests/test_market_heritage_graph.py tests/test_auth_health.py tests/test_morning_operator_status.py tests/test_runtime_status_overlay.py tests/test_orchestrator_runtime_snapshots.py tests/test_orchestrator_reports_finally.py
```

Result: **277 passed, 9 failed** in 25.58 seconds. All 9 failures were in `tests/test_market_event_graph_live_runtime_bridge.py`; they were caused by shared process-local feed-epoch state in this combined selection. This attribution is supported by running that module alone in a fresh process: **18 passed** in 2.49 seconds. The behavior assertions were not changed during baseline.

Environment warnings: installed pandas reported older-than-required `numexpr` and `bottleneck` versions; `Timestamp.utcnow` emitted a deprecation warning. These warnings did not fail the baseline.

This is targeted baseline evidence only, not whole-repository regression evidence.
