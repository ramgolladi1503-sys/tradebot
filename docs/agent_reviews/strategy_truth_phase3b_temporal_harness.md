# Strategy Truth Phase 3B Temporal Harness

IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Build a reusable causal temporal setup-conformance harness, integrate the accepted restart-persistence ancestry, and finish the Phase 3B temporal proof gate without changing strategy formulas, thresholds, ownership, or execution behavior.

WHAT WAS ACTUALLY IMPLEMENTED:
Added an explicit audit-only temporal trace model and oracle hook in [`core/strategy_temporal_harness.py`](../../core/strategy_temporal_harness.py), plus deterministic proof tests for prefix traversal, future-mutation invariance, truncation equivalence, prefix determinism, session reset, invalidation causality, no premature emission, single emission, and repeated-emission detection. Added a trend_pullback readiness audit and a separate temporal-semantics audit that classifies the current behavior as `SNAPSHOT_FALSE_POSITIVE`. Integrated the accepted restart-persistence ancestry via cherry-picked commits `627cca14` and `acc9e053`. No production movement strategy logic was changed.

RUNTIME ARCHITECTURE CHANGE:
NONE

AUDIT ARCHITECTURE CHANGE:
Added a reusable causal temporal setup-conformance harness with explicit trace states, oracle-driven observations, and repeated-emission detection.

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

INTEGRATION STATUS:
COMPLETE

FILES CHANGED:
- `core/strategy_temporal_harness.py`
- `tests/test_strategy_temporal_harness.py`
- `tests/test_trend_pullback_temporal_conformance.py`
- `docs/agent_reviews/strategy_truth_phase3b_temporal_harness.md`

STARTING HEAD:
`5d11ce2b0a5e16962fd6b6fb4f6ada0823c17f7f`

PHASE 3A3 ACCEPTED BASE:
`272b80774a0d0afed951783d2eddc40d81e61494`

PHASE 3B INITIAL HARNESS:
`5d11ce2b0a5e16962fd6b6fb4f6ada0823c17f7f`

RESTART IMPLEMENTATION SOURCE:
`e66163dc74bf10595ee758e6dfcf77ad03e8946f`

RESTART EVIDENCE SOURCE:
`ebe904eaec4f864186ccb49a67b88cbd2c3db8ab`

RESTART IMPLEMENTATION INTEGRATED COMMIT:
`627cca1412258af32c03e7f309b78d2914703687`

RESTART EVIDENCE INTEGRATED COMMIT:
`acc9e05385c6269cadf0b21ce203b87a3fc3540c`

PHASE 3B FINAL PROOF BASE:
`acc9e05385c6269cadf0b21ce203b87a3fc3540c`

ORIGINAL DIRTY FILE PRESERVED:
YES

PRESERVED PATCH PATH:
`/tmp/phase3b_temporal_harness_uncommitted.patch`

PRESERVED PATCH HASH:
`199a0b78f62440842a3fd8432cf45ba2f541f6a458e8055de7207f30c00a9bd3`

PATCH APPLIED:
NO

PATCH REVIEW RESULT:
The preserved patch was a stale blocked-handoff evidence diff and did not add useful proof for the integrated continuation branch, so it was kept outside Git and not applied.

COMPLETE TEMPORAL TRACE MODEL:
- `strategy_id`
- `symbol`
- `session_id`
- `prefix_bar_count`
- `checkpoint_timestamp`
- `history_hash`
- `setup_state_before`
- `observed_conditions`
- `transition`
- `setup_state_after`
- `candidate_emitted`
- `candidate_semantic_fingerprint`
- `invalidation_reason`
- `blocker_reason`
- `provenance`

ORACLE CONTRACT:
- A test-only oracle drives the harness state model.
- The harness keeps prefix replay causal and immutable.
- The oracle records actual candidate emission and semantic fingerprints without mutating production strategies.

