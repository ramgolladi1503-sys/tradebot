# Strategy Truth Phase 1C Fail-Closed Profiles

## Commits
- Starting commit: `2a247ec6d92f60aa101d462eb6f3013d1aec4d54`
- Phase 0 commit: `cf2d74bc7a2938a08bc651e25b5334481479d68c`
- Phase 1A commit: `9ace90c0b49d790f0e8926a75ecd9492ae6d3b26`

## Files changed
- `core/strategy_parameter_profiles.py`
- `strategies/strategy_registry.py`
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
- `tests/test_strategy_profile_integrity.py`
- `tests/test_strategy_profile_fail_closed.py`
- `docs/agent_reviews/strategy_truth_phase1c_fail_closed_profiles.md`

## Architecture assessment
- Assessment: `NONE`
- Runtime shape:
  - no new service
  - no new registry
  - no new config layer
  - no new startup validation path
- Mechanism:
  - added `resolve_required_profile_parameters()` as the explicit runtime boundary
  - generators now stop emitting candidates when profile resolution is invalid or incomplete
  - offline source parsing remains in `strategies.strategy_registry` only
  - module-level `EMBEDDED_PROFILE_DEFAULTS` constants preserve Phase 1B integrity evidence without reintroducing runtime fallback

## Scope assessment
- Scope: `IN_SCOPE`
- Preserved:
  - `NO_TRADE_CHOP` remains `role=safety_suppression`
  - every inventory row remains `execution_eligible=false`
  - quarantine remains metadata-only
  - no strategy is promoted
  - no feed, broker, risk, order, execution, credential, dashboard, backtesting, or WFA behavior changed
  - profile validation opens no network connections
  - profile validation starts no persistent threads
- Non-claims:
  - no executable edge claim
  - no profitability claim
  - no paper readiness claim
  - no live readiness claim

## Source-parsing call-site analysis
- Parser entrypoint: `strategies.strategy_registry._extract_embedded_profile_defaults()`
- Internal call sites:
  - `_profile_integrity_row()`
  - `build_strategy_profile_integrity_rows()`
  - `validate_strategy_registry_integrity()`
- External call sites:
  - tests and offline validation only
- Explicit non-callers confirmed:
  - `core.candidate_pool_orchestrator.build_candidate_pool_report()`
  - `core.candidate_pool_orchestrator.get_default_candidate_generators()`
  - movement generator runtime execution
  - ordinary registry loading
  - recurring live-cycle candidate generation
- Parser behavior:
  - prefers module-level `EMBEDDED_PROFILE_DEFAULTS` literal dicts
  - falls back to legacy `params.get(..., literal)` AST extraction when present

SOURCE PARSING STATUS: `OFFLINE_ONLY`

## Runtime fail-closed behavior
- Valid runtime resolution sources:
  - `EXACT_PROFILE`
  - `COMPATIBILITY_ALIAS`
- Blocked runtime classifications:
  - `MISSING_PROFILE`
  - `PROFILE_VALUE_DRIFT`
  - `INCOMPLETE_PROFILE`
  - any non-exact/non-alias result
- Observable warning format:
  - `event=PROFILE_RESOLUTION_BLOCKED`
  - `runtime_strategy_id=<runtime strategy id>`
  - `requested_profile_id=<requested profile id>`
  - `resolution_classification=<classification>`
  - `blocked_reason=<reason>`

## Full 12-row profile matrix

