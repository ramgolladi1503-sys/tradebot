# EDGE-67 — Strategy Hypothesis Contracts

## Purpose

EDGE-67 adds read-only strategy hypothesis contracts.

A hypothesis contract defines what each strategy must prove later through paper-truth evidence before it can be trusted by future eligibility, candidate, ranking, or promotion logic.

## Scope

This PR adds:

- `core/strategy_hypothesis_contracts.py`
- `StrategyHypothesisContract`
- `StrategyHypothesisIssue`
- `StrategyHypothesisRegistry`
- `build_default_strategy_hypothesis_contracts(...)`
- `build_strategy_hypothesis_registry(...)`
- `get_strategy_hypothesis_contract(...)`
- Unit tests for pass and blocking paths

## Hard Boundaries

This PR does not:

- calculate profitability
- prove strategy expectancy
- promote or suspend strategies
- select strategies
- replace hardcoded eligibility
- generate candidates
- rank candidates
- wire runtime behavior
- wire dashboard behavior
- call broker APIs
- create order intent

## Contract Fields

Each strategy hypothesis contract includes:

- `strategy_id`
- `hypothesis_id`
- `title`
- `thesis`
- `expected_regimes`
- `direction_capabilities`
- `required_evidence_keys`
- `outcome_metrics`
- `invalidation_reasons`
- `min_sample_size`
- `min_expectancy_r`
- `max_drawdown_r`

## Validation Rules

The registry blocks when:

- a strategy has no hypothesis contract
- duplicate hypothesis ids exist
- duplicate strategy contracts exist
- a contract references an unknown strategy
- expected regimes are not declared by StrategySpec
- directions are not declared by StrategySpec
- StrategySpec evidence keys are missing from the hypothesis contract
- required outcome metrics are missing
- invalidation rules are missing
- thresholds are invalid
- the upstream strategy-quality audit blocks a strategy

## Evidence Contract

Every payload is non-action evidence:

```json
{
  "read_only": true,
  "append": false,
  "is_order_action": false,
  "broker_api_called": false,
  "source": "strategy_hypothesis_contracts_v1"
}
```

## Acceptance Command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_67_strategy_hypothesis_contracts.py
```

## What This Proves

- Strategy hypotheses can be declared deterministically from StrategySpec metadata.
- Missing or contradictory hypothesis contracts fail closed.
- Contracts preserve non-action safety fields.
- The module does not need runtime wiring or strategy execution to validate contracts.

## What This Does Not Prove

- Profitability
- Real expectancy
- Regime-specific performance
- Candidate generation quality
- Ranking quality
- Paper/live readiness

Those belong to later PRs.

## Next PR

EDGE-68 — Replace Hardcoded Strategy Eligibility.
