# EDGE-48 — Scoring Truth Hardening

## Purpose

Prevent high numeric scores from creating false confidence when candidate truth says the row is unsafe, advisory, debug-only, soft-rejected, or not price-feasible.

EDGE-48 adds a read-only scoring truth contract. It does not tune strategies, weights, thresholds, or profitability logic.

## Implementation

Added `core/scoring_truth_contract.py`.

The contract exposes:

- `ScoringTruthDecision`
- `harden_scoring_truth(candidate, score_payload)`

The contract consumes the already-merged EDGE-46 and EDGE-47 contracts:

- `classify_candidate_state(candidate)`
- `classify_candidate_status_contract(candidate)`

## Safety Rules

The contract applies deterministic score caps:

- hard reject: `0.00`
- debug-only: `0.00`
- soft reject: `0.24`
- advisory: `0.49`
- rankable: `0.79`
- executable: `1.00`

Additional rule:

- if price feasibility is not proven, the score is capped to soft-reject range.
- execution permission controls only execution eligibility, not raw scoring.

## Scope Guard

Out of scope:

- no strategy tuning
- no scoring-weight changes
- no dashboard migration
- no runtime wiring
- no broker integration changes
- no live runtime behavior changes

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge48_scoring_truth_contract.py
```

The tests prove:

- hard rejects zero high scores
- debug-only rows zero high scores
- advisory rows are capped below rankable
- rankable rows without price truth are not rankable for scoring truth
- rankable rows with price truth are capped to rankable ceiling
- executable rows still require explicit execution permission for execution eligibility
