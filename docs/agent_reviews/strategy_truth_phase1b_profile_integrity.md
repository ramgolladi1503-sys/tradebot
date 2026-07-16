# Strategy Truth Phase 1B Profile Integrity

## Commits
- Starting commit: `9ace90c0b49d790f0e8926a75ecd9492ae6d3b26`
- Phase 0 commit: `cf2d74bc7a2938a08bc651e25b5334481479d68c`
- Phase 1A commit: `9ace90c0b49d790f0e8926a75ecd9492ae6d3b26`

## Files changed
- `config/strategy_inventory.yml`
- `core/strategy_parameter_profiles.py`
- `strategies/strategy_registry.py`
- `tests/test_strategy_parameter_profiles.py`
- `tests/test_strategy_profile_integrity.py`
- `docs/agent_reviews/strategy_truth_phase1b_profile_integrity.md`

## Architecture assessment
- Assessment: `NECESSARY`
- Reason: Phase 1B needed explicit alias lineage, deterministic hash inputs, exact/canonical profile metadata, and mechanical comparison between stored values and embedded module defaults.
- Not added: no new service, registry, runtime layer, daemon, database, or config framework.

## Scope assessment
- Scope: `IN_SCOPE`
- Preserved:
  - `NO_TRADE_CHOP` stays `role=safety_suppression`
  - every inventory row stays `execution_eligible=false`
  - quarantine remains metadata-only
  - no strategy promotion
  - no feed, broker, risk, order, execution, credential, dashboard, backtesting, or WFA code changed
- Non-claims:
  - no pattern conformance claim
  - no predictive edge claim
  - no after-cost profitability claim
  - no paper/live/production readiness claim

## Source-parsing call-site analysis
- Parser entrypoint: `strategies/strategy_registry.py::_extract_embedded_profile_defaults()`
- Internal call sites:
  - `_profile_integrity_row()`
  - `build_strategy_profile_integrity_rows()`
  - `validate_strategy_registry_integrity()`
- External repo call sites:
  - tests only: `tests/test_strategy_profile_integrity.py`, `tests/test_strategy_registry_integrity.py`
  - no non-test caller invokes `build_strategy_profile_integrity_rows()` or `validate_strategy_registry_integrity()`
- Non-callers confirmed by search:
  - candidate generation paths do not call the parser
  - ordinary `load_strategy_registry()` does not call the parser
  - application startup and recurring live-cycle code do not call the parser
- Explicit proof added:
  - `test_source_parsing_is_explicit_validation_only`
  - `test_profile_integrity_builder_has_no_network_or_thread_side_effects`

SOURCE PARSING STATUS: `OFFLINE_ONLY`

## Hash input contract
`build_profile_parameter_hash()` hashes only:
- canonical resolved profile ID
- profile version
- normalized effective parameter dictionary
- stable key ordering
- deterministic JSON serialization with `sort_keys=True` and fixed separators

It does not hash:
- requested alias name
- timestamps
- object ids
- process ids
- memory addresses
- runtime-only state

Alias request names therefore do not create false parameter divergence.

## Drift behavior
- Exact-profile drift now fails closed:
  - classification becomes `PROFILE_VALUE_DRIFT`
  - `get_default_profile()` returns `None`
  - resolution source does not claim `EXACT_PROFILE`
  - integrity evidence exposes the drift through `mismatch_classification`
  - generator code falls back to its embedded literal defaults instead of silently activating stored drift
- Proof:
  - `test_exact_profile_drift_fails_closed_to_preserve_embedded_defaults`
  - `test_validation_rejects_profile_value_drift_without_silent_activation`
  - `test_profile_value_drift_preserves_prior_generator_behavior`

## Alias integrity
- Canonical aliases:
  - `opening_range_retest_v1 -> opening_range_breakout_v1`
  - `option_pressure_confirmation_v1 -> option_pressure_v1`