COMPLETE TEMPORAL INPUT INVENTORY:
| strategy_id | temporal class | current temporal inputs | current audit posture |
| --- | --- | --- | --- |
| `opening_drive_v1` | session-open setup | `minutes_since_open`, `open_price`, `vwap`, `orb_high`, `orb_low`, `spot_ltp` | time-gated snapshot setup |
| `opening_range_retest_v1` | opening-range setup | `minutes_since_open`, `spot_ltp`, `vwap`, `orb_high`, `orb_low` | time-gated snapshot setup |
| `compression_breakout_v1` | volatility-compression setup | `spot_ltp`, `vwap`, `range_width_pct`, `atr_short`, `atr_long`, `nearest_support`, `nearest_resistance`, `day_high`, `day_low`, `orb_high`, `orb_low` | prefix-ready but snapshot-driven |
| `trend_pullback_v1` | trend-resume setup | `spot_ltp`, `vwap`, `nearest_support`, `nearest_resistance`, `trend_up/down regime scores` | first deep audit target |
| `vwap_reclaim_rejection_v1` | reclaim/rejection setup | `spot_ltp`, `vwap`, `vwap_slope`, `previous_spot_ltp` / metadata confirmation, `volume_z` | snapshot-driven with explicit confirmatory evidence |
| `failed_breakout_trap_v1` | failed-break / re-entry setup | `spot_ltp`, `day_high`, `day_low`, `orb_high`, `orb_low`, `nearest_support`, `nearest_resistance`, `previous_break_high`, `previous_break_low`, `price_reentered_range`, `ce_premium_change`, `pe_premium_change`, `volume_z` | snapshot-driven with metadata confirmations |
| `exhaustion_reversal_v1` | stretch / stall setup | `spot_ltp`, `vwap`, `ce_premium_change`, `pe_premium_change`, `volume_z`, exhaustion regime scores | snapshot-driven and conservative |
| `mean_reversion_extension_v1` | range-extension setup | `spot_ltp`, `vwap`, `nearest_support`, `nearest_resistance`, `day_high`, `day_low`, `ce_premium_change`, `pe_premium_change`, `volume_z`, range/chop regime scores | snapshot-driven with range boundary anchors |
| `event_volatility_expansion_v1` | volatility-expansion setup | `spot_ltp`, `vwap`, `atr_short`, `atr_long`, `volume_z`, volatility-expansion regime score | snapshot-driven ratio setup |
| `late_day_momentum_v1` | session-close setup | `minutes_since_open`, `minutes_to_close`, `spot_ltp`, `vwap`, `volume_z`, `expiry_context` | time-gated snapshot setup |

TEMPORAL HARNESS DESIGN:
- The harness runs a strategy across every causal completed-bar prefix produced by `core.session_bar_history.build_session_bar_history_state`
- It captures prefix count, history hash, checkpoint timestamp, provenance, explicit setup-state transitions, and semantic fingerprints for each step
- It fingerprints actual `StrategyCandidate` outputs instead of relying on mocked candidate shapes
- It does not mutate candidate logic, thresholds, or score formulas

FUTURE-MUTATION RESULT:
PASS

TRUNCATION RESULT:
PASS

PREFIX-DETERMINISM RESULT:
PASS

SESSION-RESET RESULT:
PASS

INVALIDATION RESULT:
PASS

PREMATURE-EMISSION RESULT:
PASS

SINGLE-EMISSION RESULT:
PASS

REPEATED-EMISSION DETECTION RESULT:
PASS

TREND_PULLBACK CONTEXT-READINESS RESULT:
CONTEXT_READINESS_GATING

TREND_PULLBACK TEMPORAL CLASSIFICATION:
SNAPSHOT_FALSE_POSITIVE

EARLIEST ACTUAL EMISSION:
prefix 1

EXPECTED TEMPORAL EMISSION:
prefix 3

INVALIDATION RESPECTED:
NOT_TESTED_IN_THIS_STRATEGY_AUDIT

SESSION RESET RESPECTED:
YES

REPEATED EMISSION COUNT:
3

PRODUCTION STRATEGY CHANGED:
NO

FOCUSED TEST RESULT:
`12 passed in 1.01s`

FOCUSED REGRESSION RESULT:
`87 passed in 5.90s`

STATIC CHECK RESULT:
`python -m py_compile`, `ruff check`, and `git diff --check` all passed for the modified Phase 3B files.

FULL-SUITE RESULT:
`1 failed, 5810 passed, 1 deselected, 934 warnings in 392.17s`

FAILURE CLASSIFICATION:
PREEXISTING_ENVIRONMENT_CREDENTIAL

FIRST FAILURE:
`tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`

The failure remained the established missing-token baseline:
`RuntimeError:[AUTH] missing_kite_access_token`

EXPECTED TRUTH CORRECTIONS:
- The harness now records explicit temporal states instead of only candidate fingerprints.
- Trend pullback is no longer overstated as temporally conformant; the current audit reads as a snapshot false positive with repeated emission risk.
- Restart ancestry is now integrated through patch-equivalent cherry-picks, not assumed from the initial harness base.

UNEXPECTED CHANGES:
None observed in the Phase 3B proof path.

RISKS:
- The harness remains audit-only and depends on explicit oracle/test fixtures.
- The full suite still has the established repository auth-token failure outside this phase.

ROLLBACK:
- Remove `core/strategy_temporal_harness.py`, the two temporal test files, and this evidence note if the audit direction is rejected.

EXPLICIT NON-CLAIMS:
- No claim of profitability or temporal alpha.
- No strategy formula, threshold, or ownership change.
- No production runtime context propagation change.
- No fix to the repository-wide auth-token baseline.
