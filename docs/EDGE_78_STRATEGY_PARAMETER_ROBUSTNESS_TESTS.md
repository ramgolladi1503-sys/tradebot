# EDGE-78 — Strategy Parameter Robustness Tests

## Purpose

EDGE-78 hardens pure strategy candidate generators against unsafe threshold parameters.

Invalid thresholds should be visible and fail-closed instead of making a candidate appear eligible.

## Changed files

- `core/breakout_candidate_generator.py`
- `core/vwap_candidate_generator.py`
- `core/mean_reversion_candidate_generator.py`
- `core/zero_hero_candidate_generator.py`
- `tests/test_edge_78_strategy_parameter_robustness.py`

## Parameter rules

Parameters must be finite numeric values.

Negative thresholds are rejected. Thresholds that represent a real minimum reject zero. Zero is allowed only for safe boundary cases such as volume confirmation and oscillator confirmation.

Zero Hero also rejects inverted premium bounds.

## Blockers

Invalid parameters add explicit blockers:

- `breakout_invalid_parameter`
- `vwap_invalid_parameter`
- `mean_reversion_invalid_parameter`
- `zero_hero_invalid_parameter`

The generated candidate remains blocked and non-action metadata stays explicit.

## Out of scope

No runtime wiring, dashboard work, ranking, scoring, paper journal writes, or new strategy families.

## Test command

`PYTHONPATH=. python -m pytest tests/test_edge_78_strategy_parameter_robustness.py`

## Next PR

EDGE-79 — Strategy Conflict and Consensus Engine.
