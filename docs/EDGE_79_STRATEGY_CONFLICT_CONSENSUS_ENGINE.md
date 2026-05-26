# EDGE-79 — Strategy Conflict and Consensus Engine

## Purpose

EDGE-79 adds a pure read-only consensus layer over CandidateIntent values.

The layer checks whether eligible strategy candidates agree by instrument and direction before later quality gates use them.

## Added

- `core/strategy_conflict_consensus.py`
- `StrategyConsensusDecision`
- `StrategyConsensusReport`
- `build_strategy_conflict_consensus(...)`
- `tests/test_edge_79_strategy_conflict_consensus.py`

## Behavior

The engine groups eligible entry candidates by instrument.

A consensus decision is ready only when candidates for the same instrument agree on one direction group and do not contain duplicate strategy families for that instrument-direction group.

The engine blocks empty input, no eligible entry candidates, opposing direction groups, duplicate family candidates, pool-ineligible candidates, non-entry candidates, and unsupported directions.

## Safety model

EDGE-79 is read-only and deterministic.

It does not import strategy modules, execute strategy callables, rank candidates, score edge, or touch runtime.

## Out of scope

No NoTradeOracle, dashboard changes, ranking, scoring, paper journal writes, new strategy families, or runtime wiring.

## Test command

`PYTHONPATH=. python -m pytest tests/test_edge_79_strategy_conflict_consensus.py`

## Next PR

EDGE-80 — NoTradeOracle.
