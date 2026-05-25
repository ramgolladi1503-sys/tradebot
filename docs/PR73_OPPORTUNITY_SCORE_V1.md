# PR73 — Opportunity Score V1

## Purpose

PR73 starts the roadmap scoring layer after candidate truth has been stabilized.
It converts EDGE-72/EDGE-73 readiness evidence into deterministic opportunity
score evidence without ranking, selection, runtime wiring, risk sizing, or broker
behavior.

## Scope

- Add `core/opportunity_score.py`.
- Add PR73 unit tests for score components, score breakdown, compression warning,
  advisory caps, blocked-zero behavior, malformed input, and read-only metadata.
- Keep the contract deterministic and evidence-only.

## Score Components

The V1 score exposes the roadmap components:

- edge
- momentum
- liquidity
- spread
- volatility
- regime fit
- data quality
- time decay risk

Each component is bounded from `0.0` to `1.0`. The final score is the sum of
weighted component contributions multiplied into a `0..100` score.

## Safety Boundaries

This PR does not:

- rank candidates;
- select a top candidate;
- wire runtime behavior;
- call broker APIs;
- create paper or live order intent;
- allocate capital;
- modify dashboard/UI behavior.

## Compression Warning

If multiple valid scored candidates are too close together, the report sets
`score_compressed=True` and emits `opportunity_score_compression_warning`.
This prevents fake confidence before PR76 ranking exists.

## Test Command

```bash
PYTHONPATH=. python -m pytest \
  tests/test_pr73_opportunity_score_v1.py \
  tests/test_edge_73_candidate_readiness_summary.py \
  tests/test_edge_72_hard_downgrade_engine.py \
  tests/test_edge_71_candidate_classification_layer.py
```
