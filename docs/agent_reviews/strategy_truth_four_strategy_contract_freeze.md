# Four Strategy Contract Freeze

IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Freeze and version the four-strategy contract bundle for historical validation without changing production strategy code, strategy formulas, thresholds, runtime context propagation, or phase ownership.

WHAT WAS ACTUALLY IMPLEMENTED:
A canonical, machine-readable bundle was frozen at [`docs/agent_reviews/four_strategy_contract_bundle_v1.json`](./four_strategy_contract_bundle_v1.json) with a matching SHA-256 sidecar at [`docs/agent_reviews/four_strategy_contract_bundle_v1.json.sha256`](./four_strategy_contract_bundle_v1.json.sha256). The bundle records the current repository truth for `opening_range_retest_v1`, `compression_breakout_v1`, `trend_pullback_v1`, and `vwap_reclaim_rejection_v1`, including source hashes, owner-file hashes, profile resolution, required inputs, temporal contracts, lifecycle ownership, and the current frozen candidate fingerprints. No production code changed.

ARCHITECTURE CHANGE:
NONE

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

CLOSURE STARTING HEAD:
`11cdc203565c49f01e4ca615e1c42b552ac47b51`

FROZEN SOURCE COMMIT:
`94b48666d166c45e4b65679b4811aa1ddc237b46`

BRANCH:
`fix/four-strategy-contract-freeze`

## BUNDLE FILE

- Bundle: `docs/agent_reviews/four_strategy_contract_bundle_v1.json`
- Sidecar: `docs/agent_reviews/four_strategy_contract_bundle_v1.json.sha256`
- Bundle name: `four_strategy_contract_bundle`
- Bundle ID: `four_strategy_contract_bundle_v1`
- Bundle version: `1`
- Schema version: `1`
- Bundle kind: `historical_validation_contract_freeze`
- Architecture decision: `KEEP_CANONICAL_AND_LIVE_PHASE2_SEPARATE`
- Source owner hash method: `sha256(file_bytes_at_source_commit)`

## IMMUTABILITY POLICY

The bundle is read-only evidence. It is not a runtime config, not a feature flag, and not an execution policy.

- `allow_runtime_override: false`
- `allow_shadow_copy: false`
- `editable: false`
- `canonical_serialization.encoding: UTF-8`
- `canonical_serialization.key_order: sorted`
- `canonical_serialization.list_order: semantic`
- `canonical_serialization.newline_terminated: true`
- `canonical_serialization.separators: [",", ":"]`
- `canonical_serialization.volatile_generated_timestamp: false`

## CANONICAL SERIALIZATION

The bundle is serialized canonically as UTF-8 JSON with sorted keys, semantic list order, no volatile timestamps, and a trailing newline. The measured SHA-256 for the frozen bundle is:

`71b01ae3e32044c119692411be1f4d748f03ba50a800ce4d97baca3b853793e9`

The sidecar stores:

`71b01ae3e32044c119692411be1f4d748f03ba50a800ce4d97baca3b853793e9  four_strategy_contract_bundle_v1.json`

## GAP CLASSIFICATION SUMMARY

| item | status | exact reason |
| --- | --- | --- |
| candidate identity contract: `opening_range_retest_v1` | `PROVEN` | durable owner proposal exists with explicit owner file, owner symbol, identity fields, normalization rules, restart behavior, and lifecycle owner store |
| candidate identity contract: `trend_pullback_v1` | `UNRESOLVED_WITH_EXACT_REASON` | `POOL_DEDUPLICATION_ONLY` because the only stable identity-like mechanism is `candidate_pool_dedupe_key(symbol, direction, movement_type, strategy_id)` and no durable owner store or explicit candidate identity owner exists |
| candidate identity contract: `compression_breakout_v1` | `UNRESOLVED_WITH_EXACT_REASON` | `POOL_DEDUPLICATION_ONLY` because the only stable identity-like mechanism is `candidate_pool_dedupe_key(symbol, direction, movement_type, strategy_id)` and no durable owner store or explicit candidate identity owner exists |
| candidate identity contract: `vwap_reclaim_rejection_v1` | `UNRESOLVED_WITH_EXACT_REASON` | `POOL_DEDUPLICATION_ONLY` because the only stable identity-like mechanism is `candidate_pool_dedupe_key(symbol, direction, movement_type, strategy_id)` and no durable owner store or explicit candidate identity owner exists |
| compression_breakout contract-version ownership | `UNRESOLVED_WITH_EXACT_REASON` | `UNVERSIONED_RUNTIME_CONTRACT`; no explicit semantic contract_version owner exists, so freeze identity is source commit + source-owner hashes + parameter-profile hash |
| active runtime thresholds vs dormant defaults | `PROVEN` | runtime-enforced thresholds are active; `MIN_RETEST_MINUTES` and `MAX_RETEST_MINUTES` are embedded non-enforced defaults and are not enforced in historical replay |
| explicit future-phase exclusions | `PROVEN` | all listed future-phase items are marked `FUTURE_PHASE_NOT_FROZEN` |
| baseline auth-failure evidence metadata | `PROVEN` | exact auth failure command, exit code, failure type, and failure message are recorded |
| test-residue cleanup evidence | `PROVEN` | pre-test hash, restore command, generated-file cleanup rule, and final clean status are recorded |
| subagent deployment / exact skip reason | `NOT_APPLICABLE` | primary agent executed the required read-only audit lanes in-thread; no external subagents were required or deployed |

