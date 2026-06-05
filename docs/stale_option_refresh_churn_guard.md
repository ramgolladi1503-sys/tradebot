# Stale Option Refresh Churn Guard

## Summary

This patch separates stale-option freshness diagnostics from websocket subscription mutation.
Tiny stale subsets no longer force a full-symbol refresh, and subscription mutation is only allowed after breadth, fresh-ratio, and consecutive-window thresholds are met.

## Safety

- read_only: true
- is_order_action: false
- broker_api_called: false
- live_execution_changed: false
- behavior_changed: false
- runtime_behavior_changed: false
- order_behavior_changed: false
- broker_order_called: false
- execution_behavior_changed: false

## What Changed

- Raised the default stale-option drift refresh cooldown to 45 seconds.
- Added a pure helper that requires broad stale breadth plus consecutive breached windows before allowing subscription mutation.
- Added a websocket mutation guard that blocks dynamic subscribe/unsubscribe/set_mode calls when runtime, recovery, or websocket state is unsafe.
- Kept initial on-connect subscription behavior unchanged.

## What Did Not Change

- No broker or order behavior.
- No strategy, ranking, or Phase2 behavior.
- No dashboard/UI behavior.
- No FeedTruth or candidate evidence contracts.
- No terminal WS1006 process-restart behavior.

## Tests

- `PYTHONPATH=. pytest -q tests/test_kite_depth_ws_stability.py tests/test_kite_depth_restart.py -vv`
- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr491_changed_paths.txt`

## Rollout Notes

- No runtime rollout is required.
- The guard fails closed and only reduces unnecessary subscription churn.
