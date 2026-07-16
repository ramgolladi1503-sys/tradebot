# Agent Handoff: Canonical Strategy Input Truth Repair -> Codex

```text
source_agent: Antigravity
action: CANONICAL_STRATEGY_INPUT_TRUTH_REPAIR
title: Canonical Strategy-Input Truth Repair
scope: Repair forming bar bleed and late-tick/warm-seed overlap defects
requested_paths: core/ohlc_buffer.py, core/market_data.py, tests/core/test_canonical_strategy_input_truth.py, tests/test_market_data_warm_seed.py, tests/test_market_data_index_quote_cache.py, tests/test_time_sanity_staleness.py, docs/agent_reviews/canonical_strategy_input_truth_repair.md, docs/agent_handoffs/canonical-strategy-input-truth-repair-codex.md
allowed_paths: core/ohlc_buffer.py, core/market_data.py, tests/core/test_canonical_strategy_input_truth.py, tests/test_market_data_warm_seed.py, tests/test_market_data_index_quote_cache.py, tests/test_time_sanity_staleness.py, docs/agent_reviews/canonical_strategy_input_truth_repair.md, docs/agent_handoffs/canonical-strategy-input-truth-repair-codex.md
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
1. The tested offline normal and warm-seed market-data paths now
   supply strictly ordered, completed, timezone-aware bars under
   the documented deterministic fixtures.

   Document limitations:
   offline deterministic proof only
   no live broker/provider proof
   no market-hours soak
   no complete feed-to-strategy execution proof
   no proof of every individual strategy consumer
   no strategy formula or threshold changes
2. You do not need to attempt to clean history yourself inside `compute_indicators`.
3. Proceed with Strategy improvements utilizing these guaranteed invariants.


## CI Compatibility Closure
Four legacy freshness fixtures were aligned to the single frozen cutoff and the canonical `get_completed_bars()` API. This was test-only compatibility work; no production semantics changed.
