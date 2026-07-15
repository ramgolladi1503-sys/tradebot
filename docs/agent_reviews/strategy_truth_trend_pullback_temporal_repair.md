IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Complete the `trend_pullback_v1` temporal contract by making completed-bar history first-class, removing the fail-open previous-close fallback, and failing closed on missing or inconsistent temporal evidence without changing strategy formulas, thresholds, or the accepted candidate fingerprint.

WHAT WAS ACTUALLY IMPLEMENTED:
`StrategyContext` now carries `completed_bar_history` as an explicit field, and the runtime adapter propagates it from the existing truth payload into the context. `trend_pullback_v1` now derives its temporal state from the last four completed bars in that history, emits a deterministic `STRATEGY_EVIDENCE_BLOCKED` event when the history is missing or inconsistent, and no longer treats a missing `previous_completed_close` as an acceptable fallback.

The acceptance fixtures were updated to supply causal completed-bar history everywhere `trend_pullback_v1` is expected to emit, so the accepted primary-context direct and pool fingerprints remain unchanged. A separate temporal-semantics fixture exercises a different four-bar chronology and therefore produces a different raw score, but that is a context-specific consequence of the new temporal contract rather than a formula change.

ARCHITECTURE CHANGE:
NECESSARY_MINIMAL

REQUIRED FIXES COMPLETED:
3
- Added `completed_bar_history` to `StrategyContext` and propagated it through `core.runtime_snapshot_producer._strategy_context_from_market_symbol`.
- Reworked `strategies/movement/trend_pullback.py` to derive temporal state from completed history, fail closed on missing temporal evidence, and emit deterministic blocked evidence.
- Updated trend_pullback fixtures and contract tests so the accepted fingerprint still emits with truthful completed history.

REQUIRED FIXES REMAINING:
0

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

STARTING HEAD:
9614c4ab08a20573d565073999f4d40aefcaff33

FINAL HEAD:
pending commit

FILES CHANGED:
- `core/movement_contract.py`
- `core/runtime_snapshot_producer.py`
- `strategies/movement/trend_pullback.py`
- `tests/test_candidate_phase2_ownership.py`
- `tests/test_candidate_phase2_semantic_ownership.py`
- `tests/test_compression_trend_movement_strategies.py`
- `tests/test_strategy_context_truth.py`
- `tests/test_strategy_missing_evidence_observability.py`
- `tests/test_strategy_missing_evidence_policy.py`
- `tests/test_strategy_profile_fail_closed.py`
- `tests/test_strategy_registry_integrity.py`
- `tests/test_strategy_temporal_harness.py`
- `tests/test_trend_pullback_temporal_conformance.py`
- `docs/agent_reviews/strategy_truth_trend_pullback_temporal_repair.md`

COMPLETE CONTEXT CONTRACT:
`completed_bar_history` is authoritative completed-bar evidence for `trend_pullback_v1`.
The strategy consumes the last four completed closes from that history and no longer depends on `previous_completed_close` alone.

TEMPORAL CONTRACT VERSION:
`trend_pullback_temporal_v1`

MINIMUM HISTORY:
4 completed `1m` bars

TEMPORAL STATE RESULT:
CALL side requires a causal trend-establishment sequence, a controlled pullback that holds structure, and a continuation trigger that reclaims VWAP.
PUT side requires the mirrored causal sequence with resistance as the anchor.

BLOCKED-EVENT RESULT:
Missing or inconsistent completed-bar history emits
`event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=trend_pullback_v1 missing_fields=completed_bar_history invalid_fields=- reason=missing_required_temporal_evidence`
or the matching invalid-field variant when the history is malformed.

DIRECT-CONTEXT FINGERPRINT:
`opening_range_retest_v1`, `0.328053`, `BUY_CALL`, `VALIDATED_CANDIDATE`
`compression_breakout_v1`, `0.470676`, `BUY_CALL`, `VALIDATED_CANDIDATE`
`trend_pullback_v1`, `0.648584`, `BUY_CALL`, `VALIDATED_CANDIDATE`

TEMPORAL TRACE RESULT:
Prefix 1: no candidate
Prefix 2: no candidate
Prefix 3: no candidate
Prefix 4: one `trend_pullback_v1` candidate
Prefix 5: no repeated candidate

EMISSION FINGERPRINT:
`trend_pullback_v1`
`BUY_CALL`
`RAW_CANDIDATE`
`0.648584` in the accepted primary context; `0.612584` in the stricter ad hoc semantics fixture
`trend_pullback_hold_resume`
`pullback_breaks_anchor`
`established trend resumed after a controlled pullback`

RAW OWNERSHIP RESULT:
The generator still emits `RAW_CANDIDATE` at the movement layer.

DOWNSTREAM OWNERSHIP RESULT:
No downstream Phase-2 ownership claims were added or changed here.

BEHAVIOR CHANGED:
`trend_pullback_v1` now fails closed when its completed-bar history is missing or inconsistent, and its temporal gate is derived from completed history rather than a scalar-only fallback.

BEHAVIOR PRESERVED:
The accepted candidate identity, direction, score, trigger text, invalidation text, and direct-context fingerprint remain unchanged when the truthful completed history is present.

FOCUSED TEST RESULT:
`139 passed, 1 warning in 5.26s`

FULL-SUITE RESULT:
`1 failed, 5817 passed, 1 deselected, 935 warnings in 373.68s`

FIRST FAILURE:
`tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`

The failure is pre-existing and still reports:
`RuntimeError:[AUTH] missing_kite_access_token`

REMAINING RISKS:
The repo still has one known auth-related full-suite failure that is unrelated to this temporal-contract repair.

ROLLBACK:
Remove the `completed_bar_history` field from `StrategyContext`, revert the runtime snapshot propagation, and restore the old `previous_completed_close` fallback in `strategies/movement/trend_pullback.py`.

EXPLICIT NON-CLAIMS:
No formulas changed.
No thresholds changed.
No other movement strategy changed.
No profitability claim was made.
No broker, order, execution, or feed behavior was altered.
