# Strategy Truth Phase 1A — Registry and Inventory Integrity

## Acceptance result

```text
PHASE1A_PASS_WITH_PREEXISTING_TEST_FAILURE
```

The only full-suite failure is `tests/test_orchestrator_reports_finally.py`,
which was reproduced on the untouched baseline before Phase 1A began.

## Agent work contract

```text
source_agent: Codex
action: GENERATE_PATCH
title: Make movement registry and inventory references mechanically truthful
scope: Phase 1A registry and inventory integrity only
requested_paths: strategies/strategy_registry.py, config/strategy_inventory.yml, tests/test_strategy_registry_integrity.py, docs/agent_reviews/strategy_truth_phase1a_registry_integrity.md
allowed_paths: strategies/strategy_registry.py, config/strategy_inventory.yml, tests/test_strategy_registry_integrity.py, docs/agent_reviews/strategy_truth_phase1a_registry_integrity.md
forbidden_paths: main.py, run_live.sh, credentials.py, .env, *.env, runtime/live*, logs/broker*, secrets*, core/execution*, core/broker*, core/order*, core/risk*, core/feed*, core/candidate_pool_orchestrator.py, strategies/movement/*, dashboard/*
expected_tests: focused registry/inventory tests, movement/candidate-pool regressions, and full pytest suite
acceptance_proof: All 29 registry modules import, every declared callable resolves, all twelve inventory mappings are one-to-one, aliases are unambiguous, candidate order and fixed outputs match Phase 0, and quarantine remains metadata-only.
```

## Baseline and Phase 0

- Baseline SHA: `691b8a750e805c0acffb7543e3f5b3cede2ee6d9`
- Phase 0 commit: `cf2d74bc7a2938a08bc651e25b5334481479d68c`
- Phase 0 baseline classification: `PRE_EXISTING_REPRODUCED`

Before Phase 1A, a disposable detached worktree at `691b8a75` ran:

```bash
python -m pytest -q tests/test_orchestrator_reports_finally.py
```

The untouched baseline returned `1 failed in 10.57s`. It expected
`forced_cycle_error` but reached `RuntimeError:[AUTH]
missing_kite_access_token` first through:

```text
Orchestrator._legacy_live_monitoring
-> fetch_live_market_data
-> get_ltp
-> kite_client.ensure
-> get_kite_credentials
-> resolve_access_token
```

No credentials were added and no broker call or success is claimed.

## Files changed

- `strategies/strategy_registry.py`: replaced synthesized movement entries with
  explicit compatibility-preserving registrations, corrected stale legacy
  references, and added fail-closed validation for every registry module and
  declared callable.
- `config/strategy_inventory.yml`: added unique runtime strategy IDs and the
  missing `VWAP_RECLAIM` compatibility alias.
- `tests/test_strategy_registry_integrity.py`: added mechanical, behavioral,
  ordering, alias, side-effect, and failure-path tests.
- `docs/agent_reviews/strategy_truth_phase1a_registry_integrity.md`: records the
  audit, test evidence, risks, rollback, and non-claims.

No movement module, movement package export, candidate-pool module, strategy
profile, runtime context, broker, feed, risk, order, execution, or dashboard file
was changed.

## Before/after registry matrix

`Status` is inventory maturity metadata and does not establish predictive edge.

