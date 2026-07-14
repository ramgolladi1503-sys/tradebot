IMPLEMENTATION DIRECTION:
RIGHT

VERDICT:
PHASE2C_PASS_WITH_PREEXISTING_TEST_FAILURE

APPROVED OBJECTIVE:
Enforce the existing ownership boundary between raw strategy candidates and downstream Phase-2 option, liquidity, freshness and tradability validation.

WHAT WAS ACTUALLY IMPLEMENTED:
- Changed directional movement generators to emit truthful raw setup candidates only.
- Removed fabricated generator-owned values for `option_confirmation_score`, `liquidity_score`, and `freshness_score`.
- Stopped raw generators from emitting `VALIDATED_CANDIDATE`; they now emit `RAW_CANDIDATE`.
- Reused the existing option-confirmation path to enrich directional raw candidates inside `core/candidate_pool_orchestrator.py`.
- Made ownership-boundary validation mandatory at raw candidate intake and logged deterministic `CANDIDATE_OWNERSHIP_BLOCKED` events without aborting unrelated generators.
- Converted `strategies/movement/option_pressure.py` into a compatibility wrapper that emits no standalone market-thesis candidate while preserving profile metadata.

ARCHITECTURE ASSESSMENT:
NONE

STARTING COMMIT:
`2262e3baecb05b43f6113989f9715ea3ff199433`

PRIOR PHASE COMMITS:
- Phase 0: `cf2d74bc7a2938a08bc651e25b5334481479d68c`
- Phase 1A: `9ace90c0b49d790f0e8926a75ecd9492ae6d3b26`
- Phase 1B: `2a247ec6d92f60aa101d462eb6f3013d1aec4d54`
- Phase 1C: `e74bbac98cfb3db43e15129bc78be4bb47564c45`
- Phase 2A: `db19774008db93671c8a24b93f98cb7488498ad2`
- Phase 2B: `b9142aa04cb977eea9eb9eff0eb6d6a2893c1d85`
- Phase 2B observability: `2262e3baecb05b43f6113989f9715ea3ff199433`

FILES CHANGED:
- `core/movement_contract.py`
- `core/option_confirmation.py`
- `core/candidate_pool_orchestrator.py`
- `core/candidate_normalizer.py`
- `strategies/movement/_utils.py`
- `strategies/movement/option_pressure.py`
- `tests/test_candidate_phase2_ownership.py`
- `tests/test_movement_contract.py`
- `tests/test_candidate_pool_orchestrator.py`
- `tests/test_candidate_pool_contract_snapshots.py`
- `tests/test_option_confirmation.py`
- `tests/test_strategy_context_truth.py`
- `tests/test_strategy_profile_fail_closed.py`
- `tests/test_strategy_missing_evidence_policy.py`
- `tests/test_strategy_missing_evidence_observability.py`
- `tests/test_strategy_registry_integrity.py`
- `tests/test_opening_movement_strategies.py`
- `tests/test_compression_trend_movement_strategies.py`
- `tests/test_vwap_trap_movement_strategies.py`
- `tests/test_exhaustion_mean_reversion_strategies.py`
- `tests/test_event_late_day_movement_strategies.py`
- `tests/fixtures/candidate_pool_contract/clean_report.json`
- `tests/fixtures/candidate_pool_contract/no_trade_report.json`
- `tests/fixtures/candidate_pool_contract/fallback_blocked_report.json`

COMPLETE FIELD-OWNERSHIP MATRIX:

