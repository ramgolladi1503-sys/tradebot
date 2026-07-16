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
- `docs/agent_reviews/strategy_truth_opening_range_retest_temporal_fixture_evidence.md`

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
- call-path emissions observed at prefixes `16`, `18`, `19`, and `20`
- put-path emissions observed at prefixes `16`, `17`, `18`, `19`, and `20`
- the first emission checkpoint for both directions is still `2026-07-14T09:31:00+05:30`
- the strategy does not enforce the ordered breakout -> retest -> continuation sequence
- `setup_identity` is still absent from emitted candidate evidence in the temporal fixture lane

Observed direct probe fingerprints:
- snapshot control fingerprint remains `opening_range_retest_v1 | BUY_CALL | RAW_CANDIDATE | 0.451504 | opening_range_breakout_retest_hold | price_returns_inside_opening_range | opening range breakout retest held`
- call causal trace emissions: `16`, `18`, `19`, `20`
- put causal trace emissions: `16`, `17`, `18`, `19`, `20`

## Fixture controls
Passing controls:
- ORB recomputation from completed opening-range history
- canonical setup ID helper determinism
- causal history hash helper determinism
- snapshot fingerprint preservation
- explicit candidate payload preservation with `proposal_ready_at_iso` still absent
- future-mutation and physical-truncation equivalence for CALL and PUT
- malformed-history classification matrix for builder acceptance vs rejection vs no-candidate behavior
- unrelated strategy controls
- no-breakout subcase in the session-end test
- duplicate timestamp rejection by the history builder

Expected red evidence:
- valid CALL continuation is emitted too early and multiple prefix emissions still occur
- valid PUT continuation is emitted too early and multiple prefix emissions still occur
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
| `test_future_mutation_and_physical_truncation_preserve_candidate_payload_and_history_hash[call_future_mutation-rows0-<lambda>-ORB_HIGH-22600.0-future_rows0]` | PASSING CONTROL | passed |
| `test_future_mutation_and_physical_truncation_preserve_candidate_payload_and_history_hash[put_future_mutation-rows1-<lambda>-ORB_LOW-22500.0-future_rows1]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[mixed_symbol]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[mixed_session]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[out_of_order]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[duplicate]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[missing_bar]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[cadence_30s]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[nan_ohlc]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[inf_ohlc]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[neg_inf_ohlc]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[high_below_low]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[open_outside]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[close_outside]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[incomplete_current]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[pre_session]` | PASSING CONTROL | passed |
| `test_malformed_history_controls_record_current_behavior[post_session]` | PASSING CONTROL | passed |
| `test_orb_reconciliation_matrix_records_current_behavior[orb_match-ctx_overrides0-True-0.385133]` | PASSING CONTROL | passed |
| `test_valid_sequences_emit_only_after_later_continuation` | EXPECTED TEMPORAL RED | failed |
| `test_wick_only_and_equality_cases_do_not_qualify` | EXPECTED TEMPORAL RED | failed |
| `test_same_bar_breakout_and_retest_do_not_qualify` | EXPECTED TEMPORAL RED | failed |
| `test_breakout_to_retest_age_boundary` | EXPECTED TEMPORAL RED | failed |
| `test_retest_to_continuation_age_boundary` | EXPECTED TEMPORAL RED | failed |
| `test_invalidation_requires_fresh_setup_identity_and_stops_revival` | EXPECTED TEMPORAL RED | failed |
| `test_equality_does_not_invalidate_and_later_valid_sequence_still_emits[call_equality_then_valid-rows0-<lambda>-2026-07-14T09:31:00+05:30]` | EXPECTED TEMPORAL RED | failed |
| `test_equality_does_not_invalidate_and_later_valid_sequence_still_emits[put_equality_then_valid-rows1-<lambda>-2026-07-14T09:31:00+05:30]` | EXPECTED TEMPORAL RED | failed |
| `test_no_pre_breakout_lineage_and_session_end_behaviour` | EXPECTED TEMPORAL RED | failed |
| `test_orb_reconciliation_matrix_records_current_behavior[orb_absent-ctx_overrides1-False-None]` | EXPECTED TEMPORAL RED | failed |
| `test_orb_reconciliation_matrix_records_current_behavior[orb_high_mismatch-ctx_overrides2-False-None]` | EXPECTED TEMPORAL RED | failed |
| `test_orb_reconciliation_matrix_records_current_behavior[orb_low_mismatch-ctx_overrides3-False-None]` | EXPECTED TEMPORAL RED | failed |
| `test_orb_reconciliation_matrix_records_current_behavior[orb_both_mismatch-ctx_overrides4-False-None]` | EXPECTED TEMPORAL RED | failed |
| `test_malformed_history_controls_fail_closed_before_strategy_execution` | EXPECTED TEMPORAL RED | failed |

## Exact counts
- Fixture module: `28 passed, 16 failed`
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
- ORB mismatch and absent-ORB cases still do not fail closed in the way the desired contract would require.
- Session-end breakout/retest cases still emit.

## Explicit non-claims
- No production strategy repair was made.
- No temporal conformance was proven.
- No historical edge, profitability, or production readiness claim was made.
- No owner-store, profile, or threshold behavior was modified.

## Claim boundary
This lane closes the isolated fixture-and-evidence work only. It establishes deterministic causal fixtures and red temporal-contract evidence for later repair, but it does not repair `opening_range_retest_v1`.