| Inventory ID | Legacy registry ID | Runtime strategy ID | Movement type | Module | Before declared callable | After exact callable | Role | Status | Before mismatch |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `MEAN_REVERSION_EXTENSION` | same | `mean_reversion_extension_v1` | same | `mean_reversion_extension.py` | `generate_mean_reversion_extension_candidates` | same | candidate generator | `PARTIAL_DETECTOR` | runtime ID unmodelled |
| `COMPRESSION_BREAKOUT` | same | `compression_breakout_v1` | same | `compression_breakout.py` | `generate_compression_breakout_candidates` | same | candidate generator | `PARTIAL_DETECTOR` | runtime ID unmodelled |
| `TREND_PULLBACK` | same | `trend_pullback_v1` | same | `trend_pullback.py` | `generate_trend_pullback_candidates` | same | candidate generator | `UNVERIFIED`, quarantined | runtime ID unmodelled |
| `VWAP_RECLAIM_REJECTION` | `VWAP_RECLAIM` | `vwap_reclaim_rejection_v1` | canonical | `vwap_reclaim.py` | `generate_vwap_reclaim_candidates` | `generate_vwap_reclaim_rejection_candidates` | candidate generator | `PARTIAL_DETECTOR` | missing callable and alias |
| `OPENING_DRIVE` | same | `opening_drive_v1` | same | `opening_drive.py` | `generate_opening_drive_candidates` | same | candidate generator | `PARTIAL_DETECTOR` | runtime ID unmodelled |
| `FAILED_BREAKOUT_TRAP` | same | `failed_breakout_trap_v1` | same | `failed_breakout_trap.py` | `generate_failed_breakout_trap_candidates` | same | candidate generator | `PARTIAL_DETECTOR` | runtime ID unmodelled |
| `EXHAUSTION_REVERSAL` | same | `exhaustion_reversal_v1` | same | `exhaustion_reversal.py` | `generate_exhaustion_reversal_candidates` | same | candidate generator | `UNVERIFIED`, quarantined | runtime ID unmodelled |
| `DIRECTIONAL_VOLATILITY_EXPANSION` | `EVENT_VOLATILITY_EXPANSION` | `event_volatility_expansion_v1` | `EVENT_VOLATILITY_EXPANSION` | `event_volatility_expansion.py` | `generate_event_volatility_expansion_candidates` | same | candidate generator | `PARTIAL_DETECTOR` | runtime ID unmodelled; alias already explicit |
| `LATE_DAY_MOMENTUM` | same | `late_day_momentum_v1` | same | `late_day_momentum.py` | `generate_late_day_momentum_candidates` | same | candidate generator | `PARTIAL_DETECTOR` | runtime ID unmodelled |
| `OPTION_QUOTE_CONFIRMATION` | `OPTION_PRESSURE` | `option_pressure_confirmation_v1` | `OPTION_PRESSURE_CONFIRMATION` | `option_pressure.py` | `generate_option_pressure_candidates` | same | option confirmation | `UNVERIFIED` | role and runtime ID unmodelled |
| `OPENING_RANGE_RETEST` | `OPENING_RANGE_BREAKOUT` | `opening_range_retest_v1` | canonical | `opening_range_breakout.py` | `generate_opening_range_breakout_candidates` | `generate_opening_range_retest_candidates` | candidate generator | `UNVERIFIED`, quarantined | missing callable; alias already explicit |
| `NO_TRADE_CHOP` | same | `no_trade_engine_v1` | same | `no_trade_chop.py` | `generate_no_trade_chop_candidates` | `generate_no_trade_candidates` | safety suppression | `UNVERIFIED` | missing callable and role mismatch |

## Mismatches corrected

1. `VWAP_RECLAIM` now explicitly maps to inventory
   `VWAP_RECLAIM_REJECTION`, module runtime ID
   `vwap_reclaim_rejection_v1`, and callable
   `generate_vwap_reclaim_rejection_candidates`.
2. `OPENING_RANGE_BREAKOUT` remains the public compatibility key and explicit
   alias for `OPENING_RANGE_RETEST`; its callable is now the real
   `generate_opening_range_retest_candidates` export.
3. `NO_TRADE_CHOP` now references `generate_no_trade_candidates` and carries the
   explicit `safety_suppression` role. Its existing
   `strategy_kind="candidate_generator_strategy"` remains unchanged for
   certification compatibility.
4. Option pressure retains public ID `OPTION_PRESSURE` but explicitly maps to
   inventory role `option_confirmation`, runtime strategy ID
   `option_pressure_confirmation_v1`, and movement type
   `OPTION_PRESSURE_CONFIRMATION`.
5. Every movement entry now stores its actual lower-case, versioned module
   `STRATEGY_ID`; no public ID or emitted candidate ID was renamed.
