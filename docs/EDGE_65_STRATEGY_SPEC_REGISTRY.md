# EDGE-65 — StrategySpec Registry

## Purpose

EDGE-65 introduces a read-only `StrategySpec` registry contract.

The goal is to document strategy metadata in one deterministic registry before later PRs audit strategy quality, define hypotheses, and replace hardcoded strategy eligibility. This PR does not select strategies, generate candidates, rank candidates, wire runtime behavior, change dashboard behavior, or touch broker/order paths.

## Scope

In scope:

- Add `core/strategy_spec.py`.
- Add `StrategySpec`.
- Add `StrategySpecIssue`.
- Add `StrategySpecRegistry`.
- Add `build_default_strategy_specs(...)`.
- Add `build_strategy_spec_registry(...)`.
- Add `get_strategy_spec(...)`.
- Validate required metadata:
  - strategy id
  - name
  - family
  - module path
  - callable name
  - instruments
  - declared regimes
  - blocked regimes
  - required market-state dimensions
  - required evidence keys
  - direction capabilities
- Emit non-action evidence fields:
  - `read_only=true`
  - `append=false`
  - `is_order_action=false`
  - `broker_api_called=false`

Out of scope:

- No strategy selection.
- No hardcoded eligibility replacement.
- No strategy quality scoring.
- No strategy hypothesis proof.
- No candidate intent.
- No candidate pool.
- No strategy rebuild.
- No runtime wiring.
- No dashboard wiring.
- No broker calls.
- No order behavior.

## Contract

`build_strategy_spec_registry(specs=None)` returns `StrategySpecRegistry` with:

- schema version
- read-only metadata
- spec list
- strategy ids
- validation issues
- blockers
- warnings
- metadata

The default registry is metadata only. It records module paths and callable names but does not import strategy modules and does not execute strategy code.

## Validation rules

The registry fails closed with blockers when:

- registry is empty
- strategy ids are duplicated
- required fields are missing
- declared regimes are unknown
- unsafe regimes are declared as usable metadata
- required market-state dimensions are missing
- market-state confidence is outside 0..1

The registry emits warnings when:

- unsafe regimes are not explicitly blocked
- recommended evidence keys are missing

Unsafe regimes include:

- `UNKNOWN`
- `OUT_OF_SESSION`
- `LIQUIDITY_STRESSED`
- `VOLATILITY_STRESSED`

## Safety boundary

This PR is descriptive only. Strategy specs are not strategy-selection permission.

The output explicitly contains:

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`

## Acceptance proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_65_strategy_spec_registry.py
```

Required proof:

- Default registry is valid and read-only.
- Strategy lookup normalizes ids without executing strategy code.
- JSON payload preserves non-action fields.
- Duplicate strategy ids fail closed.
- Empty registry and missing required fields fail closed.
- Unknown regimes fail closed.
- Unsafe declared regimes fail closed.
- Missing unsafe blocked regimes warn.
- Missing market-state dimensions block.
- Missing recommended evidence keys warn.
- Default specs remain metadata-only.

## Runtime Proof Required Later

Later PRs must prove:

- Strategy quality audit consumes this registry without executing strategy code.
- Strategy hypothesis contracts are defined per spec.
- Strategy eligibility replacement cannot bypass regime/feed/quote blockers.
- Candidate generation cannot treat registry presence as execution permission.

## Risk

Low. This PR adds a pure metadata registry and tests only. It does not modify runtime, strategy, ranking, dashboard, broker, or order behavior.

## Next PR

After this PR is merged and CI is green, continue to EDGE-66 — Strategy Quality Audit.
