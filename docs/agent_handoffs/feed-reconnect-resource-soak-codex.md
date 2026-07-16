# Codex Handoff: Feed Reconnect Resource Soak Recovery

## Worktree
- `/Users/madhuram/.codex/worktrees/tradebot/feed-reconnect-resource-soak-recovery`

## Branch
- `codex/feed-reconnect-resource-soak-recovery`

## Base Commit
- `4235c012874757707a14322e3d5457fe0cb1896a`

## Checkpoint Commit Tested At 1000 Cycles
- `30b13a55489ed744a257d2c58d18448eddbbd02b`

## Final Commit
- Pending at document creation time in this file. Update after local commit.

## Changed Files
- `core/kite_depth_ws.py`
- `scripts/run_feed_reconnect_resource_soak.py`
- `tests/test_feed_reconnect_resource_soak.py`
- `tests/test_kite_depth_ws_stability.py`
- `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
- `docs/agent_handoffs/feed-reconnect-resource-soak-codex.md`

## Production Changes And Rationale
- `core/kite_depth_ws.py`
  - real lifecycle fix in `_resubscribe_full()`
  - zero-count option maps no longer keep recovery uncleared after exact replay
- `scripts/run_feed_reconnect_resource_soak.py`
  - reporting-only post-checkpoint change
  - negative profiles now persist `post_cleanup_final`
  - positive reconnect semantics intentionally unchanged after checkpoint

## Profiles Implemented
- `control`
- `reconnect_guarded`
- `reconnect_unbounded_resource_stress`
- `owner_failure`
- `negative_fd_leak`
- `sqlite_same_path_multi_descriptor_negative`

## Short-Suite Result
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python -m pytest -vv tests/test_feed_reconnect_resource_soak.py tests/test_kite_depth_ws_stability.py tests/test_feed_recovery_coordinator.py tests/test_kite_depth_restart.py -k "not test_reconnect_stress_1000_has_bounded_resources and not test_control_1000_has_no_cycle_correlated_fd_growth" --tb=long`
- Result:
  - `145 passed, 2 deselected in 370.38s`

## 100-Cycle Result
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python scripts/run_feed_reconnect_resource_soak.py --profile reconnect_unbounded_resource_stress --cycles 100 --sample-every 10 --seed 42 --output-json /tmp/codex_reconnect_unbounded_100.json`
- Result:
  - `RECONNECT_RESOURCE_100_CYCLE_PASS`
  - `disconnect_count=100`
  - `verified_successful_reconnect_count=100`
  - `generation_transition_count=100`
  - `fd_count 7 -> 9 -> 9`
  - `sqlite_fd_count 0 -> 0 -> 0`
  - `retired_websocket_generations_reachable=0`

## 1000-Cycle Result
- This 1000-cycle proof applies to checkpoint `30b13a55489ed744a257d2c58d18448eddbbd02b`.
- The later change affects negative-control cleanup reporting only.
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python scripts/run_feed_reconnect_resource_soak.py --profile reconnect_unbounded_resource_stress --cycles 1000 --sample-every 100 --seed 42 --output-json /tmp/codex_reconnect_unbounded_1000.json`
- Result:
  - `RECONNECT_RESOURCE_1000_CYCLE_PASS`
  - `disconnect_count=1000`
  - `reconnect_attempt_count=1000`
  - `verified_successful_reconnect_count=1000`
  - `generation_transition_count=1000`
  - `websocket_generations_created=1001`
  - `fd_count 7 -> 9 -> 9`
  - `sqlite_fd_count 0 -> 0 -> 0`
  - `retired_websocket_generations_reachable=0`
  - `reconnect_lock_held=false`

## Guarded-Policy Result
- `RECONNECT_GUARDED_POLICY_PASS`
- `disconnect_count=3`
- `verified_successful_reconnect_count=2`
- `first_mismatch=guarded_policy_blocked_at_cycle_2: recovery blocked by original safety limits`

## Owner-Failure Result
- `RECONNECT_OWNER_FAILURE_RECOVERY_PASS`
- `disconnect_count=100`
- `owner_failures_injected_count=19`
- `owner_failures_observed_count=19`
- `owner_recoveries_completed_count=19`
- `reconnect_lock_held=false`

## Negative-Control Cleanup Result
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python scripts/run_feed_reconnect_resource_soak.py --profile negative_fd_leak --cycles 20 --sample-every 5 --seed 42 --output-json /tmp/codex_negative_fd_leak_20.json`
- Result:
  - `RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS`
  - `first_mismatch=fd_leak_detected_final`
  - `fd_count 7 -> 27 -> 7`
  - `sqlite_fd_count 0 -> 0 -> 0`

## SQLite Same-Path Result
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python scripts/run_feed_reconnect_resource_soak.py --profile sqlite_same_path_multi_descriptor_negative --cycles 20 --sample-every 5 --seed 42 --output-json /tmp/codex_sqlite_same_path_negative.json`
- Result:
  - `RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS`
  - `first_mismatch=fd_leak_detected_final`
  - `fd_count 7 -> 47 -> 7`
  - `sqlite_fd_count 0 -> 40 -> 0`

## Storage Result
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python -m pytest -q tests/test_analytics_schema_store.py tests/test_decision_store.py tests/test_depth_store_rate_limit.py tests/test_feed_debug_runtime_store.py tests/test_feed_runtime_store_lifecycle.py tests/test_order_approval_store.py tests/test_order_store_persistence.py tests/test_position_state_store.py tests/test_storage_subsystem.py tests/test_tick_store.py tests/test_tick_store_nonblocking_decision_path.py tests/test_trade_store_depth_snapshot_resilience.py tests/test_trade_store_identity.py tests/test_ws_tick_ingestion_updates_tick_store.py tests/core/test_market_snapshot_store.py tests/core/test_runtime_snapshot_store.py tests/core/test_tick_store_db_truth.py tests/analytics/test_store.py --tb=long`
- Result:
  - `66 passed in 2.60s`

## Remaining Limitations
- Offline synthetic soak only.
- No live/paper broker session proof.
- Positive final snapshots are post-stop snapshots.
- `pre_shutdown_snapshot` and `post_shutdown_snapshot` were not part of the 1000-cycle checkpoint JSON and remain `UNMEASURED`.

## No PR
- No PR opened.

## No Merge
- No merge performed.
