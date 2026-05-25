# EDGE-63 — MarketState Model

## Purpose

EDGE-63 introduces a read-only `MarketState` model contract.

The goal is to describe current market conditions in a structured way before building the regime state machine in EDGE-64. This PR does not select strategies, rank candidates, tune thresholds, or change runtime behavior.

## Scope

In scope:

- Add `core/market_state.py`.
- Add `MarketStateDimension`.
- Add `MarketState`.
- Add `build_market_state(...)`.
- Classify descriptive dimensions:
  - trend
  - volatility
  - breadth
  - liquidity
  - session
- Add missing-evidence blockers and warnings.
- Sanitize input snapshot.
- Emit non-action evidence fields:
  - `read_only=true`
  - `append=false`
  - `is_order_action=false`
  - `broker_api_called=false`

Out of scope:

- No regime state machine.
- No strategy selection.
- No candidate generation changes.
- No ranking/scoring changes.
- No runtime wiring.
- No dashboard wiring.
- No broker calls.
- No order behavior.

## Contract

`build_market_state(snapshot, symbol, mode)` returns `MarketState` with:

- schema version
- mode
- symbol
- trend dimension
- volatility dimension
- breadth dimension
- liquidity dimension
- session dimension
- confidence
- blockers
- warnings
- sanitized evidence snapshot
- metadata

## Design boundary

This is a descriptive model only. EDGE-64 may consume this model and convert it into a regime state machine. EDGE-63 does not decide whether a strategy is eligible.

## Acceptance proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_63_market_state_model.py
```

Required proof:

- Bullish/deep-liquidity state is classified.
- Bearish/thin/high-volatility state is classified.
- Volatility boundaries are deterministic.
- Missing evidence creates unknown dimensions and blocker.
- Session boundaries are deterministic.
- Snapshot sanitization prevents unknown values from being copied as evidence.
- JSON payload includes non-action fields.

## Runtime Proof Required After Merge

Later runtime wiring must prove:

- Real runtime market snapshots can be adapted into this input shape.
- MarketState evidence is emitted read-only.
- Strategy selection does not bypass the future regime contract.
- No broker/order path consumes MarketState as permission to trade.

## Risk

Low. This PR adds a pure model contract and tests only. It does not modify runtime, strategy, ranking, dashboard, broker, or order behavior.

## Next PR

After this PR is merged and CI is green, continue to EDGE-64 — Regime State Machine.
