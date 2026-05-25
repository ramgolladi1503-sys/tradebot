# Agent Review — PR73 Opportunity Score V1

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

Answer: No. Blocked or malformed decisions are forced to score `0.0` and are
placed in `blocked_scores`.

Challenge: Does advisory evidence become executable?

Answer: No. Advisory-only decisions are capped and remain only scored evidence.
No execution intent is produced.

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

## Acceptance Evidence

```bash
PYTHONPATH=. python -m pytest \
  tests/test_pr73_opportunity_score_v1.py \
  tests/test_edge_73_candidate_readiness_summary.py \
  tests/test_edge_72_hard_downgrade_engine.py \
  tests/test_edge_71_candidate_classification_layer.py
```
