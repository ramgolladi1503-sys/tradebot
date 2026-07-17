# Strategy Truth Phase 3B Gap Audit: `vwap_reclaim_v1`

IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Recover the real `vwap_reclaim_v1` implementation contract, prove the runtime and direct generator paths agree, and close the evidence gap without changing production strategy logic, thresholds, or formulas.

WHAT WAS ACTUALLY IMPLEMENTED:
- Added a dedicated audit-only test file at [`tests/test_vwap_reclaim_temporal_conformance.py`](../../tests/test_vwap_reclaim_temporal_conformance.py).
- Recovered the production callable, runtime caller chain, VWAP producer, and Phase 2 boundary behavior from the real repository code.
- Proved the direct generator and runtime-propagated context produce the same VWAP-reclaim fingerprint for the same truthful snapshot.
- Proved the current strategy contract is snapshot-confirmation driven and does not consume completed-bar history as a causal reclaim sequence.

RUNTIME ARCHITECTURE CHANGE:
NONE

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

## Repository Identity

- Worktree: `/Users/madhuram/tradebot-vwap-reclaim-phase3b-closure`
- Branch: `fix/vwap-reclaim-phase3b-closure`
- Starting head: `ff321bfee70e5667fde98dd05b431dd18999d201`
- Production callable head under audit: `ff321bfee70e5667fde98dd05b431dd18999d201`

## Classification Matrix

