# EDGE-66 — Strategy Quality Audit

## Purpose

EDGE-66 adds a read-only Strategy Quality Audit over the EDGE-65 `StrategySpec` registry.

The goal is to surface metadata quality risks before later PRs use strategy metadata for hypothesis contracts, eligibility replacement, candidate generation, or strategy rebuilds.

## Scope

This PR adds:

- `core/strategy_quality_audit.py`
- `StrategyQualityFinding`
- `StrategyQualityRecord`
- `StrategyQualityAudit`
- `build_strategy_quality_audit(...)`
- Unit tests for pass, warning, and blocking paths

## Hard Boundaries

This PR does not:

- import strategy modules
- execute strategy callables
- select strategies
- replace hardcoded strategy eligibility
- generate candidates
- rank candidates
- write runtime artifacts
- wire dashboard behavior
- call brokers
- create order intent

## Audit Signals

The audit records warnings for metadata that needs later proof:

- low market-state confidence requirement
- narrow regime coverage
- single-direction capability
- missing human-readable description
- missing recommended evidence keys from the registry validation layer
- unsafe regimes not explicitly blocked from the registry validation layer

The audit records blockers when the underlying registry is blocked, for example unsafe declared tradable regimes or empty registry input.

## Evidence Contract

Every audit payload is non-action evidence:

```json
{
  "read_only": true,
  "append": false,
  "is_order_action": false,
  "broker_api_called": false,
  "source": "strategy_quality_audit_v1"
}
```

## Acceptance Command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_66_strategy_quality_audit.py
```

## What This Proves

- Strategy quality metadata can be audited deterministically.
- Default strategy specs can produce read-only non-action audit evidence.
- Weak strategy metadata is surfaced as warnings.
- Invalid registry metadata is surfaced as blockers.
- Audit payloads do not contain strategy-selection outputs.

## What This Does Not Prove

- Strategy profitability
- Strategy hypothesis validity
- Regime-specific expectancy
- Candidate generation quality
- Runtime/live trading readiness

Those belong to later PRs.

## Next PR

EDGE-67 — Strategy Hypothesis Contracts.