| field | current writer | current reader | contract owner | current runtime meaning after Phase 2C | correct meaning | current default | fabricated by generator before Phase 2C | required correction | compatibility impact |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `strategy_id` | movement generator | pool, reports, tests | strategy layer | runtime strategy identity | strategy identity | required | no | none | none |
| `movement_type` | movement generator | pool, reports, no-trade, tests | strategy layer | setup family | setup family | required | no | none | none |
| `direction` | movement generator | pool, option confirmation, reports | strategy layer | directional intent | directional intent | required | no | none | none |
| `thesis`/`reason` | movement generator | reports/tests | strategy layer | setup thesis text | setup thesis text | required | no | none | none |
| `entry_trigger` | movement generator | reports/tests | strategy layer | setup trigger text | setup trigger text | required | no | none | none |
| `invalid_if` | movement generator | reports/tests | strategy layer | invalidation description | invalidation description | required | no | none | none |
| `raw_score` | movement generator | pool sorting, reports, tests | strategy layer | setup-quality score only | setup/pattern score only | required | yes, previously mixed with downstream quote truth indirectly | keep setup-only | expected score change at raw boundary only |
| `price_structure_score` | movement generator | reports/tests | strategy layer | setup structure score | setup structure score | required | no | none | none |
| `confidence_score` | movement generator | reports/tests | strategy layer | setup confidence derived from setup score and trap risk | setup confidence only | required | no | none | none |
| `option_confirmation_score` | downstream enrichment | option scoring, ranking/report consumers, tests | Phase 2 | real quote-confirmation score | downstream-only confirmation truth | `None` until enrichment | yes | unset at raw generation | tests and snapshots updated |
| `liquidity_score` | downstream enrichment | ranking/report consumers, tests | Phase 2 | real spread/depth liquidity score | downstream liquidity truth | `None` until enrichment | yes | unset at raw generation | tests and snapshots updated |
| `freshness_score` | downstream enrichment | ranking/report consumers, tests | Phase 2 | real quote-age freshness score | downstream freshness truth | `None` until enrichment | yes | unset at raw generation | tests and snapshots updated |
| `confluence_score` | movement generator | reports/tests | strategy layer | setup confluence score | setup confluence score | required | no | none | none |
| `status` | raw generator, downstream enrichment, no-trade | pool, reports, ranking/tests | split by stage | `RAW_CANDIDATE` before enrichment; `VALIDATED_CANDIDATE`/`BLOCKED_CANDIDATE` after enrichment | stage-truthful state | required | yes, generators used `VALIDATED_CANDIDATE` | raw candidates cannot self-validate | direct-generator tests updated |
| `option symbol/strike/expiry` | none in raw candidate | downstream/tradebuilder paths elsewhere | Phase 2 | not claimed by movement candidate | downstream-resolved contract truth or provisional hint only | absent | no | none in this phase | none |
| `execution_eligible` / `executable_eligible` | downstream enrichment / no-trade / later engines | reports, ranking/tests | Phase 2 | false at raw generation; updated after downstream checks | downstream-owned tradability/execution eligibility | false | effectively yes via validated raw status semantics | raw generators do not mark executable | direct-generator tests updated |
| `warnings` | strategy layer, ownership blocker, downstream enrichment | reports/tests | mixed | setup warnings plus downstream warnings after enrichment | observable per-stage warnings | `()` | no | none | none |
| `provenance` / `profile_lineage` / `evidence` | strategy layer then downstream enrichment | reports/tests | mixed by field | setup evidence first, downstream truth evidence appended later | stage-owned provenance only | required/optional | yes for Phase-2 evidence keys in some old paths | raw boundary rejects Phase-2 evidence keys | enforced by validator |

ALL CURRENT WRITERS AND READERS:
- Raw writers:
  - `strategies/movement/_utils.py::make_candidate`
  - `strategies/movement/no_trade_chop.py` for safety suppression only
- Raw readers:
  - `core/candidate_pool_orchestrator.py`
  - `core/candidate_pool.py`
  - direct strategy tests
- Downstream writers:
  - `core/option_confirmation.py::enrich_candidate_with_option_confirmation`
  - `core/no_trade_engine.py` influences no-trade candidates and report blockers
- Downstream readers:
  - `core/candidate_normalizer.py`
  - candidate-pool report serialization and snapshot tests
  - scoring/ranking consumers that already expect enriched values
- Inventory/registry readers:
  - `strategies/strategy_registry.py`
  - `tests/test_strategy_registry_integrity.py`
  - `tests/test_strategy_profile_fail_closed.py`

CONTRACT CONFLICTS FOUND:
- Raw movement generators were previously writing `VALIDATED_CANDIDATE`.
- Raw movement generators were previously writing non-null `option_confirmation_score`, `liquidity_score`, and `freshness_score`.
- Standalone `OPTION_QUOTE_CONFIRMATION` previously appeared as a directional candidate producer instead of downstream evidence.

RAW-CANDIDATE STATE DECISION:
- Existing contract already supported `RAW_CANDIDATE`.
- Phase 2C reuses that state rather than inventing a new candidate type.
- Mandatory raw-boundary validation now blocks any strategy-produced candidate that claims `VALIDATED_CANDIDATE`, `RANKED_OPPORTUNITY`, Phase-2-owned score fields, or Phase-2 truth evidence keys.

DOWNSTREAM-OWNED UNSET REPRESENTATION:
- `StrategyCandidate.option_confirmation_score: float | None`
- `StrategyCandidate.liquidity_score: float | None`
- `StrategyCandidate.freshness_score: float | None`
- `None` means not evaluated yet.
- `core/candidate_normalizer.py` now treats `None` as an unset raw value rather than forcing a float conversion.

