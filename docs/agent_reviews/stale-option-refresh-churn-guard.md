mode: REVIEW
candidate_id: PR-STALE-OPTION-REFRESH-CHURN-GUARD
decision: add_stale_option_refresh_churn_guard
reason: Reduce feed-layer websocket subscription churn by separating freshness diagnostics from mutation permission, raising stale-option drift refresh cooldown, and adding a fail-closed mutation guard without changing trading behavior.
timestamp: 2026-06-05T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/stale-option-refresh-churn-guard.md

# Stale Option Refresh Churn Guard

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Stale Option Refresh Churn Guard
- scope: Feed-layer websocket subscription mutation guard and evidence only.
- requested_paths: `core/kite_depth_ws.py`, `tests/test_kite_depth_ws_stability.py`, `tests/test_kite_depth_restart.py`, `docs/stale_option_refresh_churn_guard.md`, `docs/agent_reviews/stale-option-refresh-churn-guard.md`
- allowed_paths: same as requested paths.
- forbidden_paths: strategy, ranking, Phase2, broker/order, dashboard/UI, runtime artifacts, logs, config, credentials.
- expected_tests: websocket stability, websocket restart, feed runtime order-pollution suite, evidence gate, CE gate.
- acceptance_proof: stale single-token or high-fresh-ratio diagnostics do not mutate subscriptions, broad repeated stale symbol windows can still mutate, and unsafe websocket lifecycle states suppress subscribe/unsubscribe/set_mode.

## Scope Guard

Feed-layer subscription lifecycle hardening only. The goal is to reduce avoidable subscription churn from tiny stale option subsets while preserving legitimate breadth-based rebalance behavior.

## Changed Files

- `core/kite_depth_ws.py`
- `tests/test_kite_depth_ws_stability.py`
- `docs/stale_option_refresh_churn_guard.md`

## Safety Constraints

- No broker calls.
- No live orders.
- No strategy changes.
- No ranking changes.
- No Phase2 behavior changes.
- No dashboard/UI changes.
- No FeedTruth contract changes.
- No websocket terminal-recovery weakening.

## Grill Me Review

- PASS: The patch targets subscription mutation permission, not trading decisions.
- PASS: The change is fail-closed when websocket state is stopped, disconnected, recovery-blocked, or stale.
- PASS: The main residual risk is over-suppression of dynamic mutation; initial subscribe and normal reconnect paths remain separately covered.
- PASS: No evidence claims broker interaction or live execution.

## Hermes Review

- PASS: Diagnostics and mutation permission are now separate concepts.
- PASS: The helper exposes explicit thresholds, observed freshness breadth, window counters, and skip reasons.
- PASS: The mutation guard is centralized for dynamic subscribe/unsubscribe/set_mode paths.
- PASS: Configuration remains backward compatible through `getattr` defaults.

## GSD Review

- PASS: Implementation is narrow and test-backed.
- PASS: Existing WS1006/ReactorNotRestartable terminal lifecycle tests remain intact.
- PASS: Existing soft-resubscribe success tests now model the required connected/running/tick-fresh preconditions.
- PASS: No runtime artifacts are committed.

## QA / Safety Review

- PASS: Tests prove stale diagnostics alone do not trigger a full symbol refresh.
- PASS: Tests prove high fresh-ratio stale subsets are logged as skipped, not mutated.
- PASS: Tests prove broad repeated stale windows can still produce a legitimate refresh.
- PASS: Tests prove disconnected and recovery-blocked websocket states suppress dynamic mutation.

## High-Risk Path Review

- High-risk path touched: `core/kite_depth_ws.py`.
- Reason: feed/WebSocket subscription lifecycle is safety-sensitive and can affect feed freshness.
- Mitigation: change is limited to dynamic subscription mutation permission and explicit evidence; it does not alter broker/order paths, strategy logic, ranking, Phase2, or UI.
- Fail-closed behavior: mutation is blocked when the runtime is stopped, stopping, auth-blocked, import-missing, recovery-blocked, disconnected, or tick-stale.
- Preservation: initial on-connect subscription, normal non-terminal reconnect, and legitimate broad stale-window rebalance remain covered by tests.

