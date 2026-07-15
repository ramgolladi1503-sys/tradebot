# Strategy Truth Phase 3B Temporal Repair

IMPLEMENTATION DIRECTION
RIGHT_WITH_GAPS

APPROVED OBJECTIVE
Repair `trend_pullback_v1` so candidate emission is temporally causal when completed-bar truth is available, without changing the accepted fingerprint, strategy formulas, thresholds, or any other strategy.

WHAT WAS ACTUALLY IMPLEMENTED
`trend_pullback_v1` now uses `previous_completed_close` as a causal transition gate when it is present. A CALL candidate only emits if the prior completed close was still below VWAP; a PUT candidate only emits if the prior completed close was still above VWAP. If `previous_completed_close` is missing, the strategy preserves the legacy compatibility path so direct synthetic contexts continue to produce the accepted fingerprint.

The temporal conformance test fixtures were updated to pass `previous_completed_close` from the causal prefix state. The temporal proof now shows a single emission at prefix 3 and no repeated emission at prefix 4.

ARCHITECTURE CHANGE
NONE

REQUIRED FIXES COMPLETED
2
- Added a causal previous-close transition gate to `strategies/movement/trend_pullback.py`.
- Updated `tests/test_trend_pullback_temporal_conformance.py` to prove a single causal emission instead of repeated snapshot-based emission.

REQUIRED FIXES REMAINING
0

SCOPE STATUS
IN_SCOPE

EVIDENCE STATUS
PARTIALLY_PROVEN

STARTING COMMIT
c5fa5079d18ceca58d8ab8a18a64a7e1b8e8abe7

FILES CHANGED
- `strategies/movement/trend_pullback.py`
- `tests/test_trend_pullback_temporal_conformance.py`
- `docs/agent_reviews/strategy_truth_trend_pullback_temporal_repair.md`

COMPLETE CONTEXT / FINGERPRINT
The direct-context candidate pool fingerprint remained unchanged:
- `opening_range_retest_v1`, `0.328053`, `BUY_CALL`, `VALIDATED_CANDIDATE`
- `compression_breakout_v1`, `0.470676`, `BUY_CALL`, `VALIDATED_CANDIDATE`
- `trend_pullback_v1`, `0.648584`, `BUY_CALL`, `VALIDATED_CANDIDATE`

TEMPORAL REPAIR RESULT
The causal prefix trace now behaves as follows when `previous_completed_close` is supplied:
- prefix 1: no candidate
- prefix 2: no candidate
- prefix 3: one `trend_pullback_v1` candidate
- prefix 4: no repeated candidate

The candidate fingerprint at the emission point remains:
- `trend_pullback_v1`
- `BUY_CALL`
- `RAW_CANDIDATE`
- `0.648584`
- `trend_pullback_hold_resume`
- `pullback_breaks_anchor`
- `established trend resumed after a controlled pullback`

BEHAVIOR CHANGED
`trend_pullback_v1` no longer re-emits on later qualifying prefixes once the prior completed close has already crossed VWAP.

BEHAVIOR PRESERVED
Direct-context output remains unchanged when causal history is absent. The accepted candidate identity, direction, score, trigger text, and invalidation text remain intact.

TESTS AND COUNTS
Focused suite:
- `89 passed in 10.29s`

Full suite:
- `1 failed, 5810 passed, 1 deselected, 934 warnings in 790.13s`

FIRST FAILURE
`tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`

The failure is pre-existing and still reports:
- `RuntimeError:[AUTH] missing_kite_access_token`

RUNTIME ARCHITECTURE CHANGE
NONE

STRATEGY BEHAVIOR CHANGE
EXPECTED_TEMPORAL_CORRECTION

REMAINING RISKS
The repair depends on `previous_completed_close` being present in the runtime context. That field is already populated by the runtime snapshot path in this repository, but any upstream path that omits it will fall back to the legacy compatibility behavior.

ROLLBACK
Revert `strategies/movement/trend_pullback.py` and `tests/test_trend_pullback_temporal_conformance.py` together to return to the prior snapshot-driven behavior.

EXPLICIT NON-CLAIMS
This change does not alter formulas, thresholds, profile resolution, candidate ordering, option confirmation logic, or any other strategy module.
