# EDGE-64 — Regime State Machine

## Purpose

EDGE-64 introduces a read-only regime state machine on top of the EDGE-63 `MarketState` contract.

The goal is to convert descriptive market-state dimensions into one deterministic regime label and transition metadata. This PR does not select strategies, rank candidates, tune thresholds, wire runtime behavior, change dashboard behavior, or touch broker/order paths.

## Scope

In scope:

- Add `core/regime_state.py`.
- Add `RegimeTransition`.
- Add `RegimeState`.
- Add `build_regime_state(...)`.
- Consume `MarketState` objects or serialized `MarketState` payloads.
- Classify read-only regimes:
  - `BULL_TREND`
  - `BEAR_TREND`
  - `RANGE_BOUND`
  - `HIGH_VOLATILITY`
  - `VOLATILITY_STRESSED`
  - `LIQUIDITY_STRESSED`
  - `OPENING_DISCOVERY`
  - `OUT_OF_SESSION`
  - `MIXED_UNCERTAIN`
  - `UNKNOWN`
- Emit transition metadata:
  - `INITIAL`
  - `STABLE`
  - `CHANGED`
  - `UNKNOWN`
- Preserve non-action evidence fields:
  - `read_only=true`
  - `append=false`
  - `is_order_action=false`
  - `broker_api_called=false`

Out of scope:

- No strategy selection.
- No strategy eligibility matrix.
- No candidate generation changes.
- No ranking/scoring changes.
- No runtime wiring.
- No dashboard wiring.
- No broker calls.
- No order behavior.

## Contract

`build_regime_state(market_state, previous_regime=None)` returns `RegimeState` with:

- schema version
- mode
- symbol
- current regime
- transition metadata
- confidence
- blockers
- warnings
- reasons
- sanitized market-state summary
- metadata

The market-state summary intentionally keeps only dimension values, confidence, blockers, warnings, schema version, source, mode, and symbol. It does not copy `evidence_snapshot` into the regime payload.

## State machine priority

The classifier is deterministic and priority-based:

1. Missing or blocked market state -> `UNKNOWN`.
2. Pre-open/closed session -> `OUT_OF_SESSION`.
3. Thin/stale liquidity -> `LIQUIDITY_STRESSED`.
4. Extreme volatility -> `VOLATILITY_STRESSED`.
5. Opening session -> `OPENING_DISCOVERY`.
6. Uptrend + bullish breadth -> `BULL_TREND`.
7. Downtrend + bearish breadth -> `BEAR_TREND`.
8. Sideways + low/normal volatility -> `RANGE_BOUND`.
9. High volatility without clear direction -> `HIGH_VOLATILITY`.
10. Everything else -> `MIXED_UNCERTAIN`.

## Safety boundary

This PR is descriptive only. Regime labels are not execution permission.

The output explicitly contains:

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`

Stress regimes emit blockers so future strategy-selection work can fail closed instead of treating weak data as tradable edge.

## Acceptance proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_64_regime_state_machine.py
```

Required proof:

- Bull trend classification is deterministic.
- Bear trend transition from previous bull regime is detected.
- Range-bound regime is classified without strategy-selection fields.
- Liquidity stress takes priority over directional trend.
- Extreme volatility takes priority over directional trend.
- Missing market state becomes `UNKNOWN` and blocked.
- Opening and closed session boundaries are handled.
- Serialized market-state payloads are accepted.
- Regime payload does not leak raw `evidence_snapshot`.
- JSON payload includes non-action fields.

## Runtime Proof Required Later

Later runtime wiring must prove:

- Real runtime `MarketState` evidence can feed this state machine.
- Regime state is emitted read-only.
- Strategy eligibility cannot bypass blockers.
- No broker/order path consumes regime labels as permission to trade.

## Risk

Low. This PR adds a pure state-machine seam and tests only. It does not modify runtime, strategy, ranking, dashboard, broker, or order behavior.

## Next PR

After this PR is merged and CI is green, continue to the next scoped roadmap item only. Do not wire strategy selection until that PR is explicitly scoped.
