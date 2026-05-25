# EDGE-72 — Hard Downgrade Engine

## Purpose

EDGE-72 adds a read-only hard downgrade seam after EDGE-71 Candidate Classification.

The goal is to convert risky metadata warnings into explicit candidate decisions before any future ranking, scoring, selection, or runtime wiring exists.

## Scope

This PR adds:

- `core/candidate_hard_downgrade.py`
- `CandidateHardDowngradeDecision`
- `CandidateHardDowngradeReport`
- `apply_candidate_hard_downgrades(...)`
- hard downgrade decisions for candidate-ready, advisory-only, and blocked states
- tests for real EDGE-69 → EDGE-70 → EDGE-71 → EDGE-72 flow

## Decision States

| Decision | Meaning |
|---|---|
| `CANDIDATE_READY` | Classified candidate metadata is complete enough for future downstream read-only stages. |
| `ADVISORY_ONLY` | Candidate metadata exists, but unknown or incomplete classification evidence prevents clean readiness. |
| `BLOCKED` | Candidate input is invalid, malformed, or inherited blocked classification state. |

## Hard Downgrade Rules

| Source condition | EDGE-72 behavior |
|---|---|
| Clean classified candidate | `CANDIDATE_READY` |
| Unknown direction warning | `ADVISORY_ONLY` with `candidate_hard_downgrade_unknown_direction` |
| Unknown regime warning | `ADVISORY_ONLY` with `candidate_hard_downgrade_unknown_regime` |
| Unknown family warning | `ADVISORY_ONLY` with `candidate_hard_downgrade_unknown_family` |
| Incomplete core evidence warning | `ADVISORY_ONLY` with `candidate_hard_downgrade_evidence_incomplete` |
| Empty input | invalid report with `candidate_hard_downgrade_empty_input` |
| Invalid EDGE-71 report | invalid report with `candidate_hard_downgrade_classification_invalid` |
| EDGE-71 blocked candidate | blocked decision with `candidate_hard_downgrade_classification_blocked` |
| Malformed payload | blocked decision with `candidate_hard_downgrade_malformed_candidate` |

## Why This Exists Before Ranking

Ranking must not receive ambiguous metadata as if it were clean input.

EDGE-71 deliberately treated unknown metadata as warnings. EDGE-72 makes the safety consequence explicit: those rows remain visible as advisory evidence but are not candidate-ready.

This prevents silent promotion of questionable candidates into future scoring, ranking, or selection layers.

## Safety Boundaries

EDGE-72 does not:

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
  tests/test_edge_72_hard_downgrade_engine.py \
  tests/test_edge_71_candidate_classification_layer.py \
  tests/test_edge_70_candidate_normalization_dedup.py \
  tests/test_edge_69_strategy_candidate_pool.py
```

## Runtime Proof

No runtime proof is required for EDGE-72 because it is not wired into runtime code.

Runtime proof becomes mandatory only when a later scoped PR reads downgrade decisions from runtime, ranking, or dashboard code.

## What This PR Does Not Prove

- Strategy profitability
- Strategy expectancy
- Signal quality
- Candidate ranking quality
- Paper/live trading readiness
- Dashboard usability
- Broker/order safety beyond preserving non-action metadata