| inventory canonical ID | runtime strategy ID | resolved/store profile ID | resolution source | effective values | embedded values | parameter hash |
| --- | --- | --- | --- | --- | --- | --- |
| `MEAN_REVERSION_EXTENSION` | `mean_reversion_extension_v1` | `mean_reversion_extension_v1` | `EXACT_PROFILE` | `(('MAX_EXTENSION_FROM_VWAP_PCT', 0.014), ('MAX_TREND_CONTINUATION_SCORE', 0.55), ('MIN_EXTENSION_FROM_VWAP_PCT', 0.0035), ('MIN_RANGE_OR_CHOP_SCORE', 0.45))` | same | `204b4d83bd5fcc89a88697002d007762f2d045942f874ac6c1a047f85d96dda6` |
| `COMPRESSION_BREAKOUT` | `compression_breakout_v1` | `compression_breakout_v1` | `EXACT_PROFILE` | `(('MAX_ATR_RATIO', 0.75), ('MAX_RANGE_WIDTH_PCT', 0.35), ('MIN_BREAKOUT_DISTANCE_PCT', 0.0008), ('MIN_COMPRESSION_SCORE', 0.5), ('MIN_VWAP_ALIGNMENT_PCT', 0.0004))` | same | `514c4d0b5c1d95b138afa051a88dbae8a6b1e1fa090e1b6f608d8d412a6d75b5` |
| `TREND_PULLBACK` | `trend_pullback_v1` | `trend_pullback_v1` | `EXACT_PROFILE` | `(('MAX_PULLBACK_DISTANCE_PCT', 0.0035), ('MIN_STRUCTURE_RESUME_PCT', 0.0004), ('MIN_TREND_SCORE', 0.45))` | same | `04513721c5b9a7e80b02c49e658f4dabfb1d9e1b379abbf42e24157c364ec2eb` |
| `VWAP_RECLAIM_REJECTION` | `vwap_reclaim_rejection_v1` | `vwap_reclaim_rejection_v1` | `EXACT_PROFILE` | `(('MAX_CHOP_SCORE', 0.55), ('MAX_VWAP_ENTRY_DISTANCE_PCT', 0.0035), ('MIN_VWAP_DISTANCE_PCT', 0.00035))` | same | `ec28041cd6920b50018ef09fb4cf605aecb054b0205ec2852feebe801d98fc9b` |
| `OPENING_DRIVE` | `opening_drive_v1` | `opening_drive_v1` | `EXACT_PROFILE` | `(('MAX_OPENING_DRIVE_MINUTES', 20), ('MIN_OPEN_MOVE_PCT', 0.0015), ('MIN_VWAP_ALIGNMENT_PCT', 0.0005))` | same | `063e08c3ca9b8fcb6e53b8c86d57e8edb4e7e177a59c33286dd864056be88920` |
| `FAILED_BREAKOUT_TRAP` | `failed_breakout_trap_v1` | `failed_breakout_trap_v1` | `EXACT_PROFILE` | `(('MAX_REENTRY_DISTANCE_PCT', 0.0035), ('MIN_FAILED_BREAK_DISTANCE_PCT', 0.0006), ('MIN_TRAP_EVIDENCE_SCORE', 0.45))` | same | `8932b47229a435ce22696c705617e87b999dc7c4372be6da0d9dca9ba38ba1fa` |
| `EXHAUSTION_REVERSAL` | `exhaustion_reversal_v1` | `exhaustion_reversal_v1` | `EXACT_PROFILE` | `(('MAX_CONTINUATION_PRESSURE_SCORE', 0.55), ('MAX_ENTRY_STRETCH_PCT', 0.018), ('MIN_EXHAUSTION_SCORE', 0.5), ('MIN_STRETCH_FROM_VWAP_PCT', 0.005))` | same | `3dc3b99b3bed11224f608297c6561063dc7cac9748fc2e2ada5d00c5200cd1a9` |
| `DIRECTIONAL_VOLATILITY_EXPANSION` | `event_volatility_expansion_v1` | `event_volatility_expansion_v1` | `EXACT_PROFILE` | `(('MAX_CHASE_DISTANCE_PCT', 0.014), ('MIN_ATR_EXPANSION_RATIO', 1.15), ('MIN_IMPULSE_FROM_VWAP_PCT', 0.0025), ('MIN_VOLUME_Z', 1.2), ('MIN_VOL_EXPANSION_SCORE', 0.4))` | same | `ae3b107d78a9479c34d116e542038dba61d1922987e39b1a5f41b83f72038739` |
| `LATE_DAY_MOMENTUM` | `late_day_momentum_v1` | `late_day_momentum_v1` | `EXACT_PROFILE` | `(('MAX_CHASE_DISTANCE_PCT', 0.012), ('MAX_CHOP_SCORE', 0.5), ('MIN_DIRECTIONAL_SCORE', 0.45), ('MIN_MINUTES_SINCE_OPEN', 240), ('MIN_MINUTES_TO_CLOSE', 20), ('MIN_VWAP_DISTANCE_PCT', 0.002))` | same | `0ac945fc503ae580a624b3c0b7fc349aa0dbeb333a8a94af3c925a3285d3c5ea` |
| `OPTION_QUOTE_CONFIRMATION` | `option_pressure_confirmation_v1` | `option_pressure_v1` | `COMPATIBILITY_ALIAS` | `(('MIN_PRESSURE_SCORE', 0.45),)` | same | `adadeff1df6db8a4b5fa1d93a197fc4b2bac592a870bc6857ba0046f30a68dac` |
| `OPENING_RANGE_RETEST` | `opening_range_retest_v1` | `opening_range_breakout_v1` | `COMPATIBILITY_ALIAS` | `(('MAX_RETEST_DISTANCE_PCT', 0.0018), ('MAX_RETEST_MINUTES', 90), ('MIN_BREAKOUT_DISTANCE_PCT', 0.0008), ('MIN_RETEST_MINUTES', 15))` | same | `80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064` |
| `NO_TRADE_CHOP` | `no_trade_engine_v1` | `no_trade_engine_v1` | `EXACT_PROFILE` | `()` | `()` | `265fc3afdcc93c3fd90e26286d50b031dbc0fbca238fac9b151e20efb5c88ea8` |

## Drift and fail-closed proofs
- `test_profile_value_drift_blocks_only_affected_generator_and_logs_warning`
  - `opening_range_retest_v1` drifted embedded defaults
  - generator emitted no candidate
  - remaining default-generator fingerprint stayed:
    - `compression_breakout_v1 0.675169 BUY_CALL VALIDATED_CANDIDATE`
    - `trend_pullback_v1 0.719646 BUY_CALL VALIDATED_CANDIDATE`
    - `option_pressure_confirmation_v1 0.814750 BUY_CALL VALIDATED_CANDIDATE`
  - warning evidence included:
    - `resolution_classification=PROFILE_VALUE_DRIFT`
    - `blocked_reason=profile_resolution_profile_value_drift`