## OPENING RANGE RETEST CONTRACT

- Runtime strategy: `opening_range_retest_v1`
- Canonical strategy ID: `OPENING_RANGE_RETEST`
- Movement type: `OPENING_RANGE_RETEST`
- Validation level: `quarantined`
- Contract version: `opening_range_retest_temporal_v1`
- Profile resolution: compatibility alias to `opening_range_breakout_v1`
- Frozen fingerprint: `opening_range_retest_v1 / BUY_CALL / RAW_CANDIDATE / 0.42150442477876104`
- Entry trigger: `opening_range_breakout_retest_hold`
- Invalid-if: `price_returns_inside_opening_range`
- Rank reason: `opening range breakout retest held`
- Required inputs: completed-bar history, spot LTP, VWAP, ORB high, ORB low, option LTP, premium change, spread, depth
- Lifecycle owner: `core/opening_range_retest_emission_store.py`
- Candidate identity status: `CANDIDATE_IDENTITY_FINGERPRINT`

This contract is intentionally durable-owner based. It is not a Phase 2 execution or validation claim.

## TREND PULLBACK CONTRACT

- Runtime strategy: `trend_pullback_v1`
- Canonical strategy ID: `TREND_PULLBACK`
- Movement type: `TREND_PULLBACK`
- Validation level: `quarantined`
- Contract version: `trend_pullback_temporal_v1`
- Profile resolution: exact profile `trend_pullback_v1`
- Frozen fingerprint: `trend_pullback_v1 / BUY_CALL / RAW_CANDIDATE / 0.648584`
- Entry trigger: `trend_pullback_hold_resume`
- Invalid-if: `pullback_breaks_anchor`
- Rank reason: `established trend resumed after a controlled pullback`
- Required inputs: completed-bar history, spot LTP, VWAP, nearest support, nearest resistance, optional previous completed close
- Temporal contract: 1m completed bars only, strict 4-bar warmup, same-session only
- Candidate identity status: `UNRESOLVED`

## COMPRESSION BREAKOUT CONTRACT

- Runtime strategy: `compression_breakout_v1`
- Canonical strategy ID: `COMPRESSION_BREAKOUT`
- Movement type: `COMPRESSION_BREAKOUT`
- Validation level: `unverified`
- Contract version: none
- Profile resolution: exact profile `compression_breakout_v1`
- Frozen fingerprint: `compression_breakout_v1 / BUY_CALL / RAW_CANDIDATE / 0.470676`
- Entry trigger: `compression_range_breakout_release`
- Invalid-if: `price_returns_inside_compression_range`
- Rank reason: `range and ATR compression released into a directional breakout`
- Required inputs: spot LTP, VWAP, range width pct, ATR short, ATR long, optional nearest resistance, optional nearest support
- Temporal contract: snapshot-only, no completed-history requirement
- Candidate identity status: `UNRESOLVED`

## VWAP RECLAIM CONTRACT

- Runtime strategy: `vwap_reclaim_rejection_v1`
- Canonical strategy ID: `VWAP_RECLAIM_REJECTION`
- Movement type: `VWAP_RECLAIM_REJECTION`
- Validation level: `unverified`
- Contract version: `vwap_reclaim_causal_v1`
- Profile resolution: exact profile `vwap_reclaim_rejection_v1`
- Frozen fingerprint: `vwap_reclaim_rejection_v1 / BUY_CALL / RAW_CANDIDATE / 0.392377`
- Entry trigger: `confirmed_vwap_reclaim_or_rejection`
- Invalid-if: `price_crosses_back_through_vwap`
- Rank reason: `confirmed VWAP reclaim/rejection in a non-chop regime`
- Required inputs: completed-bar history, spot LTP, VWAP, optional VWAP slope, optional previous spot LTP, optional volume z
- Temporal contract: 1m completed bars only, strict 3-bar warmup, same-session only
- Candidate identity status: `UNRESOLVED`

