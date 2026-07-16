IMPLEMENTATION DIRECTION:
RIGHT

VERDICT:
PHASE2B_COMPLETE

APPROVED OBJECTIVE:
Close the Phase 2B missing-evidence observability gap without changing candidate logic, scores, thresholds or setup definitions.

WHAT WAS ACTUALLY IMPLEMENTED:
Added a shared deterministic blocked-event helper in `strategies/movement/_utils.py`, wired required-evidence early returns in the affected generators to emit `STRATEGY_EVIDENCE_BLOCKED`, added focused observability tests in `tests/test_strategy_missing_evidence_observability.py`, and updated this evidence record. No scoring, threshold, setup-definition, or candidate-type changes were made.

ARCHITECTURE CHANGE:
NONE

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

STARTING COMMIT:
`b9142aa04cb977eea9eb9eff0eb6d6a2893c1d85`

PHASE 0 COMMIT:
`cf2d74bc7a2938a08bc651e25b5334481479d68c`

PHASE 1A COMMIT:
`9ace90c0b49d790f0e8926a75ecd9492ae6d3b26`

PHASE 1B COMMIT:
`2a247ec6d92f60aa101d462eb6f3013d1aec4d54`

PHASE 1C COMMIT:
`e74bbac98cfb3db43e15129bc78be4bb47564c45`

PHASE 2A COMMIT:
`db19774008db93671c8a24b93f98cb7488498ad2`

PHASE 2B COMMIT:
`b9142aa04cb977eea9eb9eff0eb6d6a2893c1d85`

FILES CHANGED:
- `strategies/movement/_utils.py`
- `strategies/movement/compression_breakout.py`
- `strategies/movement/event_volatility_expansion.py`
- `strategies/movement/exhaustion_reversal.py`
- `strategies/movement/failed_breakout_trap.py`
- `strategies/movement/late_day_momentum.py`
- `strategies/movement/mean_reversion_extension.py`
- `strategies/movement/opening_drive.py`
- `strategies/movement/opening_range_breakout.py`
- `strategies/movement/option_pressure.py`
- `strategies/movement/trend_pullback.py`
- `strategies/movement/vwap_reclaim.py`
- `tests/test_strategy_missing_evidence_observability.py`
- `docs/agent_reviews/strategy_truth_phase2b_missing_evidence.md`

BLOCKED-EVENT MECHANISM:
- `classify_required_fields(...)` separates `missing_fields` from `invalid_fields` using field-specific validation modes: `positive`, `non_negative`, and `finite`.
- `emit_strategy_evidence_blocked(...)` logs `event=STRATEGY_EVIDENCE_BLOCKED` with `runtime_strategy_id`, sorted `missing_fields`, sorted `invalid_fields`, and a stable `reason`.
- `block_on_required_fields(...)` combines validation plus logging and returns `True` only when the generator should block.
- Logging is wrapped in `try/except`, so logging failures cannot change candidate generation.
- Empty field groups are rendered as `-`; no timestamps, object ids, or raw payload dumps are included.

