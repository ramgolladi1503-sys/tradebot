# Runtime Feed Stabilization and Canonical FeedTruth State Machine

## Traceability Fields
- mode: REVIEW
- candidate_id: PR-524-RUNTIME-FEED-STABILIZATION-CANONICAL-FEEDTRUTH
- decision: canonical_feed_truth_state_machine_and_current_session_rca
- reason: Canonical current-session feed truth must fail closed and override stale tail feed churn without changing runtime trading behavior.
- timestamp: 2026-06-08T14:45:45+05:30
- is_order_action: false
- broker_api_called: false
- source: docs/agent_reviews/runtime-feed-stabilization-canonical-feedtruth.md

## Delivery Summary
- purpose: Canonical current-session FeedTruth state machine and consumers for runtime gating and RCA.
- scope: Fail closed until current-session feed truth is VERIFIED_HEALTHY; preserve stale historical evidence as diagnostics only.
- files_changed:
  - core/feed_runtime.py
  - core/kite_depth_ws.py
  - core/orchestrator.py
  - core/latency_guard.py
  - core/review_queue.py
  - core/agents/readers.py
  - core/agents/feed_stability_agent.py
  - core/agents/live_rca_agent.py
  - core/agents/command_center.py
  - tests/test_feed_runtime_state_machine.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_orchestrator_reconciliation_startup.py
  - tests/test_orchestrator_pilot_feed_ok.py
  - tests/test_latency_guard.py
  - tests/test_review_queue_persistence.py
  - tests/test_agent_command_center.py
  - tests/test_feed_stability_agent.py
  - tests/test_live_rca_agent.py
- tests_or_reason_not_required: deterministic runtime/feed/agent regressions were required and executed.
- evidence:
  - canonical_feed_truth is published alongside the legacy runtime snapshot
  - orchestrator skips TradeBuilder/Phase2 until canonical feed truth is healthy
  - latency guard consumes canonical feed truth and blocks cleanly
  - review queue isolates stale previous-session rows
  - feed stability, live RCA, and command center prefer current-session truth
- risks:
  - accidental legacy-field regression if canonical truth is ever used as a replacement instead of an additive payload
  - overly conservative DEGRADED/RESTART_REQUIRED classification if runtime facts are missing
- next_pr: runtime-feed stabilization PR validation / merge only after gates pass

## Agent Work Contract
- source_agent: GSD
- action: IMPLEMENT_PR
- title: Runtime Feed Stabilization and Canonical FeedTruth State Machine
- scope: Introduce a canonical current-session FeedTruth state machine and consume it from orchestrator, latency guard, review queue isolation, and RCA agents.
- requested_paths:
  - core/feed_runtime.py
  - core/kite_depth_ws.py
  - core/orchestrator.py
  - core/latency_guard.py
  - core/review_queue.py
  - core/agents/readers.py
  - core/agents/feed_stability_agent.py
  - core/agents/live_rca_agent.py
  - core/agents/command_center.py
  - tests/test_feed_runtime_state_machine.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_orchestrator_reconciliation_startup.py
  - tests/test_orchestrator_pilot_feed_ok.py
  - tests/test_latency_guard.py
  - tests/test_review_queue_persistence.py
  - tests/test_agent_command_center.py
  - tests/test_feed_stability_agent.py
  - tests/test_live_rca_agent.py
- allowed_paths:
  - core/feed_runtime.py
  - core/kite_depth_ws.py
  - core/orchestrator.py
  - core/latency_guard.py
  - core/review_queue.py
  - core/agents/readers.py
  - core/agents/feed_stability_agent.py
  - core/agents/live_rca_agent.py
  - core/agents/command_center.py
  - tests/test_feed_runtime_state_machine.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_orchestrator_reconciliation_startup.py
  - tests/test_orchestrator_pilot_feed_ok.py
  - tests/test_latency_guard.py
  - tests/test_review_queue_persistence.py
  - tests/test_agent_command_center.py
  - tests/test_feed_stability_agent.py
  - tests/test_live_rca_agent.py
