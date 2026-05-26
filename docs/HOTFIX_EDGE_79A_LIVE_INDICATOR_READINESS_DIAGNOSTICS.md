# HOTFIX/EDGE-79A — Live Indicator Readiness Diagnostics

## Purpose

HOTFIX/EDGE-79A adds per-symbol indicator readiness evidence before EDGE-80 NoTradeOracle.

The goal is to make the no-trade reason explicit when live price exists but indicator inputs or computed indicators are not ready.

## Added

- `core/live_indicator_readiness.py`
- `LiveIndicatorReadinessDecision`
- `LiveIndicatorReadinessReport`
- `build_live_indicator_readiness_report(...)`
- `tests/test_hotfix_edge_79a_live_indicator_readiness.py`

## Per-symbol fields

Each decision exposes:

- `symbol`
- `indicators_ok`
- `indicator_inputs_ok`
- `ohlc_bars_count`
- `warmup_min_bars`
- `indicator_last_update_epoch`
- `indicators_age_sec`
- `missing_inputs`
- `indicator_missing_inputs`
- `compute_indicators_error`
- `vwap_present`
- `rsi_present`
- `ema_present`
- `atr_present`
- `decision_gate_reason`

## Behavior

A symbol is ready only when:

- OHLC bars meet warmup minimum
- indicator last update exists
- indicator age is within SLA
- VWAP, RSI, EMA, and ATR are present
- indicator compute error is empty

## Example blocker evidence

A later NoTradeOracle can consume this report and explain:

`NIFTY has live LTP but indicator readiness failed: ohlc_bars_count=0/50, indicator_last_update_missing, vwap/rsi/ema/atr unavailable.`

## Scope

This PR is a pure diagnostic contract.

It does not compute indicators, wire runtime, change dashboard, rank candidates, score edge, or add strategy behavior.

## Test command

`PYTHONPATH=. python -m pytest tests/test_hotfix_edge_79a_live_indicator_readiness.py`

## Next PR

HOTFIX/EDGE-79B — Market Close Feed State Classifier.