COMPLETE GENERATOR-TO-EVENT MATRIX:
| generator | blocked reason | observed fields |
| --- | --- | --- |
| `opening_drive_v1` | `missing_required_session_timing` | `minutes_since_open` |
| `opening_drive_v1` | `missing_required_thesis_evidence` | `open_price`, `spot_ltp`, `vwap` |
| `opening_range_retest_v1` | `missing_required_session_timing` | `minutes_since_open` |
| `opening_range_retest_v1` | `missing_required_orb_evidence` | `orb_high`, `orb_low`, `spot_ltp`, `vwap` |
| `compression_breakout_v1` | `missing_required_thesis_evidence` | `atr_long`, `atr_short`, `range_width_pct`, `spot_ltp`, `vwap` |
| `trend_pullback_v1` | `missing_required_thesis_evidence` | `spot_ltp`, `vwap` |
| `trend_pullback_v1` | `missing_required_structure_anchor` | `nearest_resistance` or `nearest_support` |
| `vwap_reclaim_rejection_v1` | `missing_required_thesis_evidence` | `spot_ltp`, `vwap` |
| `failed_breakout_trap_v1` | `missing_required_thesis_evidence` | `spot_ltp` |
| `exhaustion_reversal_v1` | `missing_required_thesis_evidence` | `spot_ltp`, `vwap` |
| `mean_reversion_extension_v1` | `missing_required_thesis_evidence` | `spot_ltp`, `vwap` |
| `mean_reversion_extension_v1` | `missing_required_structure_anchor` | `day_high`, `nearest_resistance` or `day_low`, `nearest_support` |
| `event_volatility_expansion_v1` | `missing_required_thesis_evidence` | `atr_long`, `atr_short`, `spot_ltp`, `volume_z`, `vwap` |
| `late_day_momentum_v1` | `missing_required_session_timing` | `minutes_since_open`, `minutes_to_close` |
| `late_day_momentum_v1` | `missing_required_thesis_evidence` | `spot_ltp`, `vwap` |
| `option_pressure_confirmation_v1` | `missing_required_option_quote_evidence` | `ce_depth`, `ce_premium_change`, `ce_spread_pct`, `option_ce_ltp`, `option_ltp_age_sec`, `option_pe_ltp`, `pe_depth`, `pe_premium_change`, `pe_spread_pct` |
| `no_trade_chop_v1` | not applicable | safety suppression only |

SAMPLE DETERMINISTIC EVENTS:
```text
event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=compression_breakout_v1 missing_fields=atr_long,atr_short,range_width_pct invalid_fields=- reason=missing_required_thesis_evidence
event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=trend_pullback_v1 missing_fields=nearest_resistance invalid_fields=- reason=missing_required_structure_anchor
event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=opening_range_retest_v1 missing_fields=orb_high,orb_low invalid_fields=- reason=missing_required_orb_evidence
event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=option_pressure_confirmation_v1 missing_fields=option_ce_ltp invalid_fields=- reason=missing_required_option_quote_evidence
```

DETERMINISM PROOF:
- Field names are sorted before formatting.
- Repeated identical calls produce byte-identical blocked messages in `tests/test_strategy_missing_evidence_observability.py::test_repeated_identical_calls_produce_identical_blocked_evidence`.
- Invalid-value classification is stable for `None`, `NaN`, `inf`, and `-inf`.
- The event payload has only strategy id, field names, and a fixed reason string.

NO SYNTHETIC CANDIDATE PROOF:
- `tests/test_strategy_missing_evidence_observability.py::test_no_rejected_or_synthetic_candidate_is_created_for_observability` proves blocked generators still return no candidate.
- No new candidate class, candidate status, or rejected placeholder was introduced.

FAILURE CONTAINMENT PROOF:
- `tests/test_strategy_missing_evidence_observability.py::test_one_blocked_component_does_not_abort_other_generators` proves one blocked generator still emits its blocked event while another generator in the same pool run can return a real candidate.
- Candidate-pool behavior remains containment-based; blocked observability does not raise or abort the pool.

COMPLETE-CONTEXT FINGERPRINT:
Preserved exactly:

```text
opening_range_retest_v1
0.639513
BUY_CALL
VALIDATED_CANDIDATE

compression_breakout_v1
0.675169
BUY_CALL
VALIDATED_CANDIDATE

trend_pullback_v1
0.719646
BUY_CALL
VALIDATED_CANDIDATE

option_pressure_confirmation_v1
0.814750
BUY_CALL
VALIDATED_CANDIDATE
```

RAW SCORE PRESERVATION:
- `tests/test_strategy_missing_evidence_observability.py::test_complete_context_raw_scores_remain_exact` proves the complete-context raw scores remain unchanged.

