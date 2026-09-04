# MARKET_STATE_ENGINE_V1

## Purpose

Provide a deterministic, read-only classification for every authoritative live cycle:

- `BULLISH`
- `NO_TRADE`
- `BEARISH`

for `NIFTY`, `BANKNIFTY`, and `SENSEX`, together with trend-confirmation and reversal levels.

This is a market-state layer, not a strategy and not an execution engine.

## Safety authority

The engine and runtime adapter are explicitly execution-inert:

- `read_only=true`
- `execution_capable=false`
- `broker_write_authority=false`
- `order_authority=false`
- `paper_authorized=false`
- `live_execution_authorized=false`
- `broker_order_calls=0`

Any missing critical input, stale quote, blocked feed authority, or closed session fails closed to `NO_TRADE` with zero confidence.

## Direction score

The score is bounded approximately to `[-100,+100]`.

| Component | Weight |
| --- | ---: |
| VWAP / ATR location | 25 |
| EMA relationship / slope | 20 |
| price structure | 15 |
| momentum | 15 |
| breadth | 10 |
| opening location | 10 |
| futures confirmation | 5 |

Each input component is normalized to `[-1,+1]` before weighting.

## Hysteresis

Entry thresholds are deliberately wider than exit thresholds:

- enter bullish: `score >= +45`
- leave bullish only after: `score < +25`
- enter bearish: `score <= -45`
- leave bearish only after: `score > -25`

This prevents rapid zone flipping around one threshold.

## Regime is not entry

`zone` and `entry_state` are separate.

Examples:

1. `zone=BULLISH`, but price is >=1.25 ATR above VWAP → `entry_state=NO_TRADE_EXTENDED`.
2. `zone=BULLISH`, but resistance is within 0.25 ATR → `entry_state=WAIT_PULLBACK`.

The same logic is mirrored for bearish conditions near support.

## Trend and reversal levels

The engine computes volatility-scaled structural levels using a minimum buffer of `0.10 * ATR`.

Bull trend confirmation can incorporate:

- VWAP + buffer
- ORB high + buffer
- confirmed swing high + buffer

Bull reversal uses the nearest authoritative support among:

- VWAP - buffer
- confirmed swing low - buffer
- structural support - buffer

Bear levels are symmetric.

These are explicit bot definitions. They are not claimed to be universal meanings of the trader terms “trend price” or “reversal price.”

## Cross-index consensus

The runtime publishes all three index states and a separate consensus layer.

- at least two bullish and none bearish → `BULLISH`
- at least two bearish and none bullish → `BEARISH`
- otherwise → `NO_TRADE / CROSS_INDEX_CONFLICT`
- fewer than two authoritative states → `NO_TRADE / INSUFFICIENT_CROSS_INDEX_AUTHORITY`

A strategy may consume an individual index state, but the consensus must remain visible so disagreement cannot be hidden.

## Required upstream snapshot contract

Critical for any classification:

- `price`
- `vwap`
- `atr`
- `quote_age_sec`
- `feed_authority=true`
- `session_open=true`

Directional features should provide, when authoritative:

- `ema_fast`, `ema_slow`, `ema_slope_atr`
- `structure_score`
- `momentum_score`
- `breadth`, `weighted_breadth`, `breadth_momentum`
- `open_location_score`
- `futures_confirmation_score`

Structural levels should provide, when available:

- `orb_high`, `orb_low`
- `swing_high`, `swing_low`
- `support`, `resistance`

Scores supplied by upstream feature builders are expected to be causal and normalized to `[-1,+1]`; the engine clips them to that range.

## Runtime artifacts

`core.live_market_state_runtime.publish_live_market_state()` atomically writes:

- `market_state_engine_v1.json` — current state
- `market_state_engine_v1.jsonl` — append-only cycle ledger

The artifact contains per-index state, score, confidence, component diagnostics, trend/reversal levels, blockers/warnings, and cross-index consensus.

## Live-readiness boundary

The classifier itself is ready for deterministic use once tests and CI pass. Full next-session readiness additionally requires the existing canonical observer to supply the required per-index snapshot fields from authoritative live data. Do not fabricate missing breadth, futures, ATR, or structural values. Until that producer wiring is proven, the runtime must remain `NO_TRADE/BLOCKED` for missing critical evidence.
