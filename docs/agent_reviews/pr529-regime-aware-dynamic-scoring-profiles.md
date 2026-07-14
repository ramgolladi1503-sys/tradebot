# PR #529 — Regime-Aware Dynamic Scoring Profiles

mode: PAPER
candidate_id: pr529-regime-aware-dynamic-scoring-profiles
signal_id: pr529-regime-aware-dynamic-scoring-profiles
strategy_id: regime_scoring_profile_contract
decision: REVIEW_ONLY
reason: read_only_regime_profile_safety_flags_locked
timestamp: 2026-06-08T15:45:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr529-regime-aware-dynamic-scoring-profiles.md

## Agent Work Contract

This PR tightens the existing read-only regime-aware scoring profile contract by adding explicit non-broker and non-live-order safety flags to the serialized profile output.

The work is intentionally limited to profile contract safety and focused tests. It does not wire profiles into live scoring, ranking, strategy generation, broker paths, feed behavior, dashboard behavior, execution gates, or runtime orchestration.

## Scope Guard

In scope:

- Preserve the existing `core/regime_scoring_profiles.py` resolver behavior.
- Add explicit `broker_api_called=False` to `RegimeScoringProfile`.
- Add explicit `live_order_action=False` to `RegimeScoringProfile`.
- Add explicit `broker_order_action=False` to `RegimeScoringProfile`.
- Add a focused safety serialization test.
- Add this agent-review evidence document.

Out of scope:

- No broker calls.
- No order actions.
- No live execution behavior.
- No strategy generation behavior changes.
- No feed or depth subscription changes.
- No scoring formula cutover.
- No ranking behavior changes.
- No dashboard/UI changes.
- No runtime wiring of regime profiles.

## Grill Me Review

The main risk is accidentally treating the regime profile as active scoring logic. This PR avoids that by preserving the existing read-only resolver scope and not wiring it into `score_opportunities(...)` or ranking.

The second risk is having advisory profile evidence that lacks explicit broker/order safety flags. This PR fixes that by serializing the same false safety fields used by other read-only evidence objects.

The third risk is broadening the PR into scoring behavior. This PR does not change score calculation or ranking consumption.

## Hermes Review

Task boundary stayed narrow.

Changed files:

- `core/regime_scoring_profiles.py`
- `tests/test_regime_scoring_profile_safety_flags.py`
- `docs/agent_reviews/pr529-regime-aware-dynamic-scoring-profiles.md`

The PR is contract-only. It does not touch runtime startup, broker adapters, feed/WebSocket code, dashboard code, strategy modules, execution engine, risk engine, order paths, or ranking consumers.

## GSD Review

This PR improves safety evidence around regime-aware scoring profiles.

The repo already had deterministic profile resolution. The miss-ing part was explicit serialization proof that the object remains read-only and non-broker. This PR locks that contract before any later PR consumes the profile in scoring or ranking.

## QA / Safety Review

Safety properties covered:

- Profile serialization remains `read_only=True`.
- Profile serialization remains `append=False`.
- Profile serialization remains `is_order_action=False`.
- Profile serialization now includes `broker_api_called=False`.
- Profile serialization now includes `live_order_action=False`.
- Profile serialization now includes `broker_order_action=False`.
- No runtime wiring is added.
- No broker or order imports are added.

No high-risk path review is required because this PR does not change config, auth, feed/WebSocket, orchestrator, execution, risk, or strategies.

## Acceptance Proof

Focused commands:

```bash
PYTHONPATH=. pytest tests/test_regime_scoring_profiles.py
PYTHONPATH=. pytest tests/test_regime_scoring_profile_safety_flags.py
```

Expected proof:

- Existing regime profile behavior remains green.
- Safety flag serialization is explicit and false for broker/order/live-order fields.
- Profile resolver remains read-only and advisory.

CI gates to satisfy:

- Agent Review Evidence Gate.
- Code Excellence Gates / Minerva / Evidence / Cerberus.
- Existing unit test workflows.

## Runtime Proof Required After Merge

No runtime proof is required to validate broker/feed behavior because this PR does not wire regime profiles into runtime execution, broker calls, feed subscriptions, dashboard, or order paths.

Future runtime proof is required only when a later PR consumes regime profiles in scoring or ranking.

## What This PR Does Not Prove

This PR does not prove trading edge.

It does not prove score profitability.

It does not prove ranking quality.

It does not prove runtime candidate improvement.

It does not prove feed recovery.

It only proves regime profile evidence now serializes explicit read-only and non-broker safety flags.

## Human Approval

Human approval is required before merge.

Do not merge only because the PR is green. Review that this remains contract-only and does not silently alter score calculation, ranking, runtime behavior, or execution behavior.


## High-Risk Path Review

N/A