- `test_missing_alias_target_blocks_only_option_pressure_generator`
  - alias target removal classified as `MISSING_PROFILE`
  - only `option_pressure_confirmation_v1` stopped emitting
  - no hidden fallback claimed `EXACT_PROFILE`
- `test_incomplete_profile_blocks_generator_without_embedded_default_fallback`
  - exact profile missing required keys classified as `INCOMPLETE_PROFILE`
  - `opening_drive_v1` emitted no candidate
  - warning evidence exposed the missing keys
- Legacy drift expectation updated:
  - `test_profile_value_drift_blocks_generator_without_silent_runtime_fallback`

## Alias integrity
- Canonical alias proofs remain covered by:
  - `test_compatibility_aliases_resolve_to_one_canonical_profile`
  - `test_alias_cycles_and_ambiguous_aliases_are_rejected`
  - `test_duplicate_and_missing_alias_targets_are_rejected`
  - `test_unknown_profile_ids_are_explicitly_classified`
  - `test_resolution_source_is_never_omitted_for_inventory_rows`
- Canonical alias rows:
  - `opening_range_retest_v1 -> opening_range_breakout_v1`
  - `option_pressure_confirmation_v1 -> option_pressure_v1`

## Hash input contract
`build_profile_parameter_hash()` hashes only:
- canonical resolved profile ID
- profile version
- normalized effective parameter dictionary
- deterministic key ordering
- deterministic JSON serialization with `sort_keys=True` and fixed separators

It does not hash:
- requested alias names
- insertion order
- process-local identity
- timestamps
- runtime state

Cross-process proof:

```json
{"alias_hash":"80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064","canonical_hash":"80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064","rebuilt_hash":"80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064"}
```

Repeated subprocess call returned the same payload again.

## Fixed candidate fingerprint
Valid-path generator fingerprint remained exactly:

```text
opening_range_retest_v1 0.639513 BUY_CALL VALIDATED_CANDIDATE
compression_breakout_v1 0.675169 BUY_CALL VALIDATED_CANDIDATE
trend_pullback_v1 0.719646 BUY_CALL VALIDATED_CANDIDATE
option_pressure_confirmation_v1 0.814750 BUY_CALL VALIDATED_CANDIDATE
```

Proof:
- generator order unchanged
- candidate count unchanged
- candidate IDs unchanged
- directions unchanged
- statuses unchanged
- raw scores unchanged

## Commands and results

Focused command:

```bash
python -m pytest -q \
  tests/test_strategy_profile_fail_closed.py \
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
- `146 passed, 1 warning in 9.68s`

Static commands:

```bash
python -m json.tool config/strategy_inventory.yml
python -m py_compile \
  core/strategy_parameter_profiles.py \
  strategies/strategy_registry.py \
  tests/test_strategy_profile_integrity.py \
  tests/test_strategy_profile_fail_closed.py
ruff check \
  core/strategy_parameter_profiles.py \
  strategies/strategy_registry.py \
  tests/test_strategy_profile_integrity.py \
  tests/test_strategy_profile_fail_closed.py
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
- `5657 passed, 1 failed, 1 deselected, 935 warnings in 334.09s`

First failure:
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- observed `last_error`:
  - `RuntimeError:[AUTH] missing_kite_access_token`
  - `Missing token at /Users/madhuram/tradebot-strategy-truth-foundation/.runtime/kite_access_token`
  - `Run scripts/kite_autologin_localhost.py to refresh token.`
- expected by test:
  - `forced_cycle_error`
- Classification:
  - identical pre-existing auth/credential baseline failure reproduced
  - Phase 1C touched no auth, broker, orchestrator, or credential path

## Required fixes completed
- runtime movement generators no longer depend on silent embedded fallback after invalid profile resolution
- invalid profile states are explicitly observable through deterministic warnings
- profile drift blocks affected candidate generation rather than silently activating new stored values
- incomplete profiles block candidate generation
- missing alias targets block candidate generation
- ordinary candidate generation does not call source parsing
- source parsing stays offline-only while preserving literal embedded-default evidence
- valid-path fingerprint remained unchanged
- profile validation proved no network connections and no persistent thread starts

## Required fixes remaining
- none inside Phase 1C scope
- unrelated full-suite auth failure remains outside this change set

## Remaining risks
- `EMBEDDED_PROFILE_DEFAULTS` constants are now the offline literal evidence surface; if a future change edits runtime parameters without updating those constants, integrity validation will fail closed as `PROFILE_VALUE_DRIFT`
- the unrelated orchestrator/auth baseline still blocks a fully green repo-level suite in this environment

## Explicit non-claims
- this phase does not prove execution readiness
- this phase does not prove strategy conformance
- this phase does not prove broker correctness
- this phase does not prove runtime profitability
- this phase does not implement StrategyContext truth propagation beyond profile consumption boundaries