## PARAMETER AND THRESHOLD MATRIX

| strategy_id | parameter | value | unit | comparison semantics | enforced by current implementation |
| --- | --- | ---: | --- | --- | --- |
| `opening_range_retest_v1` | `MIN_RETEST_MINUTES` | 15 | minutes | embedded default only | no |
| `opening_range_retest_v1` | `MAX_RETEST_MINUTES` | 90 | minutes | embedded default only | no |
| `opening_range_retest_v1` | `MAX_RETEST_DISTANCE_PCT` | 0.0018 | fraction_of_price | less_than_or_equal | yes |
| `opening_range_retest_v1` | `MIN_BREAKOUT_DISTANCE_PCT` | 0.0008 | fraction_of_price | greater_than_or_equal | yes |
| `compression_breakout_v1` | `MAX_ATR_RATIO` | 0.75 | ratio | less_than_or_equal | yes |
| `compression_breakout_v1` | `MAX_RANGE_WIDTH_PCT` | 0.35 | fraction_of_price | less_than_or_equal | yes |
| `compression_breakout_v1` | `MIN_BREAKOUT_DISTANCE_PCT` | 0.0008 | fraction_of_price | greater_than_or_equal | yes |
| `compression_breakout_v1` | `MIN_COMPRESSION_SCORE` | 0.5 | normalized_score | greater_than_or_equal | yes |
| `compression_breakout_v1` | `MIN_VWAP_ALIGNMENT_PCT` | 0.0004 | fraction_of_price | greater_than_or_equal | yes |
| `trend_pullback_v1` | `MIN_TREND_SCORE` | 0.45 | normalized_score | greater_than_or_equal | yes |
| `trend_pullback_v1` | `MAX_PULLBACK_DISTANCE_PCT` | 0.0035 | fraction_of_price | less_than_or_equal | yes |
| `trend_pullback_v1` | `MIN_STRUCTURE_RESUME_PCT` | 0.0004 | fraction_of_price | greater_than_or_equal | yes |
| `vwap_reclaim_rejection_v1` | `MIN_VWAP_DISTANCE_PCT` | 0.00035 | fraction_of_price | greater_than_or_equal | yes |
| `vwap_reclaim_rejection_v1` | `MAX_VWAP_ENTRY_DISTANCE_PCT` | 0.0035 | fraction_of_price | less_than_or_equal | yes |
| `vwap_reclaim_rejection_v1` | `MAX_CHOP_SCORE` | 0.55 | normalized_score | less_than | yes |

## REQUIRED INPUT MATRIX

