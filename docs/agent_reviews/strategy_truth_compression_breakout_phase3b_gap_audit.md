# Strategy Truth Phase 3B Gap Audit: `compression_breakout_v1`

## Scope

- Worktree: `/Users/madhuram/tradebot-compression-breakout-phase3b-closure`
- Branch: `fix/compression-breakout-phase3b-closure`
- Starting head: `7a0cd00586eac9375fee717de69f14a377fc1da7`
- Accepted ancestry: `PROVEN`
- Accepted ancestry evidence: `7a0cd005...` descends from the accepted Trend Pullback closure line and contains the accepted Phase 3B harness, restart, and PR 657/658 ancestry.

## Required evidence classification

| requirement | status | evidence |
| --- | --- | --- |
| canonical strategy identifier | PROVEN | `compression_breakout_v1` in `strategies/strategy_registry.py` and `strategies/movement/compression_breakout.py` |
| registry entry | PROVEN | registry maps `COMPRESSION_BREAKOUT -> strategies/movement/compression_breakout.py -> generate_compression_breakout_candidates` |
| production callable | PROVEN | `generate_compression_breakout_candidates(ctx, regime)` |
| production callers | PROVEN | `core.orchestrator -> core.runtime_snapshot_producer -> core.ranking_orchestrator -> core.candidate_pool_orchestrator -> generate_compression_breakout_candidates`; replay and report paths reuse the same ranking/candidate-pool chain |
| shared `StrategyContext` fields | PROVEN for `spot_ltp`, `vwap`, `atr_short`, `atr_long`; PARTIALLY_PROVEN for `range_width_pct`; UNPROVEN for `nearest_support` / `nearest_resistance` as canonical runtime sources | runtime adapter and market-data path carry ATR and core price fields; `range_width_pct` still has a missing-source marker in the canonical snapshot path |
| history producer | PROVEN | `core.session_bar_history` and `core.market_data` already produce completed session history and session ATR state |
| indicator inputs | PROVEN | compression generator consumes `spot_ltp`, `vwap`, `range_width_pct`, `atr_short`, `atr_long`, and breakout anchors |
| candidate fingerprint | PROVEN | direct complete-context fingerprint remains `compression_breakout_v1 / 0.470676 / BUY_CALL / VALIDATED_CANDIDATE` |
| candidate-pool path | PROVEN | shared pool carries the raw compression candidate into ranking without mutating setup identity |
| Phase 2 path | PROVEN | the candidate remains advisory/raw; downstream option confirmation remains separate |
| ranking path | PROVEN | `build_ranked_opportunity_report(...)` preserves the same candidate identity and routes it through ranking without changing setup formulae |
| runtime snapshot path | PARTIALLY_PROVEN | the runtime adapter path preserves the strategy context, but the canonical runtime payload still lacks `range_width_pct`, so the compression candidate is blocked in the actual runtime path |
| publication / owner path | NOT_APPLICABLE | no dedicated durable owner or outbox exists for `compression_breakout_v1` in this branch |
| outbox path | NOT_APPLICABLE | no compression-breakout outbox implementation exists or is required |
| UI / report exposure | PROVEN | ranked report and canonical snapshot code expose the candidate path without changing the candidate contract |
| existing direct / runtime / temporal tests | PROVEN | direct strategy tests, runtime context tests, ATR tests, and the accepted temporal harness remain in place |
| existing audit docs | PROVEN | Phase 2A runtime-context audit, Phase 3A2 ATR contract, and Phase 3B temporal harness docs already cover the surrounding chain |

## Call graph

1. `core.orchestrator._strategy_context_snapshot_metadata(...)`
2. `core.runtime_snapshot_producer._strategy_context_from_market_symbol(...)`
3. `core.ranking_orchestrator.build_ranked_opportunity_report(...)`
4. `core.candidate_pool_orchestrator.build_candidate_pool_report(...)`
5. `strategies.movement.compression_breakout.generate_compression_breakout_candidates(...)`

## Runtime versus direct proof

- Direct complete-context fingerprint:
  - `compression_breakout_v1`
  - `0.470676`
  - `BUY_CALL`
  - `VALIDATED_CANDIDATE`
- Runtime path with canonical missing `range_width_pct`:
  - the runtime adapter preserves `spot_ltp`, `vwap`, `atr_short`, `atr_long`, ORB anchors, and option evidence
  - the orchestrator metadata marks `range_width_pct` as `MISSING_SOURCE`
  - the compression generator returns no candidate
- Runtime path with truthful `range_width_pct` injected:
  - the same runtime adapter and ranking path reproduce the direct fingerprint exactly
  - no score, status, or direction drift is observed

## Remaining gap

The remaining gap is not formula drift. It is the missing canonical runtime source for `range_width_pct` in the current snapshot chain. The generator is already correct when the field is truthfully supplied; today’s runtime path still blocks because the canonical snapshot path does not provide that source.

## Controls

Two unrelated controls stayed stable during the audit:

- ORB stability control: `tests/test_opening_range_retest_runtime_owner_enforcement.py`
- Trend Pullback stability control: `tests/test_trend_pullback_temporal_conformance.py`

Both passed in the focused regression slice and did not change their accepted fingerprints.

## Tests and results

- Focused audit slice:
  - `python -m pytest -q tests/test_compression_breakout_phase3b_gap_audit.py tests/test_opening_range_retest_runtime_owner_enforcement.py tests/test_trend_pullback_temporal_conformance.py tests/test_strategy_context_truth.py tests/test_compression_trend_movement_strategies.py`
  - result: `27 passed in 22.67s`
- Full repository suite:
  - `python -m pytest -q`
  - result: `1 failed, 6005 passed, 24 deselected, 935 warnings in 983.24s`
  - first failure: `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
  - failure cause: pre-existing unrelated auth baseline (`RuntimeError: [AUTH] missing_kite_access_token`)

## Verified runtime path

- `range_width_pct` currently has a `MISSING_SOURCE` provenance marker in the canonical orchestrator metadata.
- `atr_short` and `atr_long` are already authoritative and survive the runtime adapter.
- `nearest_support` / `nearest_resistance` remain optional breakout anchors; compression can fall back to ORB or day levels when they are absent.
- The only repository-wide failure observed in this checkpoint is the known orchestrator auth path, not a compression-breakout regression.

## Explicit non-claims

- No claim of profitability, edge, or production readiness.
- No strategy formula, threshold, ranking weight, or owner/outbox change.
- No claim that the canonical runtime source gap has been repaired in this branch.
- No claim that compressed runtime emission is available today without a truthful `range_width_pct` source.
