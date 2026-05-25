# EDGE-68 — Replace Hardcoded Strategy Eligibility

## Purpose

EDGE-68 introduces contract-driven strategy eligibility.

The goal is to stop relying on hardcoded strategy names or fixed allow-lists at the eligibility logic layer. Eligibility is derived from:

- EDGE-65 `StrategySpec`
- EDGE-67 `StrategyHypothesisContract`
- current regime
- current direction
- available evidence keys
- market-state confidence

## Scope

This PR adds:

- `core/strategy_eligibility.py`
- `StrategyEligibilityInput`
- `StrategyEligibilityDecision`
- `StrategyEligibilityReport`
- `evaluate_strategy_eligibility(...)`
- Unit tests for eligible and rejected decisions

## Hard Boundaries

This PR does not:

- wire runtime behavior
- change the dashboard
- execute strategy modules
- generate candidates
- rank candidates
- calculate profitability
- promote or suspend strategies
- call broker APIs
- create order intent

## Eligibility Rules

A strategy is eligible only when all conditions pass:

- strategy registry is valid
- hypothesis registry is valid
- regime matches `StrategySpec.declared_regimes`
- regime matches `StrategyHypothesisContract.expected_regimes`
- direction matches `StrategySpec.direction_capabilities`
- direction matches `StrategyHypothesisContract.direction_capabilities`
- all required hypothesis evidence keys are present
- market-state confidence is greater than or equal to the strategy minimum

## Failure Modes

The module rejects or blocks with explicit reason codes:

- `strategy_eligibility_registry_invalid`
- `strategy_eligibility_hypothesis_invalid`
- `strategy_eligibility_contract_missing`
- `strategy_eligibility_regime_mismatch`
- `strategy_eligibility_direction_mismatch`
- `strategy_eligibility_evidence_missing`
- `strategy_eligibility_confidence_too_low`
- `strategy_eligibility_input_missing`

## Evidence Contract

Every payload is non-action evidence:

```json
{
  "read_only": true,
  "append": false,
  "is_order_action": false,
  "broker_api_called": false,
  "source": "strategy_eligibility_v1"
}
```

## Acceptance Command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_68_strategy_eligibility.py
```

## What This Proves

- Eligibility can be derived from contracts instead of hardcoded strategy names.
- Missing evidence, regime mismatch, direction mismatch, invalid hypothesis registry, and low confidence fail closed.
- The module is read-only and non-action.

## What This Does Not Prove

- Strategy profitability
- Strategy expectancy
- Candidate generation quality
- Candidate ranking quality
- Runtime/live readiness
- Dashboard integration

Those belong to later PRs.

## Next PR

EDGE-69 — Strategy Registry Candidate Pool.
