# Opening Range Retest Temporal Fixture Evidence

## Repository identity
- Worktree: `/Users/madhuram/tradebot-opening-range-retest-temporal-fixtures`
- Branch: `test/opening-range-retest-temporal-fixtures`
- Starting head: `8a5e3974459c5011759bb2eef7ba6b1012d2bce2`
- Frozen temporal-protocol base: `8a5e3974459c5011759bb2eef7ba6b1012d2bce2`
- Shared checkout untouched: `/Users/madhuram/tradebot`

## Scope and architecture assessment
- Implemented: deterministic test-only fixtures and contract evidence for `opening_range_retest_v1`
- Tested: yes, via the accepted Phase 3B temporal harness and direct strategy calls
- Causally proven: only the fixture lane and current snapshot false-positive behavior
- Temporally conformant: not yet
- Historically validated: not attempted
- Production ready: not claimed
- Architecture change: none
- Production logic changed: no

## Production call chain
- Registry identity: `strategies.strategy_registry.OPENING_RANGE_BREAKOUT`
- Production callable: `strategies.movement.opening_range_breakout.generate_opening_range_retest_candidates`
- Temporal contract under audit: `opening_range_retest_temporal_v1`
- Session timezone: `Asia/Kolkata`
- Session window: `09:15-15:30`
- Opening range: first 15 completed one-minute bars, authoritative only after the `09:29` bar completes

## Files changed
- `tests/test_opening_range_retest_temporal_fixture_contract.py`

## Fixture schema
The new test-only lane uses explicit completed one-minute OHLC rows with visible causal transitions:
- opening-range completion
- breakout
- retest
- continuation
- invalidation
- age boundary
- session-end boundary
- future bars

The fixture module defines:
- `_bar(...)`
- `_bars(...)`
- `_opening_range_bars()`
- `_trend_pullback_history_bars()`
- `_trace(...)`
- `_setup_id(...)`
- `_history_hash(...)`

## Current production observation
The live callable still behaves like a time-gated snapshot strategy:
- call-path emissions observed at prefixes `16`, `18`, and `19`
- put-path emissions observed at prefixes `18` and `19`
- the strategy does not enforce the ordered breakout -> retest -> continuation sequence
- `setup_identity` is still absent from emitted candidate evidence in the temporal fixture lane

Observed direct probe fingerprints:
- snapshot control fingerprint remains `opening_range_retest_v1 | BUY_CALL | RAW_CANDIDATE | 0.451504 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held`
- call causal trace emissions: `16`, `18`, `19`
- put causal trace emissions: `18`, `19`

## Fixture controls
Passing controls:
- ORB recomputation from completed opening-range history
- canonical setup ID helper determinism
- causal history hash helper determinism
- snapshot fingerprint preservation
- unrelated strategy controls
- no-breakout subcase in the session-end test
- duplicate timestamp rejection by the history builder

Expected red evidence:
- valid CALL continuation is emitted too early
- valid PUT continuation is emitted too early
- wick-only and equality cases are not causally enforced
- same-bar breakout/retest is not rejected
- breakout age boundary is not enforced
- retest age boundary is not enforced
- invalidation does not force a fresh setup identity
- session-end breakout/retest cases still emit
- ORB mismatch is not blocked
- mixed-symbol malformed history is not rejected by the current builder path

## Test matrix
| Test | Classification | Result |
|---|---|---|
| `test_fixture_orb_recomputes_from_completed_opening_range` | PASSING CONTROL | passed |
| `test_canonical_setup_identity_and_history_hash_helper_are_deterministic_for_identical_causal_inputs` | PASSING CONTROL | passed |
| `test_snapshot_fingerprint_control_preserves_the_accepted_current_output` | PASSING CONTROL | passed |
| `test_unrelated_strategy_controls_remain_stable` | PASSING CONTROL | passed |
| `test_valid_sequences_emit_only_after_later_continuation` | EXPECTED TEMPORAL RED | failed |
| `test_wick_only_and_equality_cases_do_not_qualify` | EXPECTED TEMPORAL RED | failed |
| `test_same_bar_breakout_and_retest_do_not_qualify` | EXPECTED TEMPORAL RED | failed |
| `test_breakout_to_retest_age_boundary` | EXPECTED TEMPORAL RED | failed |
| `test_retest_to_continuation_age_boundary` | EXPECTED TEMPORAL RED | failed |
| `test_invalidation_requires_fresh_setup_identity_and_stops_revival` | EXPECTED TEMPORAL RED | failed |
| `test_no_pre_breakout_lineage_and_session_end_behaviour` | EXPECTED TEMPORAL RED | failed |
| `test_orb_mismatch_is_blocked_and_supplied_orb_never_overrides_completed_history` | EXPECTED TEMPORAL RED | failed |
| `test_malformed_history_controls_fail_closed_before_strategy_execution` | EXPECTED TEMPORAL RED | failed |

## Exact counts
- Fixture module: `9 passed, 10 failed`
- Existing opening-range temporal audit: `20 passed`
- Nearby strategy slice: `39 passed`
- Static compilation: passed
- `git diff --check`: passed

## Commands and exit codes
- `python -m py_compile tests/test_opening_range_retest_temporal_fixture_contract.py` -> `0`
- `git diff --check` -> `0`
- `python -m pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py` -> `1`
- `python -m pytest -q tests/test_opening_range_retest_temporal_audit.py` -> `0`
- `python -m pytest -q tests/test_strategy_temporal_harness.py tests/test_opening_movement_strategies.py tests/test_trend_pullback_temporal_semantics.py` -> `0`

## Remaining contract gaps
- Production logic still does not enforce the causal breakout/retest/continuation sequence.
- The strategy still emits from snapshot fields before the later continuation bar.
- Mixed-symbol malformed-history rejection is not yet centralized in the fixture lane; the current builder path does not inspect raw bar symbol fields.
- `setup_identity` and temporal lineage memory are still absent from the production candidate evidence path.

## Explicit non-claims
- No production strategy repair was made.
- No temporal conformance was proven.
- No historical edge, profitability, or production readiness claim was made.
- No owner-store, profile, or threshold behavior was modified.

## Claim boundary
This lane closes the isolated fixture-and-evidence work only. It establishes deterministic causal fixtures and red temporal-contract evidence for later repair, but it does not repair `opening_range_retest_v1`.
