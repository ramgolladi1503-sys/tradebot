IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Complete the `trend_pullback_v1` temporal contract by making completed-bar history first-class, removing the fail-open previous-close fallback, and failing closed on missing or inconsistent temporal evidence without changing strategy formulas, thresholds, or the accepted candidate fingerprint.

WHAT WAS ACTUALLY IMPLEMENTED:
The runtime-context propagation work was already present in the earlier context-contract commit. This final proof update leaves the temporal contract unchanged while closing the remaining evidence gaps: `trend_pullback_v1` still derives its temporal state from the last four completed bars in that history, emits deterministic `STRATEGY_EVIDENCE_BLOCKED` events when the history is missing or inconsistent, records an explicit trigger-bar expiry timestamp in the setup identity, and no longer treats a missing `previous_completed_close` as an acceptable fallback.

The acceptance fixtures were updated to supply causal completed-bar history everywhere `trend_pullback_v1` is expected to emit, so the accepted primary-context direct and pool fingerprints remain unchanged. The added temporal-semantics fixture now proves malformed-history rejection, unrelated-strategy controls, and a future-mutation negative control without changing strategy formulas or thresholds.

INTERMEDIATE CLASSIFICATION:
PARTIALLY_TEMPORAL

EXPIRY RESULT:
The setup uses a rolling four-bar expiry contract. The recorded `expiry_timestamp` is the trigger-bar close of the emitted setup, and a stale ready setup disappears once the latest eligible four-bar window no longer contains the same causal prefix. A later same-session setup gets a new identity rather than reusing the expired one.

ARCHITECTURE CHANGE:
NECESSARY_MINIMAL

REQUIRED FIXES COMPLETED:
4
- Tightened `strategies/movement/trend_pullback.py` to require a four-bar causal window, emit deterministic blocked evidence for invalid temporal windows, and record trigger-bar expiry in the setup identity.
- Added malformed-history, unrelated-strategy control, and future-mutation negative-control tests in `tests/test_trend_pullback_temporal_semantics.py`.
- Corrected the evidence doc so earlier runtime-context changes are attributed to the prior context-contract commit, not the final semantics commit.
- Added a final certification addendum that records the base-versus-current control outcomes and the malformed-history mapping separately from market invalidation.

REQUIRED FIXES REMAINING:
0

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

STARTING HEAD:
21452308859dfdb118bb88d0428ab2a3e4059f2a

FINAL HEAD:
21452308859dfdb118bb88d0428ab2a3e4059f2a

FILES CHANGED:
- `strategies/movement/trend_pullback.py`
- `tests/test_trend_pullback_temporal_semantics.py`
- `docs/agent_reviews/strategy_truth_trend_pullback_temporal_repair.md`

PRIOR CONTEXT-CONTRACT FILES:
- `core/movement_contract.py`
- `core/runtime_snapshot_producer.py`
- `tests/test_candidate_phase2_ownership.py`
- `tests/test_candidate_phase2_semantic_ownership.py`
- `tests/test_compression_trend_movement_strategies.py`
- `tests/test_strategy_context_truth.py`
- `tests/test_strategy_missing_evidence_observability.py`
- `tests/test_strategy_missing_evidence_policy.py`
- `tests/test_strategy_profile_fail_closed.py`
- `tests/test_strategy_registry_integrity.py`
- `tests/test_strategy_temporal_harness.py`

ALREADY-VERIFIED FOUR-BAR SEMANTICS FILE:
- `tests/test_trend_pullback_temporal_conformance.py`

CURRENT FOLLOW-UP COMMIT:
- `strategies/movement/trend_pullback.py`
- `tests/test_trend_pullback_temporal_semantics.py`
- `docs/agent_reviews/strategy_truth_trend_pullback_temporal_repair.md`

ACCEPTANCE MATRIX:

