# Agent Handoff: Canonical Strategy Input Truth Repair -> Codex

## Current State
The system has been repaired to correctly construct historical input data for indicators and strategies without polluting them with incomplete forming bars.

## Changes Passed to You
1. `core/ohlc_buffer.py`:
   - `update_tick`: Strict chronologic boundary enforcement.
   - `get_completed_bars`: New API that filters forming bars and checks buffer health.
   - `seed_bars`: Proper historical data merging logic.
2. `core/market_data.py`:
   - `fetch_live_market_data`: Now uses `cycle_cutoff` for deterministic timestamp extraction and calls `get_completed_bars`.
3. `tests/core/test_canonical_strategy_input_truth.py`: Exhaustive truth testing.

## Instructions for Codex
1. All inputs should now be guaranteed clean and strictly chronologically ordered.
2. You do not need to attempt to clean history yourself inside `compute_indicators`. It is the responsibility of `OhlcBuffer` and `market_data` to only supply you with valid frames.
3. Proceed with Strategy improvements utilizing these guaranteed invariants.
