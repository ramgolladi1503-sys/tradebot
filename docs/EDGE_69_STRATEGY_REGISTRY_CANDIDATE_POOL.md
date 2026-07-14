# EDGE-69 — Strategy Registry Candidate Pool

## Purpose

EDGE-69 introduces a read-only strategy registry candidate pool.

The goal is to convert contract-eligible strategy metadata into deterministic candidate descriptors before any future ranking, scoring, selection, runtime wiring, dashboard work, or order behavior exists.

This is not a trading signal engine. It is a safe architecture seam.

## Scope

This PR adds:

- `core/strategy_candidate_pool.py`
- `StrategyCandidatePoolInput`
- `StrategyRegistryCandidate`
- `StrategyCandidatePoolReport`
- `build_strategy_candidate_pool(...)`
- Unit tests for eligible candidates, invalid inputs, invalid registry, ineligible exclusions, non-action payloads, and metadata-only behavior

## Hard Boundaries

This PR does not:

- execute strategy modules
- call strategy functions
- generate trade signals
- rank candidates
- score edge
- calculate profitability
- allocate capital
- wire runtime behavior
- change dashboard behavior
- call broker APIs
- create order intent

## Candidate Definition

A candidate is metadata only:

```text
strategy_id + instrument + direction + regime
```

A candidate can be created only when EDGE-68 eligibility marks the strategy as eligible.

The candidate payload carries:

- candidate id
- strategy id
- instrument
- regime
- direction
- strategy family
- module path metadata
- callable name metadata
- required evidence keys
- eligibility status
- non-action evidence fields

## Failure Modes

The module blocks or warns with explicit reason codes:

- `strategy_candidate_pool_input_miss-ing`
- `strategy_candidate_pool_registry_invalid`
- `strategy_candidate_pool_eligibility_invalid`
- `strategy_candidate_pool_empty`
- `strategy_candidate_pool_strategy_ineligible`

## Evidence Contract

Every payload is non-action evidence:

```json
{
  "read_only": true,
  "append": false,
  "is_order_action": false,
  "broker_api_called": false,
  "source": "strategy_candidate_pool_v1"
}
```

## Why No Ranking Here

Ranking here would be fake precision.

The candidate pool answers only:

> Which strategy metadata entries are eligible enough to become future candidate descriptors?

It does not answer:

> Which candidate is best?

That belongs to a later explicitly scoped ranking/scoring PR.

## Acceptance Command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_69_strategy_candidate_pool.py tests/test_edge_68_strategy_eligibility.py tests/test_edge_67_strategy_hypothesis_contracts.py tests/test_edge_65_strategy_spec_registry.py
```

## What This Proves

- Candidate descriptors are generated from registry eligibility instead of hardcoded strategy names.
- Ineligible strategies are excluded and reported.
- Invalid registry or invalid eligibility fails closed.
- Candidate IDs are deterministic.
- The pool is read-only and non-action.
- Strategy modules are not imported and strategy callables are not executed.

## What This Does Not Prove

- Strategy profitability
- Strategy expectancy
- Signal quality
- Candidate ranking quality
- Broker readiness
- Paper/live trading readiness
- Dashboard usability

Those belong to later PRs.

## Next PR

EDGE-70 only after EDGE-69 is merged and green.
