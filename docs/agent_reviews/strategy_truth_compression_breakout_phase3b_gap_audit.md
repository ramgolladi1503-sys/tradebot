# Strategy Truth Phase 3B Gap Audit: `compression_breakout_v1`

## Scope

- Worktree: `/Users/madhuram/tradebot-compression-breakout-phase3b-closure`
- Branch: `fix/compression-breakout-phase3b-closure`
- Starting head: `194b9c273ae0dd3fd903c61b6bf45afbd0a7477c`
- Final implementation head before evidence commit: `194b9c273ae0dd3fd903c61b6bf45afbd0a7477c`
- Accepted ancestry: `PROVEN`
- Accepted ancestry evidence: the branch descends from the accepted Trend Pullback closure line and retains the accepted Phase 3B harness, restart, and PR 657/658 ancestry.

## Canonical `range_width_pct` contract

| field | value |
| --- | --- |
| recovered formula | `(session_day_high - session_day_low) / current_close_proxy` |
| numerator | session-day high minus session-day low from completed bars only |
| denominator | current close proxy from the same snapshot, represented by live `ltp` in the runtime producer and `close` in replay / offline proxies |
| unit | fraction |
| bar interval | `1m` |
| compression window | completed session-to-date one-minute bars only |
| session contract | same `session_date`, Asia/Kolkata session boundaries, completed bars only |
| symbol contract | same symbol only; no cross-symbol mixing |
| cutoff timestamp | current cycle cutoff / prefix cutoff |
| forming-bar rule | ignore any bar whose end extends past cutoff; future bars do not contribute |
| duplicate policy | fail closed for canonical `range_width_pct` production |
| missing / malformed policy | fail closed for canonical `range_width_pct` production |
| authoritative producer | `core.market_data.fetch_live_market_data` via `core.session_bar_history.calculate_session_range_width_pct_from_completed_history` |
| provenance states | `TRUTHFUL`, `MISSING_SOURCE`, `INCOMPLETE` |
| runtime propagation path | `core.market_data.fetch_live_market_data -> core.orchestrator._strategy_context_snapshot_metadata -> core.runtime_snapshot_producer._strategy_context_from_market_symbol -> core.ranking_orchestrator.build_ranked_opportunity_report -> strategies.movement.compression_breakout.generate_compression_breakout_candidates` |
| replay propagation path | completed history / replay payload -> `core.session_bar_history.calculate_session_range_width_pct_from_completed_history` -> `core.runtime_snapshot_producer._strategy_context_from_market_symbol` -> same ranking/candidate path |

## Evidence classification

| requirement | status | evidence |
| --- | --- | --- |
| canonical strategy identifier | PROVEN | `compression_breakout_v1` in `strategies/strategy_registry.py` and `strategies/movement/compression_breakout.py` |
| registry entry | PROVEN | registry maps `COMPRESSION_BREAKOUT -> strategies/movement/compression_breakout.py -> generate_compression_breakout_candidates` |
| production callable | PROVEN | `generate_compression_breakout_candidates(ctx, regime)` |
| production callers | PROVEN | `core.orchestrator -> core.runtime_snapshot_producer -> core.ranking_orchestrator -> core.candidate_pool_orchestrator -> generate_compression_breakout_candidates`; replay and report paths reuse the same ranking/candidate-pool chain |
| shared `StrategyContext` fields | PROVEN for `spot_ltp`, `vwap`, `atr_short`, `atr_long`, and `range_width_pct`; UNPROVEN for `nearest_support` / `nearest_resistance` as canonical runtime sources | runtime adapter and market-data path carry ATR and core price fields; `range_width_pct` now has a canonical runtime source and provenance |
| history producer | PROVEN | `core.session_bar_history` and `core.market_data` already produce completed session history and session ATR state |
| indicator inputs | PROVEN | compression generator consumes `spot_ltp`, `vwap`, `range_width_pct`, `atr_short`, `atr_long`, and breakout anchors |
| candidate fingerprint | PROVEN | direct complete-context fingerprint remains `compression_breakout_v1 / 0.470676 / BUY_CALL / VALIDATED_CANDIDATE` |
| candidate-pool path | PROVEN | shared pool carries the raw compression candidate into ranking without mutating setup identity |
| Phase 2 path | PROVEN | the candidate remains advisory/raw; downstream option confirmation remains separate |
| ranking path | PROVEN | `build_ranked_opportunity_report(...)` preserves the same candidate identity and routes it through ranking without changing setup formulae |
| runtime snapshot path | PROVEN | the runtime adapter now propagates canonical `range_width_pct` from completed-bar history |
| publication / owner path | NOT_APPLICABLE | no dedicated durable owner or outbox exists for `compression_breakout_v1` in this branch |
| outbox path | NOT_APPLICABLE | no compression-breakout outbox implementation exists or is required |
| UI / report exposure | PROVEN | ranked report and canonical snapshot code expose the candidate path without changing the candidate contract |
| existing direct / runtime / temporal tests | PROVEN | direct strategy tests, runtime context tests, ATR tests, and the accepted temporal harness remain in place |
| existing audit docs | PROVEN | Phase 2A runtime-context audit, Phase 3A2 ATR contract, and Phase 3B temporal harness docs already cover the surrounding chain |