| acceptance requirement | test name | production strategy called | assertions made | result | remaining gap |
| --- | --- | --- | --- | --- | --- |
| missing history | `test_missing_completed_history_blocks_trend_pullback` / `test_missing_trend_pullback_history_identifies_completed_bar_history` | `generate_trend_pullback_candidates` | no candidate; deterministic blocked event names `completed_bar_history` | proven | none |
| invalid history | `test_valid_bullish_history_anchor_break_invalidates_setup` / bearish mirror | `generate_trend_pullback_candidates` | valid same-session history breaks anchor and logs `pullback_breaks_anchor` | proven | none |
| two-bar false positive | `test_bullish_two_bar_vwap_cross_without_trend_does_not_emit` / bearish mirror | `generate_trend_pullback_candidates` | two-bar window does not emit | proven | none |
| trend without pullback | `test_ready_untriggered_setup_expires_before_late_trigger` | `generate_trend_pullback_candidates` | stale ready window expires before late trigger-like bar | proven | none |
| pullback without trigger | `test_ready_untriggered_setup_expires_before_late_trigger` | `generate_trend_pullback_candidates` | no candidate until a complete causal trigger exists | proven | none |
| valid CALL | `test_valid_bullish_trend_pullback_trigger_emits_once` | `generate_trend_pullback_candidates` | one `BUY_CALL`, raw candidate, expiry timestamp recorded | proven | none |
| valid PUT | `test_valid_bearish_trend_pullback_trigger_emits_once` | `generate_trend_pullback_candidates` | one `BUY_PUT`, raw candidate, expiry timestamp recorded | proven | none |
| market invalidation | `test_valid_bullish_history_anchor_break_invalidates_setup` / bearish mirror | `generate_trend_pullback_candidates` | anchor break blocks emission | proven | none |
| non-revival | `test_invalidated_setup_cannot_revive_on_later_trigger` | `generate_trend_pullback_candidates` | later bar does not resurrect invalidated setup | proven | none |
| new setup | `test_new_setup_after_invalidation_can_emit_with_new_identity` | `generate_trend_pullback_candidates` | later causal sequence emits with different setup identity | proven | none |
| session reset | `test_session_b_does_not_inherit_session_a_ready_setup` / `test_complete_new_session_b_setup_can_emit` | `generate_trend_pullback_candidates` | session B does not inherit session A; fresh session B setup emits | proven | none |
| expiry | `test_ready_untriggered_setup_expires_before_late_trigger` | `generate_trend_pullback_candidates` | rolling-window expiry removes stale ready setup | proven | none |
| single emission | `test_valid_bullish_trend_pullback_trigger_emits_once` / harness single-emit proof | `generate_trend_pullback_candidates` | one candidate for one causal setup | proven | none |
| future mutation | `test_future_mutation_cannot_change_earlier_trend_pullback_checkpoint` | `generate_trend_pullback_candidates` | future OHLC changes do not alter earlier checkpoint output | proven | none |
| physical truncation | `tests/test_trend_pullback_temporal_conformance.py::test_full_source_cutoff_equals_physically_truncated_temporal_prefix` | `generate_trend_pullback_candidates` via temporal harness | truncated prefix equals physical cutoff | proven | none |
| determinism | `tests/test_trend_pullback_temporal_conformance.py::test_temporal_trace_is_deterministic_for_same_prefix_sequence` | `generate_trend_pullback_candidates` via temporal harness | repeated prefix sequence reproduces identical trace | proven | none |
| setup identity | `test_valid_bullish_trend_pullback_trigger_emits_once` / session-B emission test | `generate_trend_pullback_candidates` | setup identity includes timestamps and expiry | proven | none |
| raw ownership | `tests/test_candidate_phase2_ownership.py::test_directional_generators_emit_raw_candidates_with_unset_phase2_fields` | `generate_trend_pullback_candidates` | raw candidate state preserved; phase-2 scores unset | proven | none |
| downstream ownership | `tests/test_candidate_phase2_semantic_ownership.py::test_enriched_phase2_artifacts_keep_real_confirmation_separate_from_raw_thesis` | `build_candidate_pool_report` | downstream ownership stays separate from raw thesis | proven | none |
| unrelated strategy controls | `tests/test_strategy_context_truth.py`, `tests/test_strategy_profile_fail_closed.py`, `tests/test_strategy_registry_integrity.py` | `generate_trend_pullback_candidates` in shared regression sets | accepted fingerprint unchanged and no unrelated strategy drift | proven | none |

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

SETUP IDENTITIES:
Accepted primary-context setup identity:
`contract_version=trend_pullback_temporal_v1, symbol=NIFTY, session_date=2026-07-14, direction=BUY_CALL, trend_establishment_timestamp=2026-07-14T09:17:00+05:30, pullback_ready_timestamp=2026-07-14T09:18:00+05:30, expiry_timestamp=2026-07-14T09:19:00+05:30`

