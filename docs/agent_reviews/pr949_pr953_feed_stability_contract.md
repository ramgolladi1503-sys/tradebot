# PR #949–#953 Feed Stability Contract

## Agent Work Contract

- `source_agent: hermes` (Stage 1 design) followed by `source_agent: gsd` (Stage 2 scoped execution and verification).
- `action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS` for Stage 1; Stage 2 is limited to `PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS`.
- `title: Restore governed market-data subscription topology and remove depth retention work from the active persistence path`.
- `scope: PR #949 topology repair and its required stack through PR #953, including #950 health evidence, #951 exact subscription parity, and #952 recent-token feed diagnostics`.
- `requested_paths: core/depth_subscription_engine.py, core/kite_depth_ws.py, scripts/check_option_pipeline_health.py, scripts/run_market_event_graph_live_session_v1.py, core/subscription_truth_contract.py, core/feed_debug.py, core/depth_store.py, tests/test_kite_depth_ws_observation_on_ticks.py, tests/test_market_event_graph_live_observation_registry.py, tests/test_check_option_pipeline_health.py, tests/test_subscription_truth_contract.py, tests/test_feed_debug.py, tests/test_depth_store_accounting.py, docs/agent_reviews/pr949_pr953_feed_stability_contract.md`.
- `allowed_paths`: only the requested paths above. Any discovered failure outside those paths must be reported and must not be repaired as part of this scope without a new contract.
- `forbidden_paths`: credentials, environment files, broker/order/execution/risk/feed gate configuration, strategy thresholds, dashboards/UI, runtime data, and unrelated source or research artifacts.
- `expected_tests`: focused tests for the observation/option-universe boundary, exact parity and <=123 budget, health evidence at that topology, recent distinct-token diagnostics, idle-only depth pruning, then repository-required unit and health gates plus exact-head CI for each affected PR.
- `acceptance_proof`: preserve cash constituent identity as cash observation instruments; resolve options only for configured production indices; deduplicate the union and keep the configured 123-token cap; preserve stale/freshness/coverage and fail-closed behavior; prune only when the persistence queue is empty and no write is in flight; report exact tested SHA and all CI outcomes without treating skipped/cancelled checks as passes.

## Scope Guard

The intended topology remains approximately 51 observation instruments plus approximately 72 controlled index/option instruments, with a deduplicated final union capped at 123. The cap must not be increased, option minimums must not be reduced, and constituent observation must remain enabled. This repairs universe construction; it does not redefine which individual option quotes are fresh or whether a feed is ready.

Depth retention pruning may run only when queued persistence work is zero and in-flight persistence work is zero. Queue size, timeouts, batching, sampling, durability, and rejection semantics remain unchanged. Recent-token debug evidence is read-only and bounded to its configured time window; missing/unreadable evidence remains fail-closed.

No broker API calls or order actions are permitted. `read_only=true` for evidence inspection; `is_order_action=false`; `broker_api_called=false`; `allowed_for_live_execution=false`; `append=false` for read-only contract/evidence inspection.

## Grill Me Review

Adversarial checks: ensure no constituent ticker is passed to generic option resolution; no observation token is silently omitted from the final union; no hard-coded count substitutes for authoritative token identity; no parity check treats missing evidence as equality; no one stale token is hidden by the count repair; no pruning starts while work is queued or in flight; and no failure path silently claims health or durability.

## Hermes Review

Stage 1 design is to keep the two input authorities separate: the configured index production symbols go through option resolution, while the authoritative constituent registry contributes cash observation tokens through its existing identity-preserving path. The final subscription set is deduplicated and constrained by the existing 123-token budget. Subscription authority, desired tokens, registered tokens, and observed token activity remain distinct evidence states.

The persistence worker's idle condition is the conjunction `queue_depth == 0 && in_flight == 0`. A false or unavailable measurement must not authorize pruning. Debug token counts remain diagnostic evidence and do not grant readiness or execution authority.

## GSD Review

Stage 2 execution is authorized only inside the allowed paths. Implement the existing contract, add behavior assertions for positive and negative cases, run the required focused and repository gates, and capture commit SHA plus check outcomes. Do not change acceptance thresholds or rewrite unrelated failing tests. Failures on unrelated baseline tests remain visible and block merge readiness until correctly resolved within scope or classified as external blockers.

## QA / Safety Review

Required negative cases include: constituent option resolution is absent; exceeding the configured token cap is not represented as a successful exact-parity state; stale or missing-token evidence is not converted to healthy; recent-token queries exclude old and future timestamps; pruning is denied for queued work and for in-flight work; read-only diagnostics issue no writes or broker calls. Existing risk, freshness, identity, coverage, and kill-switch gates are invariant.

## Acceptance Proof

- Focused tests prove the separated cash-observation and index-option universes, final deduplicated <=123 topology, exact subscription parity, health evidence, bounded recent-token counts, and queue-idle pruning.
- Required full unit and health gates pass on each affected PR's exact head. Skipped, cancelled, stale-SHA, or partial CI is not a pass.
- No change expands broker/order/live authority or weakens a feed safety gate.
- Runtime topology and feed freshness still require post-merge read-only runtime proof; offline tests alone do not establish live behavior.

## Runtime Proof Required After Merge

Before any operational claim, capture read-only evidence for authority, desired, registered, and observed token sets and their counts; verify the exact token identity mapping and configured cap; inspect per-token freshness and option-health outcomes; and record process SHA/config identity. Do not call a broker or alter subscriptions as part of this PR validation.

## What This PR Does Not Prove

This work does not prove that every option is fresh, that the upstream feed delivered every event, that one/two stale options no longer affect readiness, that websocket queue pressure is resolved in production, or that trading is permitted. It does not introduce market recording or replay infrastructure. It does not authorize a merge or deployment.

## Human Approval

The user authorized auditing and repairing the identified open PR work toward merge readiness. This contract does not authorize merging, deployment, broker access, order actions, credential changes, or safety-gate changes. Human approval remains required for merge and for any runtime/live operation.

## High-Risk Path Review

`core/kite_depth_ws.py` is a high-risk feed/WebSocket path. Review is limited to preserving constituent cash identity outside generic option resolution, enforcing the existing configured subscription budget, and retaining existing freshness, coverage, and fail-closed checks. No broker API, order, risk, credential, or live-mode behavior is added. The isolated tests must verify both included observation tokens and excluded constituent-option expansion.
