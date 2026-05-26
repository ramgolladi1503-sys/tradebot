# EDGE-77 — Strategy-Specific Exit Models

## Purpose

EDGE-77 adds a pure strategy-specific exit model contract for eligible CandidateIntent values.

The layer answers one narrow question: if a candidate becomes usable later, what strategy-family-specific read-only exit guidance should be attached to it?

This PR does not mutate runtime state, does not call adapters, does not rank candidates, and does not perform execution lifecycle behavior.

## Added

- `core/strategy_exit_models.py`
- `ExitPolicySpec`
- `StrategyExitModel`
- `StrategyExitModelReport`
- `build_strategy_specific_exit_models(...)`

## Supported families

- `breakout`
- `vwap`
- `mean_reversion`
- `zero_hero`

Each family receives a different read-only policy profile for:

- initial risk percentage
- profit-take percentage
- trailing activation percentage
- maximum hold duration
- review cadence
- invalidation signals
- explanatory notes

## Confirmation behavior

An exit model is ready only when all of these are true:

1. The candidate is pool-eligible.
2. The candidate is an ENTRY intent.
3. The candidate direction is a supported long option direction.
4. The candidate family has a configured policy.
5. When option confirmation is required or supplied, the candidate is present in confirmed option-chain evidence.
6. The generated policy is structurally valid.

If any condition fails, the model is blocked with explicit blockers.

## Safety model

EDGE-77 is read-only and deterministic.

The report preserves non-action guarantees and records that it does not import strategy modules, execute strategy callables, rank candidates, score edge, touch runtime, or emit lifecycle mutations.

## Out of scope

EDGE-77 does not add:

- runtime wiring
- dashboard changes
- ranking
- scoring
- paper journal writes
- adapter integration
- lifecycle mutation behavior
- strategy parameter robustness tests

## Test command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_77_strategy_exit_models.py
```

## Next PR

EDGE-78 — Strategy Parameter Robustness Tests.
