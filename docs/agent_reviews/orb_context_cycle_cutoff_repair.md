# ORB Context Cycle Cutoff Repair

## Agent Work Contract
- source_agent: Codex
- action: PRODUCTION_REPAIR
- title: ORB Context Cycle Cutoff Propagation
- scope: Replace incorrect `now` usage with frozen `cycle_cutoff` for ORB context.
- requested_paths: `core/market_data.py`
- allowed_paths: `core/market_data.py`, `tests/core/test_orb_context_cycle_cutoff.py`
- forbidden_paths: Execution, broker logic, strategy logic, strategy inputs
- expected_tests: `tests/core/test_orb_context_cycle_cutoff.py`
- acceptance_proof: All CE gates pass, fast-suite passes, test demonstrates proper ORB arguments.

## Scope Guard
Verified this change affects only `core/market_data.py` and its related test. No broader changes made.

## Grill Me Review
No risks to strategy logic, execution paths, or feed freshness gates are introduced. The fix merely propagates an already-computed canonical timestamp to a pure function.

## Hermes Review
This honors the canonical strategy-input truth architectural invariant: the ORB context and the historical indicators both use the same shared cycle_cutoff timestamp. No architectural changes were made, only an implementation fix matching the design intent.

## GSD Review
Minimal repair applied successfully: `now_dt=now` changed to `now_dt=cycle_cutoff`. 

## QA / Safety Review
The fix does not modify LIVE behavior directly except correcting an unbound variable. It prevents a swallowed exception from degrading the system to `orb_bias="NEUTRAL"`. A regression test explicitly prevents recurrence and verifies execution safety.

## Acceptance Proof
Fast suite passes, validation scripts pass, CE gates pass.
The new regression test (`tests/core/test_orb_context_cycle_cutoff.py`) successfully asserts that:
1. `_orb_state_from_candles` is invoked exactly once.
2. It receives the frozen `cycle_cutoff`.
3. The forming bar remains excluded.
4. No broker execution occurs.

## Runtime Proof Required After Merge
Yes, the overarching Canonical Strategy-Input Runtime Proof is blocked pending this merge.

## What This PR Does Not Prove
This does not prove all strategy inputs are correct, nor does it guarantee live feed correctness, profitability, or complete production readiness.

## Human Approval
The work requires human approval before merge.
