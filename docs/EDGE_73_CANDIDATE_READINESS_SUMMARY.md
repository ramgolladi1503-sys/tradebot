# EDGE-73 — Candidate Readiness Summary

## Purpose

EDGE-73 adds a read-only candidate readiness summary after EDGE-72 Hard Downgrade Engine.

The goal is to summarize candidate readiness counts and downgrade reasons before any future ranking, scoring, selection, or runtime wiring exists.

## Scope

This PR adds:

- `core/candidate_readiness_summary.py`
- `CandidateReadinessSummary`
- `summarize_candidate_readiness(...)`
- aggregate counts for ready, advisory-only, blocked, and invalid candidates
- candidate id groupings for ready, advisory-only, and blocked states
- deterministic reason counts for advisory-only and blocked decisions
- tests for real EDGE-69 → EDGE-70 → EDGE-71 → EDGE-72 → EDGE-73 flow

## Readiness States

| State | Meaning |
|---|---|
| `READY` | At least one candidate is candidate-ready. |
| `ADVISORY_ONLY` | No ready candidates exist, but advisory-only candidates remain visible. |
| `BLOCKED` | No ready/advisory-only candidates are available, or only blocked/unknown decisions exist. |
| `INVALID` | Input is empty, invalid, or malformed enough that the summary itself must fail closed. |

## Why This Exists Before Ranking

Ranking needs a clean readiness picture before comparing candidates.

EDGE-73 does not choose the best candidate. It only summarizes whether the upstream candidate pipeline has clean, advisory-only, blocked, or invalid rows.

This prevents future scoring layers from confusing visibility with readiness.

## Safety Boundaries

EDGE-73 does not:

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

## Acceptance Proof

```bash
PYTHONPATH=. python -m pytest \
  tests/test_edge_73_candidate_readiness_summary.py \
  tests/test_edge_72_hard_downgrade_engine.py \
  tests/test_edge_71_candidate_classification_layer.py \
  tests/test_edge_70_candidate_normalization_dedup.py \
  tests/test_edge_69_strategy_candidate_pool.py
```

## Runtime Proof

No runtime proof is required for EDGE-73 because it is not wired into runtime code.

Runtime proof becomes mandatory only when a later scoped PR reads readiness summaries from runtime, ranking, or dashboard code.

## What This PR Does Not Prove

- Strategy profitability
- Strategy expectancy
- Signal quality
- Candidate ranking quality
- Paper/live trading readiness
- Dashboard usability
- Broker/order safety beyond preserving non-action metadata