- Proof:
  - all 12 registered profile identities resolve
  - exact profiles report `EXACT_PROFILE`
  - both compatibility aliases report `COMPATIBILITY_ALIAS`
  - cycles fail
  - target-is-alias ambiguity fails
  - duplicate aliases fail
  - missing targets fail
  - unknown profile IDs do not claim exact resolution
  - no hidden fallback is reported as exact

## Cross-process hash result
Two fresh subprocesses returned the same payload:

```json
{"alias_hash":"80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064","canonical_hash":"80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064","rebuilt_hash":"80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064"}
```

Proof:
- repeated calls return the same hash
- subprocesses return the same hash
- dict insertion order does not affect the hash
- changing effective parameters changes the hash
- alias and canonical requests share canonical lineage

## Full 12-row profile matrix

| inventory canonical ID | public compatibility ID | runtime strategy ID | module STRATEGY_ID | requested profile ID | canonical profile ID | stored profile ID | profile version | stored parameter keys | embedded default keys | effective parameter values | embedded default values | resolution source | compatibility alias | parameter hash | mismatch classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `MEAN_REVERSION_EXTENSION` | `MEAN_REVERSION_EXTENSION` | `mean_reversion_extension_v1` | `mean_reversion_extension_v1` | `mean_reversion_extension_v1` | `mean_reversion_extension_v1` | `mean_reversion_extension_v1` | `v1` | `('MAX_EXTENSION_FROM_VWAP_PCT', 'MAX_TREND_CONTINUATION_SCORE', 'MIN_EXTENSION_FROM_VWAP_PCT', 'MIN_RANGE_OR_CHOP_SCORE')` | `('MAX_EXTENSION_FROM_VWAP_PCT', 'MAX_TREND_CONTINUATION_SCORE', 'MIN_EXTENSION_FROM_VWAP_PCT', 'MIN_RANGE_OR_CHOP_SCORE')` | `(('MAX_EXTENSION_FROM_VWAP_PCT', 0.014), ('MAX_TREND_CONTINUATION_SCORE', 0.55), ('MIN_EXTENSION_FROM_VWAP_PCT', 0.0035), ('MIN_RANGE_OR_CHOP_SCORE', 0.45))` | `(('MAX_EXTENSION_FROM_VWAP_PCT', 0.014), ('MAX_TREND_CONTINUATION_SCORE', 0.55), ('MIN_EXTENSION_FROM_VWAP_PCT', 0.0035), ('MIN_RANGE_OR_CHOP_SCORE', 0.45))` | `EXACT_PROFILE` |  | `204b4d83bd5fcc89a88697002d007762f2d045942f874ac6c1a047f85d96dda6` | `EXACT_PROFILE` |
| `COMPRESSION_BREAKOUT` | `COMPRESSION_BREAKOUT` | `compression_breakout_v1` | `compression_breakout_v1` | `compression_breakout_v1` | `compression_breakout_v1` | `compression_breakout_v1` | `v1` | `('MAX_ATR_RATIO', 'MAX_RANGE_WIDTH_PCT', 'MIN_BREAKOUT_DISTANCE_PCT', 'MIN_COMPRESSION_SCORE', 'MIN_VWAP_ALIGNMENT_PCT')` | `('MAX_ATR_RATIO', 'MAX_RANGE_WIDTH_PCT', 'MIN_BREAKOUT_DISTANCE_PCT', 'MIN_COMPRESSION_SCORE', 'MIN_VWAP_ALIGNMENT_PCT')` | `(('MAX_ATR_RATIO', 0.75), ('MAX_RANGE_WIDTH_PCT', 0.35), ('MIN_BREAKOUT_DISTANCE_PCT', 0.0008), ('MIN_COMPRESSION_SCORE', 0.5), ('MIN_VWAP_ALIGNMENT_PCT', 0.0004))` | `(('MAX_ATR_RATIO', 0.75), ('MAX_RANGE_WIDTH_PCT', 0.35), ('MIN_BREAKOUT_DISTANCE_PCT', 0.0008), ('MIN_COMPRESSION_SCORE', 0.5), ('MIN_VWAP_ALIGNMENT_PCT', 0.0004))` | `EXACT_PROFILE` |  | `514c4d0b5c1d95b138afa051a88dbae8a6b1e1fa090e1b6f608d8d412a6d75b5` | `EXACT_PROFILE` |
| `TREND_PULLBACK` | `TREND_PULLBACK` | `trend_pullback_v1` | `trend_pullback_v1` | `trend_pullback_v1` | `trend_pullback_v1` | `trend_pullback_v1` | `v1` | `('MAX_PULLBACK_DISTANCE_PCT', 'MIN_STRUCTURE_RESUME_PCT', 'MIN_TREND_SCORE')` | `('MAX_PULLBACK_DISTANCE_PCT', 'MIN_STRUCTURE_RESUME_PCT', 'MIN_TREND_SCORE')` | `(('MAX_PULLBACK_DISTANCE_PCT', 0.0035), ('MIN_STRUCTURE_RESUME_PCT', 0.0004), ('MIN_TREND_SCORE', 0.45))` | `(('MAX_PULLBACK_DISTANCE_PCT', 0.0035), ('MIN_STRUCTURE_RESUME_PCT', 0.0004), ('MIN_TREND_SCORE', 0.45))` | `EXACT_PROFILE` |  | `04513721c5b9a7e80b02c49e658f4dabfb1d9e1b379abbf42e24157c364ec2eb` | `EXACT_PROFILE` |
| `VWAP_RECLAIM_REJECTION` | `VWAP_RECLAIM` | `vwap_reclaim_rejection_v1` | `vwap_reclaim_rejection_v1` | `vwap_reclaim_rejection_v1` | `vwap_reclaim_rejection_v1` | `vwap_reclaim_rejection_v1` | `v1` | `('MAX_CHOP_SCORE', 'MAX_VWAP_ENTRY_DISTANCE_PCT', 'MIN_VWAP_DISTANCE_PCT')` | `('MAX_CHOP_SCORE', 'MAX_VWAP_ENTRY_DISTANCE_PCT', 'MIN_VWAP_DISTANCE_PCT')` | `(('MAX_CHOP_SCORE', 0.55), ('MAX_VWAP_ENTRY_DISTANCE_PCT', 0.0035), ('MIN_VWAP_DISTANCE_PCT', 0.00035))` | `(('MAX_CHOP_SCORE', 0.55), ('MAX_VWAP_ENTRY_DISTANCE_PCT', 0.0035), ('MIN_VWAP_DISTANCE_PCT', 0.00035))` | `EXACT_PROFILE` |  | `ec28041cd6920b50018ef09fb4cf605aecb054b0205ec2852feebe801d98fc9b` | `EXACT_PROFILE` |
| `OPENING_DRIVE` | `OPENING_DRIVE` | `opening_drive_v1` | `opening_drive_v1` | `opening_drive_v1` | `opening_drive_v1` | `opening_drive_v1` | `v1` | `('MAX_OPENING_DRIVE_MINUTES', 'MIN_OPEN_MOVE_PCT', 'MIN_VWAP_ALIGNMENT_PCT')` | `('MAX_OPENING_DRIVE_MINUTES', 'MIN_OPEN_MOVE_PCT', 'MIN_VWAP_ALIGNMENT_PCT')` | `(('MAX_OPENING_DRIVE_MINUTES', 20), ('MIN_OPEN_MOVE_PCT', 0.0015), ('MIN_VWAP_ALIGNMENT_PCT', 0.0005))` | `(('MAX_OPENING_DRIVE_MINUTES', 20), ('MIN_OPEN_MOVE_PCT', 0.0015), ('MIN_VWAP_ALIGNMENT_PCT', 0.0005))` | `EXACT_PROFILE` |  | `063e08c3ca9b8fcb6e53b8c86d57e8edb4e7e177a59c33286dd864056be88920` | `EXACT_PROFILE` |
| `FAILED_BREAKOUT_TRAP` | `FAILED_BREAKOUT_TRAP` | `failed_breakout_trap_v1` | `failed_breakout_trap_v1` | `failed_breakout_trap_v1` | `failed_breakout_trap_v1` | `failed_breakout_trap_v1` | `v1` | `('MAX_REENTRY_DISTANCE_PCT', 'MIN_FAILED_BREAK_DISTANCE_PCT', 'MIN_TRAP_EVIDENCE_SCORE')` | `('MAX_REENTRY_DISTANCE_PCT', 'MIN_FAILED_BREAK_DISTANCE_PCT', 'MIN_TRAP_EVIDENCE_SCORE')` | `(('MAX_REENTRY_DISTANCE_PCT', 0.0035), ('MIN_FAILED_BREAK_DISTANCE_PCT', 0.0006), ('MIN_TRAP_EVIDENCE_SCORE', 0.45))` | `(('MAX_REENTRY_DISTANCE_PCT', 0.0035), ('MIN_FAILED_BREAK_DISTANCE_PCT', 0.0006), ('MIN_TRAP_EVIDENCE_SCORE', 0.45))` | `EXACT_PROFILE` |  | `8932b47229a435ce22696c705617e87b999dc7c4372be6da0d9dca9ba38ba1fa` | `EXACT_PROFILE` |
| `EXHAUSTION_REVERSAL` | `EXHAUSTION_REVERSAL` | `exhaustion_reversal_v1` | `exhaustion_reversal_v1` | `exhaustion_reversal_v1` | `exhaustion_reversal_v1` | `exhaustion_reversal_v1` | `v1` | `('MAX_CONTINUATION_PRESSURE_SCORE', 'MAX_ENTRY_STRETCH_PCT', 'MIN_EXHAUSTION_SCORE', 'MIN_STRETCH_FROM_VWAP_PCT')` | `('MAX_CONTINUATION_PRESSURE_SCORE', 'MAX_ENTRY_STRETCH_PCT', 'MIN_EXHAUSTION_SCORE', 'MIN_STRETCH_FROM_VWAP_PCT')` | `(('MAX_CONTINUATION_PRESSURE_SCORE', 0.55), ('MAX_ENTRY_STRETCH_PCT', 0.018), ('MIN_EXHAUSTION_SCORE', 0.5), ('MIN_STRETCH_FROM_VWAP_PCT', 0.005))` | `(('MAX_CONTINUATION_PRESSURE_SCORE', 0.55), ('MAX_ENTRY_STRETCH_PCT', 0.018), ('MIN_EXHAUSTION_SCORE', 0.5), ('MIN_STRETCH_FROM_VWAP_PCT', 0.005))` | `EXACT_PROFILE` |  | `3dc3b99b3bed11224f608297c6561063dc7cac9748fc2e2ada5d00c5200cd1a9` | `EXACT_PROFILE` |
| `DIRECTIONAL_VOLATILITY_EXPANSION` | `EVENT_VOLATILITY_EXPANSION` | `event_volatility_expansion_v1` | `event_volatility_expansion_v1` | `event_volatility_expansion_v1` | `event_volatility_expansion_v1` | `event_volatility_expansion_v1` | `v1` | `('MAX_CHASE_DISTANCE_PCT', 'MIN_ATR_EXPANSION_RATIO', 'MIN_IMPULSE_FROM_VWAP_PCT', 'MIN_VOLUME_Z', 'MIN_VOL_EXPANSION_SCORE')` | `('MAX_CHASE_DISTANCE_PCT', 'MIN_ATR_EXPANSION_RATIO', 'MIN_IMPULSE_FROM_VWAP_PCT', 'MIN_VOLUME_Z', 'MIN_VOL_EXPANSION_SCORE')` | `(('MAX_CHASE_DISTANCE_PCT', 0.014), ('MIN_ATR_EXPANSION_RATIO', 1.15), ('MIN_IMPULSE_FROM_VWAP_PCT', 0.0025), ('MIN_VOLUME_Z', 1.2), ('MIN_VOL_EXPANSION_SCORE', 0.4))` | `(('MAX_CHASE_DISTANCE_PCT', 0.014), ('MIN_ATR_EXPANSION_RATIO', 1.15), ('MIN_IMPULSE_FROM_VWAP_PCT', 0.0025), ('MIN_VOLUME_Z', 1.2), ('MIN_VOL_EXPANSION_SCORE', 0.4))` | `EXACT_PROFILE` |  | `ae3b107d78a9479c34d116e542038dba61d1922987e39b1a5f41b83f72038739` | `EXACT_PROFILE` |
| `LATE_DAY_MOMENTUM` | `LATE_DAY_MOMENTUM` | `late_day_momentum_v1` | `late_day_momentum_v1` | `late_day_momentum_v1` | `late_day_momentum_v1` | `late_day_momentum_v1` | `v1` | `('MAX_CHASE_DISTANCE_PCT', 'MAX_CHOP_SCORE', 'MIN_DIRECTIONAL_SCORE', 'MIN_MINUTES_SINCE_OPEN', 'MIN_MINUTES_TO_CLOSE', 'MIN_VWAP_DISTANCE_PCT')` | `('MAX_CHASE_DISTANCE_PCT', 'MAX_CHOP_SCORE', 'MIN_DIRECTIONAL_SCORE', 'MIN_MINUTES_SINCE_OPEN', 'MIN_MINUTES_TO_CLOSE', 'MIN_VWAP_DISTANCE_PCT')` | `(('MAX_CHASE_DISTANCE_PCT', 0.012), ('MAX_CHOP_SCORE', 0.5), ('MIN_DIRECTIONAL_SCORE', 0.45), ('MIN_MINUTES_SINCE_OPEN', 240), ('MIN_MINUTES_TO_CLOSE', 20), ('MIN_VWAP_DISTANCE_PCT', 0.002))` | `(('MAX_CHASE_DISTANCE_PCT', 0.012), ('MAX_CHOP_SCORE', 0.5), ('MIN_DIRECTIONAL_SCORE', 0.45), ('MIN_MINUTES_SINCE_OPEN', 240), ('MIN_MINUTES_TO_CLOSE', 20), ('MIN_VWAP_DISTANCE_PCT', 0.002))` | `EXACT_PROFILE` |  | `0ac945fc503ae580a624b3c0b7fc349aa0dbeb333a8a94af3c925a3285d3c5ea` | `EXACT_PROFILE` |
| `OPTION_QUOTE_CONFIRMATION` | `OPTION_PRESSURE` | `option_pressure_confirmation_v1` | `option_pressure_confirmation_v1` | `option_pressure_confirmation_v1` | `option_pressure_v1` | `option_pressure_v1` | `v1` | `('MIN_PRESSURE_SCORE',)` | `('MIN_PRESSURE_SCORE',)` | `(('MIN_PRESSURE_SCORE', 0.45),)` | `(('MIN_PRESSURE_SCORE', 0.45),)` | `COMPATIBILITY_ALIAS` | `option_pressure_confirmation_v1->option_pressure_v1` | `adadeff1df6db8a4b5fa1d93a197fc4b2bac592a870bc6857ba0046f30a68dac` | `COMPATIBILITY_ALIAS` |
| `OPENING_RANGE_RETEST` | `OPENING_RANGE_BREAKOUT` | `opening_range_retest_v1` | `opening_range_retest_v1` | `opening_range_retest_v1` | `opening_range_breakout_v1` | `opening_range_breakout_v1` | `v1` | `('MAX_RETEST_DISTANCE_PCT', 'MAX_RETEST_MINUTES', 'MIN_BREAKOUT_DISTANCE_PCT', 'MIN_RETEST_MINUTES')` | `('MAX_RETEST_DISTANCE_PCT', 'MAX_RETEST_MINUTES', 'MIN_BREAKOUT_DISTANCE_PCT', 'MIN_RETEST_MINUTES')` | `(('MAX_RETEST_DISTANCE_PCT', 0.0018), ('MAX_RETEST_MINUTES', 90), ('MIN_BREAKOUT_DISTANCE_PCT', 0.0008), ('MIN_RETEST_MINUTES', 15))` | `(('MAX_RETEST_DISTANCE_PCT', 0.0018), ('MAX_RETEST_MINUTES', 90), ('MIN_BREAKOUT_DISTANCE_PCT', 0.0008), ('MIN_RETEST_MINUTES', 15))` | `COMPATIBILITY_ALIAS` | `opening_range_retest_v1->opening_range_breakout_v1` | `80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064` | `COMPATIBILITY_ALIAS` |
| `NO_TRADE_CHOP` | `NO_TRADE_CHOP` | `no_trade_engine_v1` | `no_trade_engine_v1` | `no_trade_engine_v1` | `no_trade_engine_v1` | `no_trade_engine_v1` | `v1` | `()` | `()` | `()` | `()` | `EXACT_PROFILE` |  | `265fc3afdcc93c3fd90e26286d50b031dbc0fbca238fac9b151e20efb5c88ea8` | `EXACT_PROFILE` |