## Runtime versus direct proof

- Direct complete-context fingerprint:
  - `compression_breakout_v1`
  - `0.470676`
  - `BUY_CALL`
  - `VALIDATED_CANDIDATE`
- Runtime path with canonical completed history:
  - the runtime adapter preserves `spot_ltp`, `vwap`, `atr_short`, `atr_long`, ORB anchors, and option evidence
  - the canonical runtime producer now fills `range_width_pct` from completed-bar history
  - the compression generator reproduces the direct fingerprint exactly
- Runtime path with malformed or cross-symbol history:
  - the canonical `range_width_pct` helper returns `None`
  - provenance records `MISSING_SOURCE`
  - the producer does not fabricate a substitute value

## Controls

Two unrelated controls stayed stable during the audit:

- ORB stability control: `tests/test_opening_range_retest_runtime_owner_enforcement.py`
- Trend Pullback stability control: `tests/test_trend_pullback_temporal_conformance.py`

Both passed in the focused regression slice and did not change their accepted fingerprints.

## Files changed

- `core/session_bar_history.py`
- `core/market_data.py`
- `core/orchestrator.py`
- `tests/test_compression_breakout_range_width_runtime_contract.py`
- `tests/test_atr_contract_decision.py`
- `runtime/strategy_validation/regime_timeline.jsonl` was touched by test execution and must be clean before commit

## Tests and results

- Focused canonical-range-width slice:
  - `python -m pytest -q tests/test_compression_breakout_range_width_runtime_contract.py tests/test_compression_breakout_phase3b_gap_audit.py tests/test_opening_range_retest_runtime_owner_enforcement.py tests/test_trend_pullback_temporal_conformance.py`
  - result: `17 passed, 1 warning in 11.30s`
- Focused contract / owner slice:
  - `python -m pytest -q tests/test_strategy_context_truth.py tests/test_compression_trend_movement_strategies.py tests/test_candidate_phase2_ownership.py tests/test_candidate_phase2_semantic_ownership.py`
  - result: `48 passed, 1 warning in 25.37s`
- ATR contract slice:
  - `python -m pytest -q tests/test_atr_contract_decision.py`
  - result: `37 passed, 1 warning in 4.48s`
- Full repository suite:
  - `python -m pytest -q`
  - result: `1 failed, 6014 passed, 24 deselected, 935 warnings in 754.67s`
  - first failure: `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
  - failure cause: pre-existing unrelated auth baseline (`RuntimeError: [AUTH] missing_kite_access_token`)

## Baseline comparison

- The accepted direct fingerprint is unchanged.
- The runtime producer now computes `range_width_pct` from completed-bar history instead of leaving a missing-source gap.
- The full suite still contains one known unrelated auth failure and no compression-breakout regression.

## Explicit non-claims

- No claim of profitability, edge, or production readiness.
- No strategy formula, threshold, ranking weight, or owner/outbox change.
- No claim that the branch was pushed.
- No claim that historical validation, execution readiness, or live readiness has been proven.