PATTERN-SCORE HANDLING:
- `raw_score` is now setup-owned only.
- `make_candidate()` sets:
  - `confluence_score = price_structure_score`
  - `raw_score = confluence_score`
  - `confidence_score = raw_score * (1 - trap_risk_score * 0.25)`
- No setup formula or threshold was tuned.
- The previous mixed raw score was removed because it embedded fake downstream confirmation/liquidity/freshness truth.

OPTION-CONFIRMATION ROLE BEFORE/AFTER:
- Before:
  - `generate_option_pressure_candidates()` emitted a standalone `StrategyCandidate`.
  - It appeared in default candidate-generator ordering and complete-context fingerprints.
- After:
  - `strategies/movement/option_pressure.py` preserves profile metadata but emits `()`.
  - `core/candidate_pool_orchestrator.py` applies the existing downstream option-confirmation logic to directional raw candidates.
  - `CandidateOptionConfirmation` remains the observable downstream confirmation artifact.
  - No standalone option-confirmation candidate is counted as a directional market-thesis strategy.

NO-TRADE ROLE VERIFICATION:
- `NO_TRADE_CHOP` remains `safety_suppression`.
- Canonical runtime identity remains `no_trade_engine_v1`.
- No threshold or no-trade policy logic changed.

MANDATORY BOUNDARY BEHAVIOR:
- `core/movement_contract.py::phase2_boundary_violations(...)` now treats the following as raw-strategy ownership violations:
  - non-`None` `option_confirmation_score`
  - non-`None` `liquidity_score`
  - non-`None` `freshness_score`
  - `status == VALIDATED_CANDIDATE`
  - `status == RANKED_OPPORTUNITY`
  - Phase-2 evidence keys such as `quote_source`, `fallback_used`, `option_ltp_age_sec`, `liquidity_truth`, `freshness_truth`, `option_confirmation_truth`
- `core/candidate_pool_orchestrator.py` now enforces that check at raw candidate intake.
- Violations are dropped with deterministic logging:

```text
event=CANDIDATE_OWNERSHIP_BLOCKED runtime_strategy_id=bad_strategy_v1 violating_fields=freshness_score,liquidity_score,option_confirmation_score,status reason=strategy_candidate_claims_phase2_owned_truth
```

- Logging is wrapped in `try/except`, so observability cannot abort unrelated generators.

SETUP FINGERPRINT BEFORE/AFTER:
- Before Phase 2C direct-generator fingerprint:
  - `opening_range_retest_v1 | BUY_CALL | 0.639513 | opening range breakout retest held with option-side confirmation`
  - `compression_breakout_v1 | BUY_CALL | 0.675169 | range and ATR compression released into a confirmed option-side breakout`
  - `trend_pullback_v1 | BUY_CALL | 0.719646 | established trend resumed after controlled pullback with option-side confirmation`
  - `option_pressure_confirmation_v1 | BUY_CALL | 0.814750 | option pressure confirmation`
- After Phase 2C raw-generator fingerprint:
  - `opening_range_retest_v1 | BUY_CALL | 0.328053 | opening range breakout retest held with option-side confirmation`
  - `compression_breakout_v1 | BUY_CALL | 0.470676 | range and ATR compression released into a confirmed option-side breakout`
  - `trend_pullback_v1 | BUY_CALL | 0.648584 | established trend resumed after controlled pullback with option-side confirmation`
- Preserved fields:
  - strategy ids
  - movement types
  - directions
  - thesis text
  - entry trigger text
  - invalidation text
- Expected ownership correction:
  - raw scores no longer include downstream quote-confirmation/liquidity/freshness truth
  - standalone option-confirmation candidate is removed from the setup layer

OWNERSHIP FINGERPRINT BEFORE/AFTER:
- Before raw generation:
  - `status=VALIDATED_CANDIDATE`
  - `option_confirmation_score=0.814750`
  - `liquidity_score=0.860000`
  - `freshness_score=0.840000`
  - `execution_eligible=true`
- After raw generation:
  - `status=RAW_CANDIDATE`
  - `option_confirmation_score=None`
  - `liquidity_score=None`
  - `freshness_score=None`
  - `execution_eligible=false`
- After downstream enrichment in `build_candidate_pool_report(...)`:
  - `opening_range_retest_v1 | VALIDATED_CANDIDATE | 0.81475 | 0.86 | 0.84 | true`
  - `compression_breakout_v1 | VALIDATED_CANDIDATE | 0.81475 | 0.86 | 0.84 | true`
  - `trend_pullback_v1 | VALIDATED_CANDIDATE | 0.81475 | 0.86 | 0.84 | true`