OPTIONAL-MISSING BEHAVIOR PRESERVED:
- `tests/test_strategy_missing_evidence_observability.py::test_optional_missing_evidence_retains_zero_contribution_behavior` proves the Phase 2B zero-contribution policy remains intact for optional evidence.

PROFILE AND CONTEXT BOUNDARIES PRESERVED:
- `tests/test_strategy_missing_evidence_observability.py::test_phase1c_profile_blocking_remains_unchanged` proves Phase 1C fail-closed profile behavior is unchanged.
- `tests/test_strategy_missing_evidence_observability.py::test_phase2a_context_truth_remains_unchanged` proves Phase 2A runtime truth mapping is unchanged.

PROOF THAT OTHER GENERATORS CONTINUE:
- The observability helper returns only a boolean and logs side effects.
- Generators still return `()` on blocked evidence and the pool keeps iterating.
- Focused containment coverage passed without any candidate-pool order changes.

PROOF THAT NO SYNTHETIC CANDIDATE IS CREATED:
- Blocked generators emit only a log event and still return an empty tuple.
- No code path appends a rejected candidate or metadata-only pseudo-candidate.

FOCUSED TEST COMMAND:
```bash
python -m pytest -q \
  tests/test_strategy_missing_evidence_observability.py \
  tests/test_strategy_missing_evidence_policy.py \
  tests/test_strategy_context_truth.py \
  tests/test_strategy_profile_fail_closed.py \
  tests/test_candidate_pool.py \
  tests/test_candidate_pool_orchestrator.py \
  tests/test_opening_movement_strategies.py \
  tests/test_compression_trend_movement_strategies.py \
  tests/test_vwap_trap_movement_strategies.py \
  tests/test_exhaustion_mean_reversion_strategies.py \
  tests/test_event_late_day_movement_strategies.py \
  tests/test_option_confirmation.py \
  tests/test_no_trade_engine.py
```

FOCUSED TEST RESULT:
`132 passed, 1 warning in 8.33s`

STATIC CHECKS:
```bash
python -m py_compile \
  strategies/movement/_utils.py \
  strategies/movement/*.py \
  tests/test_strategy_missing_evidence_observability.py

ruff check \
  strategies/movement \
  tests/test_strategy_missing_evidence_observability.py

git diff --check
```

STATIC CHECK RESULT:
All passed.

FULL-SUITE RESULT:
`1 failed, 5710 passed, 1 deselected, 935 warnings in 306.29s (0:05:06)`

FIRST FAILURE:
`tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`

FIRST FAILURE DETAIL:
The failure remained the established credential-path baseline:

```text
RuntimeError:[AUTH] missing_kite_access_token
Missing token at /Users/madhuram/tradebot-strategy-truth-foundation/.runtime/kite_access_token
Run scripts/kite_autologin_localhost.py to refresh token.
```

BEHAVIOR PRESERVED:
- Complete-context candidate count, order, ids, directions, statuses, and scores stayed exact.
- No candidate logic, formula, threshold, or setup definition changed.
- Optional missing evidence still contributes zero, not positive evidence.
- `NO_TRADE_CHOP` remains `safety_suppression`.
- No synthetic candidate, no network call, no broker/order/execution path, and no persistent thread activity were added.

BEHAVIOR CHANGED:
- Required-evidence blockers that already returned no candidate now emit a deterministic observable blocked event.

REMAINING RISKS:
- Runtime candidate counts can still drop where truthful Phase 2A sources remain missing; that is intentional and unchanged.
- This pass makes blockers observable; it does not yet resolve candidate-versus-Phase-2 ownership boundaries.

ROLLBACK:
- Revert only the observability corrective commit. No config or data migration is required.

EXPLICIT NON-CLAIMS:
- No strategy threshold tuning.
- No setup-definition rewrite.
- No profile-resolution change.
- No ranking, no-trade, feed, broker, risk, order, execution, dashboard, backtesting, or WFA change.
- No claim of trading edge or profitability.