| requirement | status | evidence |
| --- | --- | --- |
| canonical strategy identifier | PROVEN | `STRATEGY_ID = "vwap_reclaim_rejection_v1"` in [`strategies/movement/vwap_reclaim.py`](../../strategies/movement/vwap_reclaim.py#L29-L30) |
| registry path | PROVEN | [`strategies/strategy_registry.py`](../../strategies/strategy_registry.py#L158-L163) maps `VWAP_RECLAIM` to `generate_vwap_reclaim_rejection_candidates` |
| production callable | PROVEN | [`generate_vwap_reclaim_rejection_candidates`](../../strategies/movement/vwap_reclaim.py#L39-L97) |
| all production callers | PROVEN | [`core.candidate_pool_orchestrator`](../../core/candidate_pool_orchestrator.py#L84-L178), [`core.ranking_orchestrator`](../../core/ranking_orchestrator.py#L151-L170), [`core.runtime_snapshot_producer`](../../core/runtime_snapshot_producer.py#L402-L415), [`core.replay_candidate_handoff_entrypoint`](../../core/replay_candidate_handoff_entrypoint.py#L651-L657) |
| authoritative runtime caller | PROVEN | runtime snapshot producer builds `StrategyContext`, then calls ranked opportunity reporting, which calls the candidate pool and generator |
| VWAP formula | PROVEN | `compute_indicators()` uses typical price `(high + low + close) / 3` and volume-weighting over the configured window; the replay engine calls the same helper |
| VWAP producer | PROVEN | [`core/indicators_live.py`](../../core/indicators_live.py#L9-L46), runtime binding in [`core/market_data.py`](../../core/market_data.py#L2811-L2820), and replay usage in [`core/replay_engine.py`](../../core/replay_engine.py#L661-L671) |
| VWAP provenance | PROVEN | runtime context carries `strategy_context_truth` and `strategy_context_provenance` through [`core/runtime_snapshot_producer.py`](../../core/runtime_snapshot_producer.py#L85-L142) |
| volume contract | PROVEN | zero or missing volume falls back to unit weight in `compute_indicators()`; zero-volume proof exists in [`tests/core/test_canonical_strategy_input_truth.py`](../../tests/core/test_canonical_strategy_input_truth.py#L220-L234) |
| price contract | PROVEN | VWAP is anchored to OHLC typical price, not close-only |
| bar interval | PROVEN | runtime consumes completed 1m bars from `ohlc_buffer.get_completed_bars(...)` before indicator evaluation |
| history requirements | UNPROVEN | the generator does not consume `completed_bar_history`; history is not part of the current emission contract |
| temporal sequence | UNPROVEN | no causal multi-step reclaim sequence is implemented; the current contract is snapshot-confirmation driven |
| candidate identity | PROVEN | direct generator emits a deterministic `RAW_CANDIDATE` fingerprint for the truthful snapshot |
| candidate-pool path | PROVEN | pool layer accepts the candidate and enriches it through the existing Phase 2 path |
| Phase 2 transformations | PROVEN | [`core/option_confirmation.py`](../../core/option_confirmation.py#L220-L262) adds option confirmation, liquidity, freshness, and can change status to `VALIDATED_CANDIDATE` |
| ranking transformations | PROVEN | ranked opportunity reporting consumes the candidate pool and produces a downstream ranking score without changing generator formulas |
| runtime snapshot exposure | PROVEN | [`core.orchestrator.py`](../../core/orchestrator.py#L1565-L1576) copies `previous_spot_ltp` into metadata; [`core/runtime_snapshot_producer.py`](../../core/runtime_snapshot_producer.py#L85-L142) propagates the truth payload into `StrategyContext` |
| owner/publication contract | NOT_APPLICABLE | no durable owner/outbox publication model exists for this strategy in the current branch |
| outbox contract | NOT_APPLICABLE | not present for this strategy |
| existing tests | PROVEN | [`tests/test_vwap_trap_movement_strategies.py`](../../tests/test_vwap_trap_movement_strategies.py#L60-L120), [`tests/test_strategy_generators_lineage.py`](../../tests/test_strategy_generators_lineage.py#L71-L82), [`tests/test_strategy_missing_evidence_observability.py`](../../tests/test_strategy_missing_evidence_observability.py#L254-L410), [`tests/test_strategy_missing_evidence_policy.py`](../../tests/test_strategy_missing_evidence_policy.py#L364-L445), [`tests/test_strategy_context_truth.py`](../../tests/test_strategy_context_truth.py#L171-L214), new [`tests/test_vwap_reclaim_temporal_conformance.py`](../../tests/test_vwap_reclaim_temporal_conformance.py) |
| accepted prior evidence | PROVEN | prior Phase 2A/2C evidence already established truthful runtime propagation and Phase 2 boundary behavior |
| remaining gaps | UNPROVEN | the strategy still lacks a causal completed-bar reclaim sequence; only snapshot confirmation is proven |

## Production Call Chain

1. `core.orchestrator.py` stores `previous_spot_ltp` in snapshot metadata with provenance.
2. `core.runtime_snapshot_producer._strategy_context_from_market_symbol()` copies runtime truth into `StrategyContext`.
3. `core.runtime_snapshot_producer.build_ranked_opportunity_report()` invokes ranked opportunity reporting.
4. `core.ranking_orchestrator.build_ranked_opportunity_report()` invokes `core.candidate_pool_orchestrator.build_candidate_pool_report()`.
5. `core.candidate_pool_orchestrator.build_candidate_pool_report()` iterates the default generator list, which includes `generate_vwap_reclaim_rejection_candidates()`.
6. `core.option_confirmation.enrich_candidate_with_option_confirmation()` adds downstream-owned option truth and can promote the candidate to `VALIDATED_CANDIDATE`.

## VWAP Contract

1. **What price is used?** Typical price.
2. **Formula basis?** `((high + low + close) / 3) * volume`, divided by volume sum over the window.
3. **Is volume mandatory?** For the indicator path, volume is used; missing/zero volume falls back to unit weight rather than fabricating a different price.
4. **Authoritative volume source?** Completed candle volume from the indicator input.
5. **What happens when volume is zero?** Unit-volume fallback is used.
6. **What happens when volume is missing?** The indicator path treats missing volume as `1`.
7. **Are synthetic or fallback volumes allowed?** Yes, in the indicator contract as implemented; they are explicit fallback behavior, not silent mutation.
8. **Session-reset or rolling?** Rolling over the completed-bar window in the runtime/replay helper; the offline vectorized proxy is separately daily anchored and not canonical for this audit.
9. **What session boundary applies?** Day/session grouping in the indicator path.
10. **What bar interval applies?** 1 minute in the runtime completed-bar path.
11. **Are forming bars included?** No, the runtime path uses completed bars.
12. **Is VWAP calculated by market data or accepted from the broker?** Calculated by the repository indicator pipeline and then bound into `StrategyContext`.
13. **Does runtime and replay use the same formula?** Yes for the runtime producer and replay engine (`compute_indicators()`); no for the offline `vectorized_signals` proxy, which is a separate research helper.
14. **Is `StrategyContext.vwap` independently provenance-checked?** Yes, provenance is carried alongside truth in the runtime snapshot path.
15. **Can stale or cross-session VWAP enter the strategy?** The strategy does not revalidate provenance itself; the runtime path is the truth source, so stale/cross-session protection depends on upstream truth handling rather than the generator.

## Reclaim Sequence

The current callable name suggests reclaim/rejection behavior, but the implementation proves a much narrower contract:

- It requires `spot_ltp` and `vwap`.
- It requires the signed spot-vs-VWAP distance to fall inside the configured band.
- It requires either explicit metadata confirmation or a previous spot cross through VWAP.
- It uses `vwap_slope` and `volume_z` as score inputs, not as temporal gating evidence.
- It does **not** consume completed-bar history or a multi-step causal reclaim sequence.

That means the observed contract is **snapshot confirmation**, not a causal completed-bar reclaim sequence.

## Candidate Identity

### Direct generator fingerprint

Truthful snapshot:

```text
('vwap_reclaim_rejection_v1', 0.392377, 'BUY_CALL', 'RAW_CANDIDATE', 'confirmed_vwap_reclaim_or_rejection', 'price_crosses_back_through_vwap', 'confirmed VWAP reclaim/rejection in a non-chop regime')
```

### Runtime-propagated fingerprint

The runtime-propagated context built by `_strategy_context_from_market_symbol()` produces the same fingerprint for the same truthful inputs.

### Candidate-pool / ranking transformation

When the generator is isolated inside the candidate pool:

```text
pool candidate_count=1
pool candidate status=VALIDATED_CANDIDATE
pool raw_score=0.392377
ranked top strategy=vwap_reclaim_rejection_v1
ranked top score=0.35
```

That status change and score change are downstream transformations. They do not change generator-owned thesis truth.

## Temporal Classification

**CURRENT CLASSIFICATION:** `TIME_GATED_SNAPSHOT`

The current implementation is not a multi-step causal temporal reclaim engine. It is a snapshot-confirmation strategy with previous-spot cross evidence and optional explicit confirmation metadata.

## Existing Tests

The following tests already prove the relevant boundaries:

- `tests/test_vwap_trap_movement_strategies.py` proves the generator emits for the confirmed reclaim/rejection snapshot and fails closed without confirmation.
- `tests/test_strategy_generators_lineage.py` proves the VWAP reclaim generator preserves lineage and advisory-only ownership.
- `tests/test_strategy_missing_evidence_observability.py` and `tests/test_strategy_missing_evidence_policy.py` prove missing VWAP remains missing and optional slope evidence does not create a false positive.
- `tests/test_strategy_context_truth.py` proves runtime truth propagation for VWAP and `previous_spot_ltp`.
- `tests/test_vwap_reclaim_temporal_conformance.py` adds the missing audit-only proof that runtime and direct fingerprints match and that completed history does not alter the current contract.

## Remaining Gaps

- No completed-bar causal reclaim sequence exists in the current implementation.
- The strategy does not consume `completed_bar_history`.
- The strategy is therefore not temporally conformant in the strict causal-sequence sense; it is only snapshot-confirmation conformant.

## Smallest Proposed Repair

If the intent is a true causal reclaim sequence, the smallest compatible repair is to add an explicit completed-bar history contract for this strategy and make the generator fail closed unless the ordered reclaim sequence is present in that history. That repair is not part of this task.

## Prohibited Scope

Not touched:

- strategy formulas
- thresholds
- execution
- broker integration
- ranking policy
- no-trade policy
- live feed behavior
- owner/publication integration
- profitability validation
- historical validation