| strategy_id | field | required | missing data behavior | source owner | semantic requirement |
| --- | --- | --- | --- | --- | --- |
| `opening_range_retest_v1` | `completed_bar_history` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | truthful completed-bar prefix only |
| `opening_range_retest_v1` | `spot_ltp` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | current snapshot truth |
| `opening_range_retest_v1` | `vwap` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | authoritative causal VWAP |
| `opening_range_retest_v1` | `orb_high` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | authoritative opening-range ceiling |
| `opening_range_retest_v1` | `orb_low` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | authoritative opening-range floor |
| `opening_range_retest_v1` | `option_ltp` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | replay-time option quote truth |
| `opening_range_retest_v1` | `premium_change` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | quote-change truth |
| `opening_range_retest_v1` | `spread_pct` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | tradability boundary evidence |
| `opening_range_retest_v1` | `depth` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | tradability boundary evidence |
| `compression_breakout_v1` | `spot_ltp` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | current snapshot truth |
| `compression_breakout_v1` | `vwap` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | causal VWAP alignment |
| `compression_breakout_v1` | `range_width_pct` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | canonical completed-session range width |
| `compression_breakout_v1` | `atr_short` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | short ATR truth |
| `compression_breakout_v1` | `atr_long` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | long ATR truth |
| `compression_breakout_v1` | `nearest_resistance` | no | fallback to ORB high or day high | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | breakout ceiling when available |
| `compression_breakout_v1` | `nearest_support` | no | fallback to ORB low or day low | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | breakout floor when available |
| `trend_pullback_v1` | `completed_bar_history` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | causal 1m completed bars |
| `trend_pullback_v1` | `spot_ltp` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | current snapshot truth |
| `trend_pullback_v1` | `vwap` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | causal VWAP truth |
| `trend_pullback_v1` | `nearest_support` | no | directional call paths fail closed when anchor missing | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | support anchor for call path |
| `trend_pullback_v1` | `nearest_resistance` | no | directional put paths fail closed when anchor missing | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | resistance anchor for put path |
| `trend_pullback_v1` | `previous_completed_close` | no | optional consistency check only | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | must match penultimate bar when supplied |
| `vwap_reclaim_rejection_v1` | `completed_bar_history` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | causal 1m completed bars |
| `vwap_reclaim_rejection_v1` | `spot_ltp` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | current snapshot truth |
| `vwap_reclaim_rejection_v1` | `vwap` | yes | fail closed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | causal VWAP truth |
| `vwap_reclaim_rejection_v1` | `vwap_slope` | no | warning only optional corroboration | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | observed slope if available |
| `vwap_reclaim_rejection_v1` | `previous_spot_ltp` | no | optional provenance only | `core.runtime_snapshot_producer._strategy_context_from_market_symbol.metadata` | previous completed or prior snapshot truth |
| `vwap_reclaim_rejection_v1` | `volume_z` | no | unit-weight proxy allowed | `core.runtime_snapshot_producer._strategy_context_from_market_symbol` | truthful volume normalization if available |

## PROVENANCE MATRIX

| source artifact | type | hash / property | evidence role |
| --- | --- | --- | --- |
| `config/strategy_inventory.yml` | source file | `d14d28fea0950fe1a13eb2d975c12f9a1b0c789f21ae239fc7edea824b81c717` | inventory truth |
| `core/movement_contract.py` | source file | `3e0025abfb1266a65617082cc09293e084392aa6c6f29d7d18c0381e9f765f95` | contract truth |
| `core/strategy_parameter_profiles.py` | source file | `c40787d570956da03f814dbb6a9fd6bb528c840c42c959ddb544e16e3a861407` | profile truth |
| `strategies/movement/opening_range_breakout.py` | source file | `06be67cf8bac5b4d4901929b77e638c726a6b4910f646d20780e584327144b2e` | ORB/retest owner path |
| `strategies/movement/trend_pullback.py` | source file | `36a86be053398daaf72b885a9d214f3545df97d5a25d2ca3b3dd7a5aad8b51e1` | trend pullback owner path |
| `strategies/movement/compression_breakout.py` | source file | `c32ef22b278ad883e577ab90aac2f6e84b546eefda0f43e56e55ef0ccb00b0e7` | compression owner path |
| `strategies/movement/vwap_reclaim.py` | source file | `7a30df420d2b70b4533c96e07bcccf784fbfe9e28e504cc2af7ff0aaa89566fc` | VWAP reclaim owner path |
| `core/opening_range_retest_publication.py` | owner file | `7c8183b4f5c7a46c6165d6cc06a33c42cb8e3c89b7679b2f810374fb7779658a` | durable owner emission path |
| `core/opening_range_retest_emission_store.py` | owner file | `24702110e6e4789f510bfc291bf7a86d21056a8cd85f122e47c7ce5a104c43d0` | durable owner store |
| `core/candidate_pool.py` | owner file | `0dff0a9405340f9deda8a875af0322883b7614df369d6dc0e54d6f14c7792bfa` | pool dedupe and lifecycle snapshots |

## TEMPORAL MATRIX

| strategy_id | bar interval | completed-history requirement | warmup | cutoff semantics | future mutation expectation | session interpretation |
| --- | --- | ---: | --- | --- | --- | --- |
| `opening_range_retest_v1` | `1m` | 15 | strict 15-bar warmup | continuation bar end | future suffix mutation must not change result | same session, causal completion only |
| `compression_breakout_v1` | snapshot only | 0 | not applicable | current snapshot only | future mutation must not change current snapshot score | current snapshot over a completed session range |
| `trend_pullback_v1` | `1m` | 4 | strict 4-bar warmup | trigger bar end | future mutation after trigger prefix must not change result | causal completed-bar history only |
| `vwap_reclaim_rejection_v1` | `1m` | 3 | strict 3-bar warmup | hold bar end | future mutation after causal prefix must not change result | causal completed-bar history only |

