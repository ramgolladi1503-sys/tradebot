# Agent Handoff: Canonical Strategy Input Truth Repair -> Codex

```text
source_agent: Antigravity
action: CANONICAL_STRATEGY_INPUT_TRUTH_REPAIR
title: Canonical Strategy-Input Truth Repair
scope: Repair forming bar bleed and late-tick/warm-seed overlap defects
requested_paths: core/ohlc_buffer.py, core/market_data.py, tests/core/test_canonical_strategy_input_truth.py
allowed_paths: core/ohlc_buffer.py, core/market_data.py, tests/core/test_canonical_strategy_input_truth.py
forbidden_paths: core/execution, core/broker, core/order, core/risk, strategies/
expected_tests: 10 new behavioral boundary and overlap tests
acceptance_proof: 100% pass rate in tests/core/test_canonical_strategy_input_truth.py, Zero CE blocks
```

## Current State
The system has been repaired to correctly construct historical input data for indicators and strategies without polluting them with incomplete forming bars, even after a warm-seed overlap.

## Changes Passed to You
1. `core/ohlc_buffer.py`:
   - `update_tick`: Strict chronologic boundary enforcement.
   - `get_completed_bars`: Filters forming bars and fails closed on data anomalies.
   - `seed_bars`: Atomic batch contract, preserving live overlapping bars.
2. `core/market_data.py`:
   - `fetch_live_market_data` & `_warm_seed_ohlc_from_history`: Now uses deterministic `cycle_cutoff` and queries via `get_completed_bars`.
3. `tests/core/test_canonical_strategy_input_truth.py`: Exhaustive truth testing.

## Instructions for Codex
1. All inputs are now guaranteed clean and strictly chronologically ordered.
2. You do not need to attempt to clean history yourself inside `compute_indicators`.
3. Proceed with Strategy improvements utilizing these guaranteed invariants.
