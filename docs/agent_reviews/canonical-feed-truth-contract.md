# Canonical FeedTruth Contract

## Agent Work Contract
source_agent: GSD
action: GENERATE_PATCH
title: Canonical FeedTruth Contract
scope: Add a pure, immutable feed-truth contract module and deterministic tests without changing runtime consumers.
requested_paths: core/feed_truth_contract.py, tests/test_feed_truth_contract.py, docs/agent_reviews/canonical-feed-truth-contract.md
allowed_paths: core/feed_truth_contract.py, tests/test_feed_truth_contract.py, docs/agent_reviews/canonical-feed-truth-contract.md
forbidden_paths: core/kite_depth_ws.py, core/orchestrator.py, core/runtime_execution_truth.py, strategies/, core/broker*, core/order*, dashboard/
expected_tests: PYTHONPATH=. pytest -q tests/test_feed_truth_contract.py
acceptance_proof: The new contract fails closed on ambiguous input, dedupes blockers, excludes *_OK markers, and keeps quote/runtime blocked states from appearing healthy.

## Scope Guard
- In scope: a pure canonical FeedTruth model, pure derivation helpers, and tests that prove safety semantics.
- Out of scope: broker/order behavior, strategy logic, ranking, Phase2, UI, websocket reconnect behavior, latency thresholds, and runtime consumer rewiring.

## High-Risk Path Review
- This PR touches `core/` and adds safety-facing evidence only.
- No runtime wiring changes are included.
- No live execution, broker, or order paths are modified.

## Grill Me Review
- Weak assumption risk: a contract can drift from existing runtime naming if we do not keep the fields conservative.
- Failure mode: over-asserting “live” on partial input would hide feed problems.
- Missing proof: explicit tests for blocked, advisory, and ambiguous inputs.
- Verdict: acceptable only if the contract fails closed on missing/unsafe input and ignores *_OK markers.

## Hermes Review
- Scope pass/fail: PASS
- Boundary violations: none
- Files-not-to-touch check: PASS
- Verdict: additive contract only; no consumer rewiring in this PR.

## GSD Review
- delivery_verdict: PASS
- evidence_summary: New `FeedTruth` contract adds deterministic state derivation and test coverage for live, blocked, stale, disconnected, recovery-blocked, auth-blocked, import-missing, advisory, and unknown cases.
- next_action: Land the contract as a standalone evidence-first PR, then wire consumers in later steps if needed.

## QA / Safety Review
- The contract is pure and immutable.
- It does not call broker APIs, place orders, or change runtime behavior.
- It preserves fail-closed behavior for ambiguous input and blocked states.

## Acceptance Proof
- mode: feed_truth_contract
- candidate_id: canonical_feed_truth
- decision: add_pure_contract
- reason: unify_feed_truth_evidence_without_runtime_wiring
- timestamp: 2026-06-04T00:00:00+05:30
- is_order_action: false
- broker_api_called: false
- source: core/feed_truth_contract.py
- LIVE with trusted fresh input allows entries.
- DISCONNECTED blocks entries and untrusts quotes.
- STALE_OPTION_LTP blocks entries.
- RECOVERY_BLOCKED blocks entries and exposes terminal metadata.
- AUTH_BLOCKED and IMPORT_MISSING block entries and disallow reconnect.
- Duplicate blockers are deduped deterministically.
- LATENCY_GUARD_OK and other *_OK markers are excluded from blockers.

## Runtime Proof Required After Merge
- Re-run the contract tests and ensure existing feed/runtime and websocket safety suites still pass without any consumer rewiring.

## What This PR Does Not Prove
- It does not replace existing runtime feed truth consumers yet.
- It does not alter the websocket reconnect implementation.
- It does not change ranking, strategy, Phase2, or broker/order behavior.

## Human Approval
- Merge only after CI and evidence gates pass and the contract remains backward-compatible.