## Closed Environment Rule

This is an offline code and test change. It does not require live market access or production execution.

## What Changed

- Added a pure helper to require broad stale breadth plus consecutive breached windows before allowing symbol-level subscription mutation.
- Added a websocket mutation guard that blocks dynamic subscribe/unsubscribe/set_mode when runtime or recovery state is unsafe.
- Increased the default stale-option drift refresh cooldown from 5 seconds to 45 seconds.
- Preserved initial on-connect subscription behavior and normal reconnect behavior.

## What Did Not Change

- No broker/order behavior.
- No live orders.
- No strategy/ranking/Phase2 changes.
- No dashboard/UI changes.
- No FeedTruth or candidate evidence contract rewrites.
- No WS1006 terminal process-restart semantics.

## Tests Run

- `PYTHONPATH=. pytest -q tests/test_kite_depth_ws_stability.py -vv`
- `PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py -vv`

## Validation Commands

- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `git diff --check`
- `git diff --name-only origin/main...HEAD > /tmp/pr491_changed_paths.txt`
- `PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr491_changed_paths.txt`

## Acceptance Proof

- `test_single_stale_token_does_not_refresh_full_symbol` proves one stale option token cannot fan out into full-symbol subscription mutation.
- `test_high_fresh_ratio_with_one_stale_symbol_logs_skip_reason` proves urgent diagnostics remain observable while mutation is skipped.
- `test_symbol_mutation_allowed_after_consecutive_broad_stale_windows` proves legitimate broad stale conditions can still mutate after hysteresis.
- `test_ensure_subscribed_tokens_skips_when_recovery_blocked`, `test_soft_resubscribe_skips_when_recovery_blocked`, and `test_apply_subscription_delta_skips_when_recovery_blocked` prove unsafe lifecycle states suppress dynamic websocket mutation.

## Runtime Proof Required After Merge

- Run a safe live audit and confirm `FEED_OPTION_PRUNE_REFRESH_SKIPPED` appears for narrow stale subsets without repeated `subscribe`/`unsubscribe` churn.
- Confirm initial connect still subscribes expected option tokens.
- Confirm broad stale symbol conditions still produce explicit mutation evidence only after the configured consecutive-window threshold.
- Confirm no broker/order calls occur.

## Expected Changed Files

- `core/kite_depth_ws.py`
- `tests/test_kite_depth_ws_stability.py`
- `docs/stale_option_refresh_churn_guard.md`

## Forbidden Scope Not Touched

- `strategies/*`
- `core/orchestrator.py`
- `core/engine_phase2_adapter.py`
- `core/runtime_execution_truth.py`
- `core/feed_truth_contract.py`
- `core/feed_truth_audit.py`
- `candidate_outcome*`
- `candidate_executability*`
- broker/order/execution files
- `dashboard/*`
- `runtime/*`
- `logs/*`
- `config/*`

## Risk Assessment

Low to moderate. The main risk is over-constraining mutation in edge cases where a broad stale condition should have been allowed. The guard is intentionally conservative and only applies to dynamic mutation paths.

## Rollback Plan

Revert `core/kite_depth_ws.py` and the two documentation/test files in this PR if the guard proves too strict. Because the change is isolated, rollback is straightforward.

## Why This Does Not Prove Trading Edge

This change only reduces feed subscription churn and improves evidence quality. It does not prove profit, predictive power, or execution edge.

## What This PR Does Not Prove

- It does not prove trading profitability.
- It does not prove quote quality under all broker/network conditions.
- It does not prove a strategy edge.
- It does not prove live order safety beyond preserving no-broker/no-order scope.

## Human Approval

- Required before merge because this touches feed websocket lifecycle code.
- Required before any live deployment or operational rollout.
- Required before changing any thresholds away from the conservative defaults documented in this PR.

## Future Work Out Of Scope

- Any relaxation of execution gates.
- Any strategy or ranking tuning.
- Any live trading rollout.
- Any websocket protocol redesign.
