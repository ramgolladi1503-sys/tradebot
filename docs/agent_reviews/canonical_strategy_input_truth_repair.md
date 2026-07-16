# Agent Review: Canonical Strategy-Input Truth Repair

## Objectives
- Fix defect 1: Forming bar bleed into indicators due to fetching uncompleted bars.
- Fix defect 2: Late-tick order corruption where old buckets overwrite newer buckets instead of failing closed or merging correctly.

## Architectural Changes Made
1. **Buffer Strictness**: `OhlcBuffer.update_tick` now rejects out-of-order buckets completely (returns `REJECTED_LATE_BUCKET`) to protect the downstream indicator invariants.
2. **Read Strictness**: Introduced `get_completed_bars(symbol, as_of=cycle_cutoff)`. This ensures that forming ticks (bars > `as_of` minus interval) are completely ignored.
3. **Data Protection**: If the underlying `deque` becomes corrupted with out-of-order timestamps, `get_completed_bars` will instantly fail closed and return an empty list `[]`, forcing indicators to bypass rather than emit bad values.
4. **Seed Bars Strictness**: `seed_bars` now correctly handles merging deduplicated historical frames and existing ticks, rather than relying on weak appending rules.
5. **Tick Cutoff Centralization**: `fetch_live_market_data` now freezes exactly one `cycle_cutoff` at the top of the symbol loop. This eliminates mid-loop tick skew.

## Verification
- Validated all behaviors via 12 robust new test cases covering boundaries, out of order ticks, invalid history, seed merging, and fallback modes.
- Regression tests fully verified.
- `run_unified_ce_gates.py` passes with zero blocks.
