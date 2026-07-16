# Strategy Truth Phase 3B Gap Audit: `trend_pullback_v1`

## Scope

- Worktree: `/Users/madhuram/tradebot-trend-pullback-phase3b-closure`
- Branch: `fix/trend-pullback-phase3b-closure`
- Starting head: `66ba99256006d1681a07b8e2689769d7d053635a`
- Accepted temporal base in ancestry: `10f0c0d20e99f3ca84d84578276f43dd2e971a98`
- Accepted temporal worktree remains clean: `/Users/madhuram/tradebot-trend-pullback-temporal`

## Required evidence classification

| requirement | status | evidence |
| --- | --- | --- |
| canonical strategy identifier | PROVEN | `trend_pullback_v1` in `strategies/strategy_registry.py` and `strategies/movement/trend_pullback.py` |
| registration path | PROVEN | registry entry maps `TREND_PULLBACK -> strategies/movement/trend_pullback.py -> generate_trend_pullback_candidates` |
| production callable | PROVEN | `generate_trend_pullback_candidates(ctx, regime)` |
| all production callers | PROVEN | `core.orchestrator.produce_and_store_runtime_snapshots -> core.runtime_snapshot_producer._build_and_write_canonical_ranked_snapshot -> core.ranking_orchestrator.build_ranked_opportunity_report -> core.candidate_pool_orchestrator.build_candidate_pool_report -> generate_trend_pullback_candidates`; replay path also routes through `core.replay_candidate_handoff_entrypoint` |
| history requirements | PROVEN | causal completed-bar history is required; validator rejects missing / malformed / mixed-session / unordered history |
| indicator inputs | PROVEN | `spot_ltp`, `vwap`, `nearest_support`, `nearest_resistance`, completed 1m history, regime trend scores |
| temporal contract | PROVEN | trend-establishment, controlled pullback, continuation trigger, expiry timestamp, fail-closed invalidation |
| candidate fingerprint | PROVEN | direct generator fingerprint remains `trend_pullback_v1 / 0.648584 / BUY_CALL / RAW_CANDIDATE` and runtime-enriched pool fingerprint remains stable |
| candidate-pool path | PROVEN | generic candidate pool routes trend pullback through the shared read-only pool |
| ranking path | PROVEN | ranked report composes the candidate pool without mutating the trend-pullback candidate contract |
| runtime caller | PROVEN | `_build_and_write_canonical_ranked_snapshot` passes a `StrategyContext` carrying completed-bar history into the real ranked report path; the captured runtime report candidate matches the direct generator when evaluated on the report-classified regime |
| owner/publication path | NOT_APPLICABLE | trend pullback has no dedicated durable owner/outbox implementation in this branch; only ORB owns that boundary |
| outbox path | NOT_APPLICABLE | no trend-pullback outbox exists or is required for this strategy |
| existing tests | PROVEN | temporal semantics, harness, context truth, and phase-2 ownership tests already cover the direct strategy and downstream contract |
| accepted prior evidence | PROVEN | accepted temporal repair and temporal harness work remain in ancestry and unchanged |
| remaining gaps | NONE | the only missing proof was direct runtime-caller propagation; it is now covered by a focused test |
| proposed smallest repair | COMPLETED | add one focused runtime-propagation test and document the audit result; no production strategy logic change required |
| prohibited scope | PROVEN respected | no formulas, thresholds, ranking weights, broker, execution, or owner-authority code were changed |

## Call graph

1. `core.orchestrator.produce_and_store_runtime_snapshots`
2. `core.runtime_snapshot_producer._build_and_write_canonical_ranked_snapshot`
3. `core.ranking_orchestrator.build_ranked_opportunity_report`
4. `core.candidate_pool_orchestrator.build_candidate_pool_report`
5. `strategies.movement.trend_pullback.generate_trend_pullback_candidates`

Replay support also reaches the same ranked-report path through `core.replay_candidate_handoff_entrypoint`.

## Temporal contract summary

- `completed_bar_history` is first-class temporal evidence.
- The strategy consumes the last four completed bars.
- Missing or malformed history emits deterministic `STRATEGY_EVIDENCE_BLOCKED`.
- The strategy no longer depends on `previous_completed_close` alone.
- The accepted direct setup fingerprint remains unchanged when truthful history is present.

## Remaining-owner analysis

Trend pullback is a candidate generator, not a durable publication owner.

- `owner/publication path`: not applicable to this strategy in this branch.
- `outbox path`: not applicable.
- The only durable owner boundary in the branch is ORB-specific and remains separate.

## Existing proof sources

- `tests/test_trend_pullback_temporal_semantics.py`
- `tests/test_trend_pullback_temporal_conformance.py`
- `tests/test_strategy_context_truth.py`
- `tests/test_candidate_phase2_ownership.py`
- `tests/test_candidate_phase2_semantic_ownership.py`

## Proposed smallest repair

Add one runtime-caller proof test that:

- exercises the real runtime snapshot producer path,
- confirms `completed_bar_history` survives into the `StrategyContext` passed to `build_ranked_opportunity_report`,
- confirms the emitted trend-pullback candidate is still the accepted one,
- and leaves the strategy formula, thresholds, and other movement strategies untouched.

## Prohibited scope

- no strategy formula changes
- no threshold changes
- no ranking changes
- no owner-service implementation
- no outbox implementation
- no broker/execution/risk/feed changes

## Final classification target

The branch lands as `RIGHT` because the runtime-caller proof passed and no other Trend Pullback gap remains.

## Verification results

- Focused runtime-propagation proof: `3 passed in 2.12s`
- Adjacent Trend Pullback/runtime/regression slice: `91 passed in 13.41s`
- Full repository suite: `1 failed, 6003 passed, 24 deselected in 1280.20s`
- Full-suite failure is the known unrelated auth baseline:
  - `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
  - `RuntimeError: [AUTH] missing_kite_access_token`

## Runtime fingerprint observed in the proof payload

- `trend_pullback_v1`
- `BUY_CALL`
- `VALIDATED_CANDIDATE`
- `raw_score=0.597560`
- `entry_trigger=trend_pullback_hold_resume`
- `invalid_if=pullback_breaks_anchor`
- `rank_reason=established trend resumed after a controlled pullback`

The direct generator on the captured runtime report regime matched the same candidate identity and setup evidence, while the accepted direct temporal fingerprint remains unchanged in the existing direct-context tests.