## Fixed candidate fingerprint
Phase 1A fingerprint preserved exactly:

```text
opening_range_retest_v1           0.639513  BUY_CALL  VALIDATED_CANDIDATE
compression_breakout_v1           0.675169  BUY_CALL  VALIDATED_CANDIDATE
trend_pullback_v1                 0.719646  BUY_CALL  VALIDATED_CANDIDATE
option_pressure_confirmation_v1   0.814750  BUY_CALL  VALIDATED_CANDIDATE
```

Proof:
- candidate generator order unchanged
- candidate count unchanged
- candidate IDs unchanged
- directions unchanged
- statuses unchanged
- raw scores unchanged

## Commands and results

Focused verification commands:

```bash
python -m pytest -q \
  tests/test_strategy_parameter_profiles.py \
  tests/test_strategy_profile_integrity.py \
  tests/test_strategy_inventory.py \
  tests/test_strategy_registry.py \
  tests/test_strategy_registry_integrity.py \
  tests/test_candidate_pool.py \
  tests/test_candidate_pool_quality.py \
  tests/test_candidate_pool_orchestrator.py \
  tests/test_candidate_pool_contract_snapshots.py \
  tests/test_opening_movement_strategies.py \
  tests/test_compression_trend_movement_strategies.py \
  tests/test_vwap_trap_movement_strategies.py \
  tests/test_exhaustion_mean_reversion_strategies.py \
  tests/test_event_late_day_movement_strategies.py \
  tests/test_option_confirmation.py \
  tests/test_no_trade_engine.py \
  tests/test_strategy_generators_lineage.py \
  tests/test_movement_registry.py
```

