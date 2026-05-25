# Agent Review Evidence — EDGE-64 Regime State Machine

## Agent Work Contract

### Goal

Add a read-only regime state machine that consumes EDGE-63 `MarketState` evidence and produces deterministic regime and transition evidence without selecting strategies or creating order intent.

### Files changed

- `core/regime_state.py`
- `tests/test_edge_64_regime_state_machine.py`
- `docs/EDGE_64_REGIME_STATE_MACHINE.md`
- `docs/agent_reviews/edge_64_regime_state_machine.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: EDGE_64_REGIME_STATE_MACHINE
message_decision: READ_ONLY_REGIME_STATE_MACHINE
decision: READ_ONLY_REGIME_STATE_MACHINE
reason: RegimeState now converts MarketState dimensions into deterministic read-only regimes and transition metadata without strategy selection, runtime wiring, dashboard wiring, broker calls, or order intent.
timestamp: 2026-05-25T14:20:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge_64_regime_state_machine.md

### Non-goals

- No strategy selection.
- No strategy eligibility matrix.
- No candidate generation changes.
- No ranking/scoring changes.
- No runtime wiring.
- No dashboard wiring.
- No broker calls.
- No order creation.

## Grill Me Review

### Pushback

A regime state machine can easily become fake intelligence if it starts picking strategies too early. EDGE-64 must only classify regimes and transitions. Strategy selection belongs in a later scoped PR after blockers and transition behavior are proven.

### Required proof

- Regime labels are deterministic.
- Stress regimes take priority before directional regimes.
- Missing MarketState evidence becomes blocked `UNKNOWN`.
- Regime output does not leak raw snapshot evidence.
- Non-action fields remain explicit.

## Hermes Review

### Contract clarity

`RegimeState` is a read-only evidence contract. It contains current regime, transition metadata, confidence, blockers, warnings, reasons, and a sanitized MarketState summary.

### Safety boundary

The state machine emits `is_order_action=false` and `broker_api_called=false`. It does not import broker, websocket, ranking, scoring, dashboard, or strategy modules.

## GSD Review

### Minimality

The PR adds only the regime seam for EDGE-64. It does not implement strategy eligibility, scoring, runtime routing, dashboard rendering, or order behavior.

### Determinism

Classification is deterministic over supplied MarketState values and optional previous regime. No time, network, broker, file, runtime, dashboard, or external dependency is required.

## QA / Safety Review

Tests assert:

- Bull trend classification and stable transition.
- Bear trend transition from previous bull regime.
- Range-bound classification without strategy-selection fields.
- Liquidity stress priority.
- Extreme volatility stress priority.
- Missing market-state blocker behavior.
- Opening and closed session behavior.
- Serialized MarketState payload compatibility.
- Snapshot non-leakage.
- Non-action JSON serialization.

## Scope Guard

Confirmed not touched:

- Runtime feed handling.
- Strategy code.
- Candidate generation.
- Ranking/scoring behavior.
- Dashboard UI.
- Broker/order execution paths.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_64_regime_state_machine.py
```

Expected:

- Regime state-machine tests pass.
- Regime payload remains read-only.
- Missing or blocked MarketState evidence fails closed into `UNKNOWN`.
- Stress regimes emit blockers for future strategy-selection gates.

## Runtime Proof Required After Merge

Later runtime wiring must prove:

- Real runtime MarketState evidence can feed the state machine.
- Regime state evidence is emitted read-only.
- Strategy selection cannot bypass regime blockers.
- No broker/order path consumes RegimeState as permission to trade.

## What This PR Does Not Prove

- It does not prove strategy edge.
- It does not prove profitability.
- It does not choose strategies.
- It does not tune thresholds.
- It does not wire runtime or dashboard behavior.

## Human Approval

Proceed only if CI is green and the PR remains limited to the read-only RegimeState state machine.