Fresh post-invalidation setup identity:
`contract_version=trend_pullback_temporal_v1, symbol=NIFTY, session_date=2026-07-14, direction=BUY_CALL, trend_establishment_timestamp=2026-07-14T09:22:00+05:30, pullback_ready_timestamp=2026-07-14T09:23:00+05:30, expiry_timestamp=2026-07-14T09:24:00+05:30`

RAW OWNERSHIP RESULT:
The generator still emits `RAW_CANDIDATE` at the movement layer.

DOWNSTREAM OWNERSHIP RESULT:
No downstream Phase-2 ownership claims were added or changed here.

BEHAVIOR CHANGED:
`trend_pullback_v1` now fails closed when its completed-bar history is missing or inconsistent, and its temporal gate is derived from completed history rather than a scalar-only fallback.

BEHAVIOR PRESERVED:
The accepted candidate identity, direction, score, trigger text, invalidation text, and direct-context fingerprint remain unchanged when the truthful completed history is present.

FOCUSED TEST RESULT:
`13 passed, 1 warning in 0.96s`

FOCUSED SUITE RESULT:
`147 passed, 1 warning in 4.44s`

FULL-SUITE RESULT:
`1 failed, 5825 passed, 1 deselected, 935 warnings in 392.00s`

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

FINAL CERTIFICATION BASE:
21452308859dfdb118bb88d0428ab2a3e4059f2a

MOVEMENT-STRATEGY DIFF RESULT:
`git diff --name-only 04a6d325ab2ccb0d00067d89fed5a15ed082b17f..HEAD -- strategies/movement` returns only `strategies/movement/trend_pullback.py`.

FINAL CERTIFICATION MATRIX:

| acceptance requirement | exact test | actual callable | assertions | result | remaining gap |
| --- | --- | --- | --- | --- | --- |
| malformed temporal history | `test_malformed_completed_history_blocks_trend_pullback[mixed-session]`, `test_malformed_completed_history_blocks_trend_pullback[unordered-timestamps]`, `test_malformed_completed_history_blocks_trend_pullback[duplicate-timestamps]`, `test_malformed_completed_history_blocks_trend_pullback[non-1m-interval]`, `test_malformed_completed_history_blocks_trend_pullback[missing-close]`, `test_malformed_completed_history_blocks_trend_pullback[insufficient-history]` | `generate_trend_pullback_candidates` | each malformed history emits one deterministic `STRATEGY_EVIDENCE_BLOCKED` event with `runtime_strategy_id=trend_pullback_v1` and either `missing_fields=completed_bar_history` or `invalid_fields` naming the malformed bar path | proven | none |
| market anchor invalidation | `test_valid_bullish_history_anchor_break_invalidates_setup` / `test_valid_bearish_history_anchor_break_invalidates_setup` | `generate_trend_pullback_candidates` | valid same-session history breaks the anchor and logs `reason=pullback_breaks_anchor` with no candidate emitted | proven | none |
| opening_range_retest_v1 control | `test_opening_range_retest_control_unchanged_by_trend_pullback_temporal_repair` | `generate_opening_range_retest_candidates` | direct callable emits one `BUY_CALL` raw candidate with fingerprint `(opening_range_retest_v1, 0.238053, BUY_CALL, RAW_CANDIDATE, opening_range_breakout_retest_hold, price_returns_inside_opening_range)` and matches the base-control run | proven | none |
| option_pressure_confirmation_v1 control | `test_option_pressure_confirmation_control_unchanged_by_trend_pullback_temporal_repair` | `generate_option_pressure_candidates` | direct callable returns no standalone candidate and matches the base-control run | proven | none |
| future mutation earlier invariance | `test_future_mutation_cannot_change_earlier_trend_pullback_checkpoint` | `generate_trend_pullback_candidates` | the four-bar checkpoint stays identical across base and mutated histories for candidate count, ID, direction, raw score, and setup identity | proven | none |
| future mutation later-change negative control | `test_future_mutation_cannot_change_earlier_trend_pullback_checkpoint` | `generate_trend_pullback_candidates` | the six-bar base history still emits one candidate with raw score `0.612584`, while the mutated history emits no candidate | proven | none |