6. `HTF_OPENING_DRIVE_CONT` now resolves to the actual
   `core/candidate_audits/htf_strategies.py:HTFStrategy` class with explicit
   constructor argument `OPENING_DRIVE_CONT`.
7. `PRO_STRATEGY_ENGINE` now resolves the actual qualified method
   `ProStrategyEngine.run`, and `ENSEMBLE` now resolves `ensemble_signal`.
8. Metadata-only `TEST_STRAT` no longer claims a nonexistent implementation
   module. Its module reference is the registry file where the fixture metadata
   is defined, and it declares no callable or production eligibility.

## Alias compatibility

- `VWAP_RECLAIM` -> `VWAP_RECLAIM_REJECTION` (added in Phase 1A).
- `OPENING_RANGE_BREAKOUT` -> `OPENING_RANGE_RETEST` (preserved).
- `EVENT_VOLATILITY_EXPANSION` ->
  `DIRECTIONAL_VOLATILITY_EXPANSION` (preserved).
- `OPTION_PRESSURE` -> `OPTION_QUOTE_CONFIRMATION` (preserved).

Canonical IDs and aliases share one fail-closed index. Duplicate canonical IDs,
duplicate runtime IDs, ambiguous aliases, aliases with invalid types, unknown
roles, and execution-eligible inventory rows are rejected.

## Registry validation boundary

Phase 1A mechanically imports every module referenced by all 29 registry entries
and resolves every non-empty callable, including qualified callables. The
seventeen components outside the movement inventory remain exactly allowlisted
for inventory reconciliation only; the allowlist does not exempt their module or
callable references from structural validation.

For each of the twelve inventory-managed movement components, it additionally
proves:

- module file exists and imports;
- exact callable exists and is callable;
- callable accepts positional `(ctx, regime)` in that order without unknown
  required arguments;
- callable is the same object exported by `strategies.movement`;
- module `STRATEGY_ID` matches the explicit runtime strategy ID;
- module `MOVEMENT_TYPE` matches the explicit movement type;
- canonical inventory mapping count is exactly one.

The non-movement inventory allowlist contains two execution entries, one
aggregate, one deferred aggregate, twelve helpers, and one test fixture. Their
interfaces are not invoked, and no execution behavior is changed; their module
and callable references are nevertheless imported and resolved mechanically.

## Candidate behavior and ordering proof

`core/candidate_pool_orchestrator.py` was not modified. The default activation
order remains:

```text
opening_drive
opening_range_retest
compression_breakout
trend_pullback
vwap_reclaim_rejection
failed_breakout_trap
exhaustion_reversal
mean_reversion_extension
event_volatility_expansion
option_pressure
late_day_momentum
```

No-trade remains outside that tuple and is evaluated and appended separately.
The test freezes the exact callable sequence.

A rich, fixed synthetic Phase 0 context was captured before registry edits. It
emitted, in order:

```text
opening_range_retest_v1       raw_score=0.639513 BUY_CALL VALIDATED_CANDIDATE
compression_breakout_v1       raw_score=0.675169 BUY_CALL VALIDATED_CANDIDATE
trend_pullback_v1             raw_score=0.719646 BUY_CALL VALIDATED_CANDIDATE
option_pressure_confirmation_v1 raw_score=0.814750 BUY_CALL VALIDATED_CANDIDATE
```

The Phase 1A regression test reproduces that fingerprint. All three quarantined
generators remain present in the default tuple, proving quarantine is still
metadata-only and has not changed candidate counts or activation.

## Tests and outcomes

Focused registry, inventory, candidate-pool, movement, and compatibility run:

```bash
python -m pytest -q \
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
  tests/test_movement_registry.py \
  tests/test_upstox_data_recovery_pipeline.py
```

Final focused outcome after independent review fixes: `128 passed`.

Additional validation:

```bash
python -m json.tool config/strategy_inventory.yml
python -m py_compile strategies/strategy_registry.py tests/test_strategy_registry_integrity.py
ruff check strategies/strategy_registry.py tests/test_strategy_registry_integrity.py
git diff --check
```

All passed before the full suite.

Full suite:

```bash
python -m pytest -q
```