## HISTORICAL VALIDATION PROFILE MATRIX

| strategy_id | profile resolution | parameter hash | proof lanes |
| --- | --- | --- | --- |
| `opening_range_retest_v1` | compatibility alias to `opening_range_breakout_v1` | `80e9589866186bbc73f2a5e4530a96ae2b62d86ec5062e60f7eecbfe11a7a064` | owner integration and runtime enforcement tests |
| `compression_breakout_v1` | exact profile | `514c4d0b5c1d95b138afa051a88dbae8a6b1e1fa090e1b6f608d8d412a6d75b5` | compression runtime contract tests |
| `trend_pullback_v1` | exact profile | `04513721c5b9a7e80b02c49e658f4dabfb1d9e1b379abbf42e24157c364ec2eb` | temporal conformance tests |
| `vwap_reclaim_rejection_v1` | exact profile | `ec28041cd6920b50018ef09fb4cf605aecb054b0205ec2852feebe801d98fc9b` | runtime and temporal conformance tests |

## FINGERPRINT CLASSIFICATION MATRIX

| strategy_id | output fingerprint | candidate identity fingerprint | classification |
| --- | --- | --- | --- |
| `opening_range_retest_v1` | `opening_range_retest_v1 / BUY_CALL / RAW_CANDIDATE / 0.42150442477876104` | `CANDIDATE_IDENTITY_FINGERPRINT` | fixed output + durable owner identity |
| `compression_breakout_v1` | `compression_breakout_v1 / BUY_CALL / RAW_CANDIDATE / 0.470676` | `UNRESOLVED` | fixed output only |
| `trend_pullback_v1` | `trend_pullback_v1 / BUY_CALL / RAW_CANDIDATE / 0.648584` | `UNRESOLVED` | fixed output only |
| `vwap_reclaim_rejection_v1` | `vwap_reclaim_rejection_v1 / BUY_CALL / RAW_CANDIDATE / 0.392377` | `UNRESOLVED` | fixed output only |

## DEDUPLICATION MATRIX

| strategy_id | dedupe key / lifecycle owner | restart behavior | repeat emission behavior |
| --- | --- | --- | --- |
| `opening_range_retest_v1` | `setup_id` owned by `OpeningRangeRetestEmissionStore` | replay-safe suppression of duplicate setup IDs | accepted proposal persisted once |
| `compression_breakout_v1` | `candidate_pool_dedupe_key(symbol, direction, movement_type, strategy_id)` | repeatable raw generation | dedupe handled by candidate pool |
| `trend_pullback_v1` | `candidate_pool_dedupe_key(symbol, direction, movement_type, strategy_id)` | repeatable raw generation | dedupe handled by candidate pool |
| `vwap_reclaim_rejection_v1` | `candidate_pool_dedupe_key(symbol, direction, movement_type, strategy_id)` | repeatable raw generation | dedupe handled by candidate pool |

## EMISSION AND RESTART MATRIX

| strategy_id | emission ownership | restart behavior | missing-data behavior |
| --- | --- | --- | --- |
| `opening_range_retest_v1` | durable owner store + publication helper | `ALREADY_EMITTED` on replay with same `setup_id` | fail closed on missing or malformed history; reject missing owner store |
| `compression_breakout_v1` | raw candidate only | no durable owner store | fail closed on missing required context |
| `trend_pullback_v1` | raw candidate only | no durable owner store | fail closed on missing required context |
| `vwap_reclaim_rejection_v1` | raw candidate only | no durable owner store | fail closed on missing required context |

## MISSING DATA AND FAILURE MATRIX

| strategy_id | missing input / failure | behavior |
| --- | --- | --- |
| `opening_range_retest_v1` | missing history, malformed history, missing owner store, ORB reconciliation mismatch | fail closed or reject with reason |
| `compression_breakout_v1` | missing `range_width_pct`, `atr_short`, `atr_long`, `vwap`, or required price truth | fail closed |
| `trend_pullback_v1` | missing anchor / missing required input / previous-close mismatch | fail closed |
| `vwap_reclaim_rejection_v1` | missing history, short history, metadata-only confirmation, missing required input | fail closed |

## AUTHORITY MATRIX

| field / authority | owner |
| --- | --- |
| raw strategy score | strategy |
| rank score | ranking |
| Phase 2 score | phase2 |
| execution eligibility | live_phase2 |
| freshness score | live_phase2 |
| liquidity score | live_phase2 |
| opening-range durable ownership | `OpeningRangeRetestEmissionStore` |
| candidate pool dedupe | `core.candidate_pool.candidate_pool_dedupe_key` |

