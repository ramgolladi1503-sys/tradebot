# Runtime Execution Truth Consumes FeedTruth

## Agent Work Contract
source_agent: GSD
action: GENERATE_PATCH
title: Runtime Execution Truth Consumes FeedTruth
scope: Migrate runtime execution truth/evidence to consume the new pure FeedTruth contract without changing websocket reconnect behavior, strategy logic, ranking, Phase2, broker/order, or UI.
requested_paths: core/runtime_execution_truth.py, tests/test_runtime_execution_truth_evidence.py, docs/agent_reviews/runtime-execution-truth-consumes-feedtruth.md
allowed_paths: core/runtime_execution_truth.py, tests/test_runtime_execution_truth_evidence.py, docs/agent_reviews/runtime-execution-truth-consumes-feedtruth.md
forbidden_paths: core/kite_depth_ws.py, core/orchestrator.py, core/feed_truth_contract.py, strategies/, core/broker*, core/order*, dashboard/
expected_tests: PYTHONPATH=. pytest -q tests/test_runtime_execution_truth_evidence.py
acceptance_proof: FeedTruth becomes the decision source for runtime execution truth while preserving fail-closed behavior and backwards-compatible blocker labels.

## Scope Guard
- In scope: runtime execution truth reads FeedTruth in a read-only way and uses it for blocking/advisory/executable decisions.
- Out of scope: websocket reconnect logic, feed runtime writers, strategy/ranking/Phase2, broker/order placement, and dashboard/UI.

## High-Risk Path Review
- This PR touches safety-sensitive execution truth only.
- The change is additive/stricter: it does not loosen any existing blocked state or safety guard.
- No live execution or broker behavior is changed.

## Grill Me Review
- Weak assumption risk: if FeedTruth is absent or ambiguous, the runtime must fail closed rather than guessing.
- Failure mode: a consumer migration could accidentally overwrite legacy blocker labels; this PR keeps the legacy blocker vocabulary where possible.
- Missing proof: disconnected, recovery-blocked, stale, auth-blocked, import-missing, and unknown cases must all be covered.
- Verdict: acceptable only if tests prove blocked candidates remain non-reportable and blocker lists remain deterministic.

## Hermes Review
- Scope pass/fail: PASS
- Boundary violations: none
- Files-not-to-touch check: PASS
- Verdict: narrow consumer migration only; no websocket or strategy wiring.

## GSD Review
- delivery_verdict: PASS
- evidence_summary: Runtime execution truth now derives its entry/blocking decision from canonical FeedTruth while preserving conservative blocker output and backward-compatible blocked/advisory/executable behavior.
- next_action: Land the consumer migration, then consider later PRs for other feed/runtime consumers if needed.

## QA / Safety Review
- The migration is read-only and fail-closed.
- It does not call broker APIs or place orders.
- It keeps recovery-blocked, disconnected, stale, auth-blocked, and import-missing paths blocked.

## Acceptance Proof
- mode: runtime_execution_truth_migration
- candidate_id: feedtruth_consumer_runtime_truth
- decision: consume_feedtruth_for_truth_decision
- reason: unify_runtime_execution_truth_with_canonical_feedtruth
- timestamp: 2026-06-04T00:00:00+05:30
- is_order_action: false
- broker_api_called: false
- source: core/runtime_execution_truth.py
- `FeedTruth.entries_allowed == false` blocks reportable executable output.
- `FeedTruth.state == DISCONNECTED|RECOVERY_BLOCKED|AUTH_BLOCKED|IMPORT_MISSING|STALE|UNKNOWN` fails closed.
- Duplicate blockers remain deduped.
- `_OK` markers and `LATENCY_GUARD_OK` stay excluded from blockers.

## Runtime Proof Required After Merge
- Re-run the runtime execution truth evidence suite and confirm blocked candidates never regain executable/reportable truth.

## What This PR Does Not Prove
- It does not replace other feed consumers yet.
- It does not change websocket reconnect behavior.
- It does not change strategy/ranking/Phase2/broker/order/UI behavior.

## Human Approval
- Merge only after CI and evidence gates pass and the migration remains backward-compatible.
