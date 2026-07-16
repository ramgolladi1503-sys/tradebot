# Agent Review: Canonical Strategy-Input Truth Repair

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

## Objectives
- Fix defect 1: Forming bar bleed into indicators due to fetching uncompleted bars, including from the warm seed path.
- Fix defect 2: Late-tick order corruption where old buckets overwrite newer buckets instead of failing closed or merging correctly.

## Architectural Changes Made
1. **Buffer Strictness**: `OhlcBuffer.update_tick` now rejects out-of-order buckets completely (returns `REJECTED_LATE_BUCKET`) to protect the downstream indicator invariants.
2. **Read Strictness**: Introduced `get_completed_bars(symbol, as_of=cycle_cutoff)`. This ensures that forming ticks (bars > `as_of` minus interval) are completely ignored.
3. **Data Protection**: If the underlying `deque` becomes corrupted with out-of-order timestamps, `get_completed_bars` will instantly fail closed and return an empty list `[]`, forcing indicators to bypass rather than emit bad values.
4. **Seed Bars Strictness**: `seed_bars` implements a strict atomic batch contract, rejecting malformed history and properly merging with runtime ticks while giving runtime ticks priority.
5. **Tick Cutoff Centralization**: `fetch_live_market_data` uses a frozen `cycle_cutoff` for both normal and warm-seed paths.

## Verification
- Validated all behaviors via robust new test cases covering boundaries, out of order ticks, invalid history, seed merging, and fallback modes.
- Regression tests fully verified.
- `run_unified_ce_gates.py` passes with zero blocks.
