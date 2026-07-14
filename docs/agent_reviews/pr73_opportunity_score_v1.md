# Agent Review — PR73 Opportunity Score V1

## Evidence Trace Fields

mode: PAPER
candidate_id: PR73_OPPORTUNITY_SCORE_V1
candidate_id: pr73_opportunity_score_v1
source: docs/agent_reviews/pr73_opportunity_score_v1.md
decision: FIX_NOW
reason: roadmap_pr73_score_contract_evidence
reason: deterministic_read_only_score_contract_without_ranking_or_selection
timestamp: 2026-05-25T18:25:00Z
is_order_action: false
broker_api_called: false

## Agent Work Contract

Roadmap item: PR73 — Opportunity Score V1.

The uploaded roadmap places PR73 immediately after the candidate truth layer and
before regime-aware scoring profiles, directional balance, ranking, runtime
wiring, safety gates, risk, feedback, and ML.

## Scope Implemented

- Added a read-only opportunity score contract.
- Added deterministic score components and weighted contribution breakdowns.
- Added score-compression warning evidence.
- Added tests for ready, advisory, blocked, compression, and read-only behavior.

## Scope Guard

This PR intentionally does not add:

- ranking;
- top candidate selection;
- directional balancing;
- regime-aware profiles;
- runtime orchestration;
- dashboard/UI changes;
- broker calls;
- paper/live order behavior;
- risk sizing or allocation.

## Grill Me Review

Challenge: Is this fake precision?

Answer: The score is deterministic and transparent. It exposes component scores,
weights, and compression warnings. It does not claim profitability, does not rank,
and does not select candidates.

Challenge: Can blocked candidates become attractive because of scoring?

Answer: Blocked or malformed decisions are forced to score `0.0` and are placed
in `blocked_scores`.

Challenge: Does advisory evidence become executable?

Answer: Advisory-only decisions are capped and remain only scored evidence.
The contract produces no execution intent.

## Hermes Review

The payload includes read-only/non-action markers:

- `read_only=True`
- `append=False`
- `is_order_action=False`
- `broker_api_called=False`

Metadata explicitly states that the PR does not rank, select, wire runtime, call
brokers, or allocate capital.

## GSD Review

This PR is small, deterministic, test-covered, and roadmap-aligned. It creates
the scoring contract needed before PR74/PR75/PR76 can safely proceed.

## QA / Safety Review

- Negative path: empty input fails closed with `opportunity_score_empty_input`.
- Negative path: invalid readiness summary forces blocked scores.
- Negative path: blocked candidates receive `0.0` score and stay out of scores.
- Safety path: payload explicitly emits non-action markers.

## What This PR Proves

- Score components exist and are exposed.
- Score breakdown is deterministic.
- Score compression is visible.
- Blocked candidates cannot receive positive score.
- Advisory candidates are capped.
- The contract is read-only and non-actionable.

## What This PR Does Not Prove

- It does not prove strategy profitability.
- It does not prove ranking quality.
- It does not prove live execution readiness.
- It does not validate broker payloads.
- It does not allocate capital.
- It does not implement regime-aware profile weighting.

## Acceptance Proof

Required command:

```bash
PYTHONPATH=. python -m pytest \
  tests/test_pr73_opportunity_score_v1.py \
  tests/test_edge_73_candidate_readiness_summary.py \
  tests/test_edge_72_hard_downgrade_engine.py \
  tests/test_edge_71_candidate_classification_layer.py
```

## Acceptance Evidence

```bash
PYTHONPATH=. python -m pytest \
  tests/test_pr73_opportunity_score_v1.py \
  tests/test_edge_73_candidate_readiness_summary.py \
  tests/test_edge_72_hard_downgrade_engine.py \
  tests/test_edge_71_candidate_classification_layer.py
```

## Runtime Proof Required After Merge

Runtime proof is not required for PR73 because this PR does not wire runtime,
dashboard, broker, paper order, or live order behavior. Runtime proof becomes
relevant in later roadmap PRs that explicitly wire ranking or runtime evidence.

## Human Approval

Human approval required before merge: yes.

Approval status: pending repository owner review.


## High-Risk Path Review

N/A
