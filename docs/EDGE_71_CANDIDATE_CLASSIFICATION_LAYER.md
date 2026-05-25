# EDGE-71 — Candidate Classification Layer

## Purpose

EDGE-71 adds a read-only candidate classification seam after EDGE-70 Candidate Normalization and Dedup.

The goal is to attach deterministic metadata classes to normalized candidates before any future scoring or ranking exists.

## Scope

This PR adds:

- `core/strategy_candidate_classification.py`
- `ClassifiedStrategyCandidate`
- `CandidateClassificationReport`
- `classify_strategy_candidates(...)`
- direction classification
- regime classification
- family classification
- instrument classification
- core evidence completeness classification
- tests for real EDGE-69 → EDGE-70 → EDGE-71 flow

## Classification Buckets

| Field | Example classes |
|---|---|
| Direction | `CALL_BIAS`, `PUT_BIAS`, `NEUTRAL`, `UNKNOWN_DIRECTION` |
| Regime | `TREND`, `RANGE`, `VOLATILITY`, `OPENING_DISCOVERY`, `MIXED`, `UNKNOWN_REGIME` |
| Family | `VWAP`, `BREAKOUT`, `MEAN_REVERSION`, `EXPIRY`, `ENSEMBLE`, `EVENT`, `UNKNOWN_FAMILY` |
| Instrument | `INDEX`, `UNKNOWN_INSTRUMENT` |
| Evidence | `CORE_EVIDENCE_COMPLETE`, `CORE_EVIDENCE_INCOMPLETE` |

## Why This Exists Before Ranking

Ranking needs clean input labels, not raw strings.

EDGE-71 avoids fake precision by separating classification from scoring. It does not claim one candidate is better than another. It only says what type of candidate each row is.

## Safety Boundaries

EDGE-71 does not:

- rank candidates
- score edge
- select strategies
- allocate capital
- change runtime behavior
- update dashboard behavior
- import strategy modules
- call strategy callables
- call broker APIs
- create order intent
- write runtime artifacts

## Failure Handling

| Case | Behavior |
|---|---|
| Empty input | Report is invalid with `strategy_candidate_classification_empty_input` |
| Invalid EDGE-70 normalization report | Report is invalid with `strategy_candidate_classification_normalization_invalid` |
| Missing required candidate fields | Candidate is placed in `blocked_candidates` with `strategy_candidate_classification_missing_field` |
| Unknown direction | Candidate remains metadata-valid but receives `strategy_candidate_classification_unknown_direction` warning |
| Unknown regime | Candidate remains metadata-valid but receives `strategy_candidate_classification_unknown_regime` warning |
| Unknown family | Candidate remains metadata-valid but receives `strategy_candidate_classification_unknown_family` warning |
| Missing core evidence keys | Candidate remains metadata-valid but receives `strategy_candidate_classification_evidence_incomplete` warning |

## Acceptance Proof

```bash
PYTHONPATH=. python -m pytest \
  tests/test_edge_71_candidate_classification_layer.py \
  tests/test_edge_70_candidate_normalization_dedup.py \
  tests/test_edge_69_strategy_candidate_pool.py
```

## Runtime Proof

No runtime proof is required for EDGE-71 because it is not wired into runtime code.

Runtime proof becomes mandatory only when a later PR reads classified candidates from runtime, ranking, or dashboard code.
