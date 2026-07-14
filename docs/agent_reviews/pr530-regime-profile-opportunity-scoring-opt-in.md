# PR #530 — Regime Profile Consumption in Opportunity Scoring

mode: PAPER
candidate_id: pr530-regime-profile-opportunity-scoring-opt-in
signal_id: pr530-regime-profile-opportunity-scoring-opt-in
strategy_id: opportunity_scoring_profile_opt_in
decision: REVIEW_ONLY
reason: read_only_opt_in_regime_profile_scoring_path_added
timestamp: 2026-06-08T16:20:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr530-regime-profile-opportunity-scoring-opt-in.md

## Agent Work Contract

This PR adds an opt-in path for opportunity scoring to consume regime-aware component weights.

The default scoring path remains unchanged. The new behavior is active only when a caller explicitly passes a scoring profile or component-weight mapping.

## Scope Guard

In scope:

- Add optional `scoring_profile` argument to `score_opportunities(...)`.
- Add optional `component_weights` argument to `score_candidate(...)`.
- Preserve fixed `COMPONENT_WEIGHTS` when no profile is passed.
- Accept a read-only regime profile object with `adjusted_component_weights`.
- Accept an explicit component-weight mapping.
- Normalize and validate profile weights.
- Add safety serialization fields to `OpportunityScoreReport`.
- Add focused opt-in tests.

Out of scope:

- No broker calls.
- No order actions.
- No live execution behavior.
- No strategy generation behavior changes.
- No feed or depth subscription changes.
- No ranking cutover.
- No dashboard/UI changes.
- No runtime wiring.

## Grill Me Review

The main risk is silently changing existing scoring. This PR prevents that by making profile consumption opt-in only and testing that the default path keeps fixed `COMPONENT_WEIGHTS`.

The second risk is accepting malformed profile weights. This PR validates component shape and rejects mismatched profiles.

The third risk is pretending profile scoring proves trading edge. It does not. It only changes read-only score composition when explicitly requested.

## Hermes Review

Task boundary stayed narrow.

Changed files:

- `core/opportunity_scoring.py`
- `tests/test_opportunity_scoring_regime_profile_opt_in.py`
- `docs/agent_reviews/pr530-regime-profile-opportunity-scoring-opt-in.md`

The PR does not touch runtime startup, broker adapters, feed/WebSocket code, dashboard code, strategy modules, execution engine, risk engine, order paths, or ranking consumers.

## GSD Review

This PR turns the previously locked regime profile contract into an explicit scoring input without forcing any runtime consumer to use it.

It improves correctness because score records can now show whether regime weights were applied, which profile was used, and what component weights created the final score.

## QA / Safety Review

Safety properties covered:

- Default scoring path remains fixed-weight.
- Profile scoring is opt-in only.
- Profile component weights are recorded in report metadata and score breakdown.
- Invalid profile component shape is rejected.
- Score report serialization includes `read_only=True`.
- Score report serialization includes `append=False`.
- Score report serialization includes `is_order_action=False`.
- Score report serialization includes `broker_api_called=False`.
- Score report serialization includes `live_order_action=False`.
- Score report serialization includes `broker_order_action=False`.

No high-risk path review is required because this PR does not change config, auth, feed/WebSocket, orchestrator, execution, risk, strategies, ranking, or dashboard runtime.

## Acceptance Proof

Focused commands:

```bash
PYTHONPATH=. pytest tests/test_opportunity_scoring.py
PYTHONPATH=. pytest tests/test_opportunity_scoring_regime_profile_opt_in.py
```

Expected proof:

- Existing opportunity scoring behavior remains green.
- Default scoring report keeps fixed `COMPONENT_WEIGHTS`.
- Explicit regime profile changes only the opt-in score path.
- Explicit component-weight mapping works when complete.
- Invalid component mapping fails closed.
- Score report safety flags remain explicit and false for broker/order/live-order fields.

CI gates to satisfy:

- Agent Review Evidence Gate.
- Code Excellence Gates / Minerva / Evidence / Cerberus.
- Existing unit test workflows.

## Runtime Proof Required After Merge

No runtime proof is required to validate broker/feed behavior because this PR does not wire regime profile scoring into runtime execution, broker calls, feed subscriptions, dashboard, or order paths.

Future runtime proof is required only when a later PR wires profile scoring into ranking or runtime candidate selection.

## What This PR Does Not Prove

This PR does not prove trading edge.

It does not prove ranking quality.

It does not prove runtime candidate improvement.

It does not prove strategy quality.

It does not prove feed recovery.

It only proves opportunity scoring can consume regime-aware component weights through an explicit, read-only opt-in path.

## Human Approval

Human approval is required before merge.

Do not merge only because the PR is green. Review that default scoring remains unchanged and no runtime/ranking cutover was introduced.


## High-Risk Path Review

N/A