- forbidden_paths:
  - strategies/*
  - core/candidate_scoring.py
  - core/expectancy/*
  - dashboard/*
  - broker/order/execution files
  - websocket runtime behavior files beyond canonical feed truth wiring

## Scope Guard
- No strategy generation changes.
- No scoring/ranking changes.
- No Phase2 math/filtering changes.
- No dashboard/UI changes.
- No broker/order placement or live order changes.
- No threshold changes.
- Fail closed when current-session feed truth is not VERIFIED_HEALTHY.
- Preserve stale historical evidence as diagnostics only.
- Keep legacy runtime snapshot fields backward compatible.

## Grill Me Review
- The main risk is accidentally overriding legacy `feed_truth_state` fields in runtime snapshots and breaking existing feed-runtime contracts.
- Another risk is letting session isolation leak into current-session executable rows.
- The implementation keeps the canonical state as an adjacent payload and isolates stale rows only when session IDs differ.
- Historical feed churn remains visible in RCA; it no longer dominates when the current session is healthy.

## Hermes Review
- Canonical FeedTruth is modeled as a small explicit state machine with restart-required artifact support.
- Orchestrator gating uses the canonical state to stop TradeBuilder/Phase2 until the feed is healthy.
- Latency guard consumes canonical feed truth and fails closed with FEED_BLOCKED when the feed is unhealthy.
- Feed and RCA agents prefer canonical current-session evidence while preserving stale tail diagnostics.

## GSD Review
- Implemented `core/feed_runtime.py` as the canonical state machine.
- Wired `core/kite_depth_ws.py` to publish canonical feed truth into runtime snapshots without breaking legacy top-level feed state.
- Gated orchestrator entry on canonical feed health.
- Added feed-aware latency-guard blocking.
- Added review-queue stale-session isolation.
- Added reader/helper support plus feed-stability, live-RCA, and command-center canonical feed truth consumption.

## QA / Safety Review
- Read-only evidence remains read-only.
- `is_order_action=false`, `broker_api_called=false`, and `read_only=true` remain intact in canonical payloads.
- Restart-required writes a restart artifact and does not enable trading.
- Stale previous-session rows are marked historical_only / non-reportable.
- Existing regression tests were preserved where legacy feed-runtime fields still matter.

## Acceptance Proof
- `PYTHONPATH=. pytest -q tests/test_feed_runtime_state_machine.py tests/test_kite_depth_ws_stability.py tests/test_orchestrator_reconciliation_startup.py tests/test_orchestrator_pilot_feed_ok.py tests/test_latency_guard.py tests/test_review_queue_persistence.py tests/test_agent_command_center.py tests/test_feed_stability_agent.py tests/test_live_rca_agent.py -vv`
- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `git diff --check`
- `PYTHONPATH=. python scripts/run_unified_ce_gates.py`
- `git diff --name-only origin/main...HEAD | grep -E '^strategies/' || true` returned no paths.

## Runtime Proof Required After Merge
- Validate that live snapshots continue to write both legacy feed fields and `canonical_feed_truth`.
- Validate that TradeBuilder and Phase2 stay gated until current-session feed truth is VERIFIED_HEALTHY.
- Validate that current-session feed health suppresses stale-tail RCA recommendations.
- Validate that previous-session review-queue rows remain historical_only and non-reportable.

## What This PR Does Not Prove
- It does not prove durable market edge.
- It does not rewrite strategy generation or ranking quality.
- It does not prove broker connectivity beyond existing fail-closed guards.
- It does not change or validate live order behavior.
- It does not relax any feed freshness or recovery safety gates.

## High-Risk Path Review
- `core/kite_depth_ws.py`: canonical feed truth is additive only; legacy snapshot fields remain backward compatible.
- `core/orchestrator.py`: gating is fail-closed and only blocks trade-builder/Phase2 until feed truth is VERIFIED_HEALTHY.
- `core/latency_guard.py`: feed-blocked state prevents noisy HALT_ALL oscillation.
- `core/review_queue.py`: stale-session rows are isolated as historical_only and cannot become current-session executable truth.
- `core/agents/*`: RCA layers now prefer canonical current-session truth and keep stale tail evidence diagnostic-only.

## Human Approval
- Approved for implementation with the explicit constraint that canonical feed truth must remain additive and fail-closed.
- High-risk paths were reviewed narrowly: `core/kite_depth_ws.py`, `core/orchestrator.py`, `core/latency_guard.py`, `core/review_queue.py`, and agent RCA consumers.
- No forbidden strategy, ranking, Phase2, broker, or dashboard files were touched.