CANDIDATE-COUNT CHANGES:
- Default directional generator count changed from `11` to `10`.
- Standalone `option_pressure_confirmation_v1` no longer appears in directional candidate fingerprints.
- Complete enriched pool still carries directional candidates plus downstream `option_confirmations` as separate artifacts.
- `report.metadata["raw_candidate_count_before_phase2_enrichment"]` records the directional raw count explicitly.

EXPECTED OWNERSHIP CORRECTIONS:
- Direct movement generators now emit `RAW_CANDIDATE`.
- Direct movement generators now leave Phase-2-owned fields unset.
- Standalone option-pressure candidate generation disappears from the directional setup inventory.
- Candidate-pool reports enrich directional candidates with real quote evidence through the existing downstream path.

UNEXPECTED SETUP CHANGES:
- None found.
- The observed score changes are ownership-surface corrections, not setup-formula changes.

FOCUSED TESTS AND COUNTS:
- Required focused suite:

```bash
python -m pytest -q \
  tests/test_candidate_phase2_ownership.py \
  tests/test_strategy_missing_evidence_observability.py \
  tests/test_strategy_missing_evidence_policy.py \
  tests/test_strategy_context_truth.py \
  tests/test_strategy_profile_fail_closed.py \
  tests/test_candidate_pool.py \
  tests/test_candidate_pool_quality.py \
  tests/test_candidate_pool_orchestrator.py \
  tests/test_candidate_pool_contract_snapshots.py \
  tests/test_option_confirmation.py \
  tests/test_no_trade_engine.py \
  tests/test_strategy_generators_lineage.py \
  tests/test_movement_registry.py
```

- Result: `120 passed, 1 warning in 7.54s`

- Additional ownership-related tests discovered from repo search:

```bash
python -m pytest -q \
  tests/test_strategy_registry_integrity.py \
  tests/test_opening_movement_strategies.py \
  tests/test_compression_trend_movement_strategies.py \
  tests/test_vwap_trap_movement_strategies.py \
  tests/test_exhaustion_mean_reversion_strategies.py \
  tests/test_event_late_day_movement_strategies.py \
  tests/test_movement_contract.py \
  tests/test_opportunity_scoring.py \
  tests/test_opportunity_scoring_regime_profile_opt_in.py \
  tests/test_execution_grade_firewall.py \
  tests/test_hard_downgrade_engine.py \
  tests/test_candidate_normalizer.py
```

- Result: `111 passed, 1 warning in 6.29s`

STATIC CHECKS:

```bash
python -m py_compile \
  core/movement_contract.py \
  strategies/movement/_utils.py \
  core/candidate_pool_orchestrator.py \
  tests/test_candidate_phase2_ownership.py

ruff check \
  core/movement_contract.py \
  strategies/movement \
  core/candidate_pool_orchestrator.py \
  tests/test_candidate_phase2_ownership.py

git diff --check
```

STATIC CHECK RESULT:
All passed.

FULL-SUITE RESULT:
- `python -m pytest -q`
- Result: `1 failed, 5721 passed, 1 deselected, 935 warnings in 297.87s (0:04:57)`

FIRST FAILURE:
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- Failure detail:

```text
RuntimeError:[AUTH] missing_kite_access_token
Missing token at /Users/madhuram/tradebot-strategy-truth-foundation/.runtime/kite_access_token
Run scripts/kite_autologin_localhost.py to refresh token.
```

- Classification: pre-existing baseline failure, identical to the previously established orchestrator credential path.

RISKS:
- Some legacy consumers outside the focused Phase 2C surface may still implicitly assume all candidates are already enriched. The current targeted tests and normalizer fix cover the exercised paths, but the repository remains broad.
- Raw-score comparisons across older artifacts are no longer apples-to-apples with pre-Phase-2C values because those older values embedded downstream truth.
- If a future strategy module bypasses `make_candidate()` and writes Phase-2-owned fields directly, the orchestrator will now drop it. That is intended, but the failure will surface as a logged ownership block.

ROLLBACK:
- Revert only the Phase 2C ownership commit.
- No config migration or data backfill is required.

EXPLICIT NON-CLAIMS:
- No strategy threshold tuning.
- No setup-definition rewrite.
- No Phase 2A StrategyContext propagation change.
- No Phase 2B missing-evidence policy change.
- No new Phase-2 service, registry, queue, database, or event bus.
- No change to no-trade policy, broker, risk, order, execution, dashboard, backtesting, or WFA behavior.