Outcome: `5635 passed, 1 failed, 1 deselected, 935 warnings in 317.38s`.

The sole failure was the same pre-existing
`test_cycle_exception_still_writes_reports` missing-token failure reproduced on
untouched `691b8a75`. There were seventeen more passes than the Phase 0 full run,
corresponding to the final Phase 1A integrity tests.

## Import side-effect proof

Inventory loading and validation run in a fresh Python subprocess and assert
that no credential, broker, execution, feed, order, risk, or
`strategies.risk_manager` module enters `sys.modules`. Full registry integrity
validation separately imports all registered modules and resolves declared
callables but does not invoke strategy logic, broker APIs, or order actions. The
HTF constructor is instantiated only in a focused offline structural test and
does not evaluate market data.

Registry identity, allowlist membership, and exact canonical metadata are
validated before any registered module is imported. Tests prove an unknown ID
or drifted non-movement entry is rejected with zero resolver calls. Independent
review also observed zero network connection attempts and zero new threads while
resolving the final 29-module registry in a clean process.

## Risks

- Importing every registry module proves reference integrity, not that every
  legacy module has a uniform strategy interface. Only inventory-managed
  movement callables receive the candidate-generator interface gate.
- This registry still is not the runtime activation source. That is intentional
  compatibility preservation, but registry/runtime drift remains possible and
  is guarded here by ordering and output regression tests.
- Quarantine is declarative only. Unsafe readers must not infer that inventory
  status changes runtime activation.
- A callable importing successfully proves structural integrity, not pattern
  correctness, predictive value, tradability, profitability, or readiness.

## Rollback and migration

No runtime migration is required. New metadata fields are optional dataclass
fields with defaults, so existing test and caller construction remains valid.
Registry loads continue returning fresh mutable entries, preserving prior caller
semantics. Legacy dictionary keys, insertion order, movement file-style module
paths, certification tracks, activation code, and generator functions remain
unchanged. Four previously invalid non-movement references are migrated to their
truthful sources: HTF, Pro Strategy Engine, Ensemble, and metadata-only
`TEST_STRAT`. Existing batch certification tests prove execution-strategy and
fixture dispatch behavior remains unchanged.

Rollback:

1. Revert the Phase 1A commit only.
2. Retain Phase 0 commit `cf2d74bc`.
3. Rerun Phase 0 inventory tests and the pre-existing baseline comparison.

Rollout:

1. Review the exact mapping matrix and non-movement allowlist.
2. Run focused integrity and candidate behavior tests.
3. Run the full suite and compare the sole failure to baseline `691b8a75`.
4. Merge without runtime quarantine enforcement.
5. Address profile integrity in separately scoped work.

New config metadata: `runtime_strategy_id` for every inventory entry and the
`VWAP_RECLAIM` alias. No environment variables or runtime flags were added.

## Explicit non-claims

- No strategy threshold, score, setup sequence, or parameter was changed.
- No strategy was promoted, dequarantined, or made execution-eligible.
- No runtime activation, candidate count, candidate ordering, ranking, Phase 2,
  option-confirmation policy, or no-trade decision policy was changed.
- No feed, broker, risk, order, execution, credential, live, paper, or dashboard
  path was changed.
- No pattern conformance, predictive edge, option translation, after-cost edge,
  profitability, paper readiness, production readiness, or live readiness is
  proven.

## Safety evidence

```text
mode: OFFLINE
candidate_id: STRATEGY_TRUTH_PHASE1A_REGISTRY_INTEGRITY
message_decision: STRATEGY_REGISTRY_REFERENCES_VALIDATED
decision: PHASE1A_PASS_WITH_PREEXISTING_TEST_FAILURE
reason: All registry modules and declared callables validate, twelve inventory-managed movement references reconcile, and activation, outputs, quarantine enforcement, and execution authority remain unchanged; the sole full-suite failure is reproduced on the untouched baseline.
timestamp: 2026-07-14T15:49:28+05:30
source: docs/agent_reviews/strategy_truth_phase1a_registry_integrity.md
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
append: false
```