Focused result:
- `140 passed, 1 warning`

Static checks:

```bash
python -m json.tool config/strategy_inventory.yml
python -m py_compile core/strategy_parameter_profiles.py strategies/strategy_registry.py tests/test_strategy_profile_integrity.py
ruff check core/strategy_parameter_profiles.py strategies/strategy_registry.py tests/test_strategy_profile_integrity.py
git diff --check
```

Static result:
- `json.tool`: pass
- `py_compile`: pass
- `ruff check`: pass
- `git diff --check`: pass

Full suite command:

```bash
python -m pytest -q
```

Full suite result:
- `5651 passed, 1 failed, 1 deselected, 935 warnings`

First failure:
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- observed error:
  - expected `forced_cycle_error`
  - got `[AUTH] missing_kite_access_token`
- touched files do not overlap the failing orchestrator/auth path

## Remaining risks
- The source parser intentionally supports only literal `params.get(..., <literal>)` defaults. If modules move to non-literal default expressions, the explicit validation path will fail closed.
- Full-suite green is blocked by the unrelated orchestrator/auth test failure in the current environment.

## Explicit non-claims
- This phase does not prove executable edge.
- This phase does not prove profitable edge.
- This phase does not prove option-translation correctness.
- This phase does not prove paper readiness.
- This phase does not prove live readiness.
- This phase does not implement Phase 1C fail-closed removal of remaining fallback behavior.