The generator-owned contracts do not claim Phase 2 truth, execution authority, or liquidity/freshness ownership.

## EXPLICIT FUTURE PHASE EXCLUSIONS

The bundle intentionally does **not** claim any of the following:

- profitability
- live readiness
- production certification
- execution authority
- Phase 2 authority

Historical validation is frozen only. No production runtime decision is implied by this document.

## SUBAGENT RESULTS

`NOT_APPLICABLE`

Reason: the primary agent executed the required read-only audit lanes in-thread; no external subagents were required or deployed.

## FOCUSED BUNDLE TEST COMMAND

```bash
python -m pytest -q \
  tests/test_four_strategy_contract_freeze.py \
  tests/test_strategy_inventory.py \
  tests/test_strategy_profile_integrity.py \
  tests/test_strategy_registry_integrity.py \
  tests/test_candidate_phase2_ownership.py \
  tests/test_candidate_phase2_semantic_ownership.py \
  tests/test_opening_movement_strategies.py \
  tests/test_compression_breakout_range_width_runtime_contract.py \
  tests/test_vwap_reclaim_runtime_conformance.py \
  tests/test_vwap_reclaim_temporal_conformance.py \
  tests/test_trend_pullback_temporal_conformance.py \
  tests/test_opening_range_retest_owner_integration.py \
  tests/test_opening_range_retest_runtime_owner_enforcement.py
```

## FOCUSED BUNDLE TEST RESULT

`109 passed, 1 warning in 6.09s`

## FROZEN CONTROL COMMAND

```bash
python -m pytest -q tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports
```

## FROZEN CONTROL RESULT

`RuntimeError: [AUTH] missing_kite_access_token`

This control was used as baseline evidence only. It does not indicate a four-strategy contract failure.

## BASELINE AUTH FAILURE REPRODUCTION

The same auth failure reproduced at the current frozen baseline and remains unrelated to the four-strategy bundle:

- test: `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- failure: `RuntimeError: [AUTH] missing_kite_access_token`
- classification: pre-existing unrelated baseline failure

## FULL SUITE COMMAND

```bash
python -m pytest -q
```

## FULL SUITE RESULT

`1 failed, 6063 passed, 24 deselected, 935 warnings in 357.62s`

## NEW FAILURE ANALYSIS

No new four-strategy bundle failure appeared in the full suite. The only failing test remains the pre-existing auth path failure in `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`.

## TEST RESIDUE CLEANUP METHOD

The full suite produced transient runtime residue. It was cleaned without touching source data:

- restored `runtime/strategy_validation/regime_timeline.jsonl` from `HEAD`
- removed generated MagicMock-named runtime files from the worktree

No market data file was modified.

## PRODUCTION FILE CHANGE CHECK

No production strategy files changed.

The frozen bundle and evidence/test updates were limited to contract documentation and test verification.

## STATIC CHECKS

Executed successfully:

```bash
python -m py_compile tests/test_four_strategy_contract_freeze.py
ruff check tests/test_four_strategy_contract_freeze.py
git diff --check
python -m json.tool docs/agent_reviews/four_strategy_contract_bundle_v1.json
```

## RESIDUAL LIMITS

- Full repository suite is not green because of the known unrelated auth failure.
- No historical validation, profitability analysis, live-readiness claim, or production certification was started.
- No Phase 2 authority was claimed or implemented.
- The three repeatable raw strategies remain classified as `UNRESOLVED_WITH_EXACT_REASON` for durable identity because only pool-level deduplication exists.

## ROLLBACK

Rollback is file-local and straightforward:

- revert `docs/agent_reviews/four_strategy_contract_bundle_v1.json`
- revert `docs/agent_reviews/four_strategy_contract_bundle_v1.json.sha256`
- revert `docs/agent_reviews/strategy_truth_four_strategy_contract_freeze.md`
- revert `tests/test_four_strategy_contract_freeze.py`
- restore `docs/agent_reviews/four_strategy_contract_bundle.json` only if the rename is being undone

## CLAIM BOUNDARY

This evidence proves a frozen four-strategy historical-validation bundle with canonical serialization, stable hashes, owner/lifecycle matrices, and reproducible tests. It does **not** prove historical edge, profitability, live readiness, production certification, or Phase 2 authority.

## FINAL VERDICT

`RIGHT_WITH_GAPS`
