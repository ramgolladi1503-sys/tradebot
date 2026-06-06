# Stale Option Mutation Guard Tightening

mode: REVIEW
candidate_id: PR-STALE-OPTION-MUTATION-GUARD-TIGHTENING
decision: tighten_stale_option_mutation_guard
reason: Prevent stale-option diagnostics from triggering websocket subscription churn when mutation guard conditions are not eligible, while keeping diagnostics visible and fail-closed feed safety intact.
timestamp: 2026-06-06T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/stale-option-mutation-guard-tightening.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (stale-option mutation guard tightening + deterministic regression tests + review doc)
title: Stale Option Mutation Guard Tightening
scope: suppress stale-option driven websocket subscription churn when mutation guard is not eligible, while preserving diagnostics and fail-closed feed safety
requested_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_kite_depth_restart.py
  - docs/agent_reviews/stale-option-mutation-guard-tightening.md
allowed_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_kite_depth_restart.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/runtime_execution_truth.py
  - core/orchestrator.py
  - core/review_queue.py
  - core/feed_truth_contract.py
  - core/broker*
  - core/order*
  - strategies/*
  - dashboard/*
  - runtime/live*
  - logs/*
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_kite_depth_ws_stability.py -vv
  - PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py -vv
  - PYTHONPATH=. pytest -q tests/test_feed_runtime_states.py tests/test_feed_truth_contract.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr494_changed_paths.txt
acceptance_proof:
  - mutation_guard_ok=false suppresses stale-option rebalance application
  - stale-option diagnostics remain visible in skip evidence
  - tiny stale subsets do not trigger full-symbol mutation
  - broad stale windows can still mutate after hysteresis and cooldown when runtime is safe
  - initial on-connect subscribe behavior is unchanged
  - terminal WS1006 recovery behavior remains fail-closed and does not retry in-process
```

## Scope Guard

- This PR is off-market and read-only.
- It must not alter strategy logic, ranking math, Phase 2 behavior, broker calls, order behavior, or dashboard/UI behavior.
- It must preserve stale-feed safety, recovery-blocked safety, and fail-closed behavior.

## Grill Me Review

- Stale-option diagnostics must stay visible even when mutation is skipped.
- Mutation suppression must not become a hidden blanket ban on all websocket activity.
- Skip reasons must be explicit and deterministic so we can audit churn reduction.

## Hermes Review

- The mutation guard decision belongs at the stale-option mutation boundary, not in strategy or ranking paths.
- The new skip helper keeps the decision observable without changing higher-level trading logic.
- Legitimate broad-stale recovery remains available once hysteresis and cooldown are satisfied.

## GSD Review

- Changes are limited to `core/kite_depth_ws.py` plus narrow regression tests.
- The patch does not change strategy candidate generation, execution truth, ranking, or Phase 2 behavior.
- The new tests prove both suppression and allowed mutation paths.

## QA / Safety Review

- `read_only=true`, `append=false`, `is_order_action=false`, and `broker_api_called=false` remain enforced in the evidence paths.
- `mutation_guard_ok=false` must skip stale-option driven rebalance application.
- `FEED_REBALANCE_SKIPPED` must remain explicit and explainable.
- Terminal WS1006 behavior must still fail closed with `RECOVERY_BLOCKED` and `process_restart_required=true`.

## High-Risk Path Review

- `core/kite_depth_ws.py` is a high-risk feed lifecycle path, so the patch is intentionally narrow and only changes stale-option mutation gating and skip evidence.
- The patch does not change broker/order paths, strategy formulas, ranking math, or Phase 2 behavior.
- The added regression tests prove the guard can block unsafe churn without breaking initial subscribe or terminal WS1006 recovery semantics.

## Evidence

- Post-merge evidence showed `FEED_OPTION_PRUNE_REFRESH_SKIPPED` with `mutation_guard_ok=false`, but nearby rebalance activity was still possible.
- The remaining churn risk is stale-option driven subscription mutation, not strategy or ranking behavior.
- The live feed must preserve diagnostics while refusing unsafe subscription mutation.

## Root Cause

- Stale-option diagnostics were able to proceed far enough that later subscription mutation paths could still apply rebalances in the same cycle.
- The guard decision existed, but it was not authoritative at the point where later mutation logic decided whether to apply a rebalance.

## Fix

- Treat stale-option mutation guard failure as authoritative for stale-option driven subscription mutation.
- Emit skip evidence with symbol counts, freshness metrics, and guard reasons.
- Suppress rebalance application when stale-option mutation is not eligible.
- Keep initial connection behavior and terminal WS1006 recovery behavior unchanged.

## Safety Constraints

- No broker/order changes.
- No live orders.
- No strategy changes.
- No ranking/scoring changes.
- No Phase 2 behavior changes.
- No dashboard/UI changes.
- No stale-feed relaxation.
- No risk gate relaxation.
- No weakening FeedTruth.
- No weakening RECOVERY_BLOCKED/process_restart_required behavior.
- No in-process retry after terminal WS1006.

## Tests Run

- `PYTHONPATH=. pytest -q tests/test_kite_depth_ws_stability.py -vv`
- `PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py -vv`
- `PYTHONPATH=. pytest -q tests/test_feed_runtime_states.py tests/test_feed_truth_contract.py -vv`

## Acceptance Proof

- `mutation_guard_ok=false` suppresses stale-option rebalance application.
- `FEED_REBALANCE_SKIPPED` remains explicit with stale-count, fresh-count, fresh-ratio, and per-symbol skip reasons.
- Tiny stale subsets do not trigger full-symbol mutation.
- Broad stale windows can still mutate after hysteresis and cooldown when the websocket runtime is safe.
- Initial on-connect subscribe behavior is unchanged.
- Terminal WS1006 recovery still suppresses in-process retry and remains `RECOVERY_BLOCKED`.

## Runtime Proof Required After Merge

- Re-run the stability and restart suites against a fresh live session.
- Confirm `FEED_OPTION_PRUNE_REFRESH_SKIPPED` and `FEED_REBALANCE_SKIPPED` appear where mutation is not eligible.
- Confirm `FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh` is reduced or absent when the guard is false.
- Confirm there is no `Starting factory`, `ReactorNotRestartable`, or in-process reconnect loop after terminal WS1006.

## What This PR Does Not Prove

- It does not prove trading edge, profitability, or strategy quality.
- It does not change live order placement or broker behavior.
- It does not alter ranking math or Phase 2 behavior.

## What Was Not Changed

- Strategy candidate generation.
- Ranking and scoring math.
- Phase 2 behavior.
- Broker/order paths.
- Dashboard/UI paths.
- FeedTruth contract semantics.
- Terminal WS1006 recovery semantics.

## Remaining Risks

- This is a live feed lifecycle path, so over-tightening mutation suppression could delay useful subscription churn.
- We specifically keep broad-stale, hysteresis-qualified, cooldown-qualified mutation available to avoid freezing legitimate recovery behavior.

## Next Market Validation Signals

- `FEED_OPTION_PRUNE_REFRESH_SKIPPED`
- `FEED_REBALANCE_SKIPPED`
- `mutation_skipped_symbols`
- `mutation_skip_reason_by_symbol`
- reduced `FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh`
- no `Starting factory`
- no `ReactorNotRestartable`
- no in-process retry loop after terminal WS1006
- candidate supply can survive longer if feed remains connected

## Rollback Plan

- Revert the guard-skip helper and the stale-option rebalance suppression branch.
- Remove the added regression tests only after confirming the previous churn behavior is still undesirable.

## Why This Does Not Prove Trading Edge

- It only improves feed lifecycle safety and evidence quality.
- It does not change strategy formulas, ranking math, or execution selection edge.
- It does not place or modify any order.

## Human Approval

This is safe to review as a narrow stale-option mutation guard tightening patch.
