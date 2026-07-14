# Agent Review Evidence — EDGE-65 StrategySpec Registry

## Agent Work Contract

### Goal

Add a read-only StrategySpec registry that records declarative strategy metadata before later PRs audit strategy quality, define hypotheses, and replace hardcoded strategy eligibility.

### Files changed

- `core/strategy_spec.py`
- `tests/test_edge_65_strategy_spec_registry.py`
- `docs/EDGE_65_STRATEGY_SPEC_REGISTRY.md`
- `docs/agent_reviews/edge_65_strategy_spec_registry.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: EDGE_65_STRATEGY_SPEC_REGISTRY
message_decision: READ_ONLY_STRATEGY_SPEC_REGISTRY
decision: READ_ONLY_STRATEGY_SPEC_REGISTRY
reason: StrategySpec now provides a deterministic read-only registry for strategy metadata without selecting strategies, replacing eligibility, generating candidates, ranking candidates, runtime wiring, dashboard wiring, broker calls, or order intent.
timestamp: 2026-05-25T14:35:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge_65_strategy_spec_registry.md

### Non-goals

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
- No order creation.

## Grill Me Review

### Pushback

A strategy registry can become fake progress if it is treated as strategy intelligence. EDGE-65 must only lock metadata and validation. Strategy quality belongs to EDGE-66, strategy hypotheses to EDGE-67, and eligibility replacement to EDGE-68.

### Required proof

- Registry is read-only and non-action.
- Default specs are metadata-only.
- Bad specs fail closed.
- Unsafe regimes are blocked or warned.
- Registry output does not contain selected strategy or eligible-strategy decisions.

## Hermes Review

### Contract clarity

`StrategySpecRegistry` is a metadata contract. It contains specs, strategy ids, validation issues, blockers, warnings, and registry metadata.

### Safety boundary

The registry emits `is_order_action=false` and `broker_api_called=false`. It does not import strategy modules, call strategy functions, import broker modules, wire runtime, or change dashboard behavior.

## GSD Review

### Minimality

The PR adds only the StrategySpec registry seam for EDGE-65. It does not implement EDGE-66 quality audit, EDGE-67 hypotheses, EDGE-68 eligibility replacement, EDGE-69 candidate intent, or EDGE-70 candidate pool.

### Determinism

Validation is deterministic over supplied specs. No time, network, broker, file, runtime, dashboard, or external dependency is required.

## QA / Safety Review

Tests assert:

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

## Scope Guard

Confirmed not touched:

- Runtime feed handling.
- Existing strategy execution code.
- Candidate generation.
- Ranking/scoring behavior.
- Dashboard UI.
- Broker/order execution paths.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_65_strategy_spec_registry.py
```

Expected:

- StrategySpec registry tests pass.
- Registry remains read-only.
- Invalid metadata fails closed.
- Registry does not perform strategy selection.

## Runtime Proof Required After Merge

Later PRs must prove:

- Strategy quality audit consumes the registry without executing strategy modules.
- Strategy hypothesis contracts are defined per spec.
- Strategy eligibility replacement cannot bypass regime/feed/quote blockers.
- Candidate generation cannot treat registry presence as execution permission.

## What This PR Does Not Prove

- It does not prove strategy edge.
- It does not prove strategy quality.
- It does not prove profitability.
- It does not choose strategies.
- It does not generate candidates.
- It does not wire runtime or dashboard behavior.

## Human Approval

Proceed only if CI is green and the PR remains limited to the read-only StrategySpec registry.


## High-Risk Path Review

N/A
