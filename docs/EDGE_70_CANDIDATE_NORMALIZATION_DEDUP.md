# EDGE-70 — Candidate Normalization and Dedup Contract

## Purpose

EDGE-70 adds a read-only normalization seam after EDGE-69 Strategy Registry Candidate Pool.

The goal is to make candidate identity deterministic before any future ranking work exists. This prevents duplicate strategy/instrument/direction/regime rows from becoming fake separate opportunities later.

## Scope

This PR adds:

- `core/strategy_candidate_normalization.py`
- `NormalizedStrategyCandidate`
- `CandidateNormalizationRejection`
- `CandidateNormalizationReport`
- `normalize_strategy_candidates(...)`
- deterministic canonical candidate IDs
- duplicate rejection
- malformed-candidate rejection
- invalid pool fail-closed behavior
- tests for read-only payload guarantees

## Canonical Candidate Identity

A candidate is canonicalized by these fields only:

```text
strategy_id:instrument:direction:regime
```

The normalizer intentionally ignores display casing, spacing, and hyphen differences while preserving a deterministic lower-case colon-separated key.

Examples:

```text
sample_strategy:nifty:buy_call:bull_trend
sample_strategy:banknifty:buy_call:bull_trend
```

## Why This Exists Before Ranking

Ranking duplicate or malformed candidates would create fake precision.

EDGE-70 makes future ranking safer by ensuring the input list is:

- canonical
- de-duplicated
- metadata-only
- read-only
- explicit about rejections
- explicit about invalid input

## Safety Boundaries

EDGE-70 does not:

- rank candidates
- score edge
- select a strategy
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
| Empty input | Report is invalid with `strategy_candidate_normalization_empty_input` |
| Invalid EDGE-69 pool | Report is invalid with `strategy_candidate_normalization_pool_invalid` |
| Miss-ing required candidate fields | Candidate is rejected with `strategy_candidate_normalization_miss-ing_field` |
| Invalid canonical key | Candidate is rejected with `strategy_candidate_normalization_invalid_candidate` |
| Duplicate canonical key | First candidate is preserved, duplicate is rejected with `strategy_candidate_normalization_duplicate_candidate` |

## Acceptance Proof

```bash
PYTHONPATH=. python -m pytest \
  tests/test_edge_70_candidate_normalization_dedup.py \
  tests/test_edge_69_strategy_candidate_pool.py \
  tests/test_edge_68_strategy_eligibility.py
```

## Runtime Proof

No runtime proof is required for EDGE-70 because it is not wired into runtime code.

Runtime proof becomes mandatory only when a later PR reads normalized candidates from runtime, ranking, or dashboard code.
