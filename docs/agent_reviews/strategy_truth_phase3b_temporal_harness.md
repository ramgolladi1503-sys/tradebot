# Strategy Truth Phase 3B Temporal Harness

## IMPLEMENTATION DIRECTION
RIGHT

## APPROVED OBJECTIVE
Build a common temporal setup-conformance harness over causal completed-bar prefixes and begin the trend_pullback audit without changing strategy formulas, thresholds, or candidate ownership.

## WHAT WAS ACTUALLY IMPLEMENTED
- Added a shared temporal harness in [`core/strategy_temporal_harness.py`](/Users/madhuram/tradebot-strategy-phase3b/core/strategy_temporal_harness.py)
- Added generic harness coverage in [`tests/test_strategy_temporal_harness.py`](/Users/madhuram/tradebot-strategy-phase3b/tests/test_strategy_temporal_harness.py)
- Added a first strategy-level temporal audit for trend_pullback in [`tests/test_trend_pullback_temporal_conformance.py`](/Users/madhuram/tradebot-strategy-phase3b/tests/test_trend_pullback_temporal_conformance.py)
- Recorded the current temporal classification and strategy input inventory in this evidence note
- No production movement strategy logic was changed

## ARCHITECTURE CHANGE
NONE

## REQUIRED FIXES COMPLETED
4
- Common harness for causal completed-bar prefix evaluation
- Deterministic candidate fingerprinting for setup conformance
- First trend_pullback prefix audit over causal history
- Evidence note for the temporal audit boundary

## REQUIRED FIXES REMAINING
0

## SCOPE STATUS
IN_SCOPE

## EVIDENCE STATUS
PROVEN

## STARTING COMMIT
- `951673de6dfb3c5b94bd6da19317111fae0d172b`

## PHASE 3A2 COMMIT
- `272b80774a0d0afed951783d2eddc40d81e61494`

## PHASE 3A3 COMMIT
- `3479b898072ead19bea0bc563a016d97be75a1d0`

## PHASE 3B OBSERVABILITY COMMIT
- to be recorded in the final commit hash

## FILES CHANGED
- [`core/strategy_temporal_harness.py`](/Users/madhuram/tradebot-strategy-phase3b/core/strategy_temporal_harness.py)
- [`tests/test_strategy_temporal_harness.py`](/Users/madhuram/tradebot-strategy-phase3b/tests/test_strategy_temporal_harness.py)
- [`tests/test_trend_pullback_temporal_conformance.py`](/Users/madhuram/tradebot-strategy-phase3b/tests/test_trend_pullback_temporal_conformance.py)
- [`docs/agent_reviews/strategy_truth_phase3b_temporal_harness.md`](/Users/madhuram/tradebot-strategy-phase3b/docs/agent_reviews/strategy_truth_phase3b_temporal_harness.md)

## COMPLETE TEMPORAL INPUT INVENTORY
### Priority strategy classification
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

## TEMPORAL HARNESS DESIGN
- The harness runs a strategy across every causal completed-bar prefix produced by `core.session_bar_history.build_session_bar_history_state`
- It captures prefix count, history hash, latest completed timestamp, and provenance for each step
- It fingerprints actual `StrategyCandidate` outputs instead of relying on mocked candidate shapes
- It does not mutate candidate logic, thresholds, or score formulas

## TREND_PULLBACK AUDIT
- The first audit uses a causal prefix sequence where the setup becomes ready at the third completed bar
- Before the threshold, `nearest_support` is absent and no candidate is emitted
- After the threshold, the same canonical raw candidate fingerprint appears and remains stable on later prefixes
- The strategy remains snapshot-driven; this phase does not add direct `completed_bar_history` consumption to the generator

## COMPLETE-CONTEXT FINGERPRINT
- `trend_pullback_v1`
- `0.648584`
- `BUY_CALL`
- `RAW_CANDIDATE`
- `trend_pullback_hold_resume`
- `pullback_breaks_anchor`
- `established trend resumed after a controlled pullback`

## EXPECTED OBSERVATIONS
- Causal prefix history changes the setup-ready boundary
- Candidate identity, direction, score, entry trigger, invalidation description, and rank reason remain stable once the setup is complete
- No strategy formula or threshold changed

## UNEXPECTED CHANGES
- None observed in this phase

## PROOF SUMMARY
- Harness test proves deterministic prefix traversal and immutable trace results
- Trend pullback audit proves setup readiness emerges only after the causal prefix threshold and remains stable after it

## FOCUSED TEST RESULT
- `92 passed, 1 warning in 6.62s`

## STATIC CHECK RESULT
- `All checks passed!`

## FULL-SUITE RESULT
- `5801 passed, 1 deselected, 1 failed, 935 warnings in 458.27s (0:07:38)`

## FIRST FAILURE
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- The failure remains the established missing-token baseline: `RuntimeError:[AUTH] missing_kite_access_token`
- The failure text masks the injected `forced_cycle_error`, so the branch did not introduce a new orchestrator-auth path

## RISKS
- The harness still relies on explicit context builders for current strategies because the production generators do not yet consume `completed_bar_history` directly
- The phase remains audit-only; no temporal strategy repair has been introduced

## ROLLBACK
- Remove the new harness module, its tests, and this evidence note if the audit direction is rejected

## EXPLICIT NON-CLAIMS
- No runtime strategy propagation changed
- No thresholds changed
- No setup formulas changed
- No phase-2 ownership behavior changed
- No claim of profitability or temporal alpha is made
