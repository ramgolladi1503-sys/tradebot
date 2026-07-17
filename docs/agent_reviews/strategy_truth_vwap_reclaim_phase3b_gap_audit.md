# Strategy Truth Phase 3B Closure: `vwap_reclaim_rejection_v1`

IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Convert `vwap_reclaim_rejection_v1` from a snapshot-confirmation strategy into a causal completed-bar reclaim/rejection implementation using `completed_bar_history`, while preserving strategy thresholds, formulas, directionality, and Phase 2 ownership boundaries.

WHAT WAS ACTUALLY IMPLEMENTED:
- Rewrote [`strategies/movement/vwap_reclaim.py`](../../strategies/movement/vwap_reclaim.py) to treat `completed_bar_history` as first-class temporal evidence.
- Added deterministic validation for missing, malformed, out-of-order, mixed-symbol, mixed-session, or inconsistent completed-bar data.
- Computed per-prefix causal VWAP from completed bars only, with explicit `VWAP_AUTHORITATIVE` versus `VWAP_UNIT_WEIGHT_PROXY` provenance.
- Corrected sequence-level provenance emission so any zero/missing-volume bar in the validated causal prefix upgrades the reported VWAP provenance to `VWAP_UNIT_WEIGHT_PROXY` instead of inheriting only the final bar's provenance.
- Required the final 3 completed bars to satisfy the ordered establishment → reclaim → hold sequence before a candidate can emit.
- Added a runtime conformance proof that `StrategyContext.vwap` resolves to the causal VWAP from completed bars and not the final close of the last bar.
- Preserved the existing candidate identity, raw-candidate ownership, trigger text, invalidation text, and downstream ownership split.
- Added shared causal-history fixtures and updated the temporal, lineage, observability, policy, and semantic-ownership tests to exercise the repaired contract.

ARCHITECTURE CHANGE:
NECESSARY_MINIMAL

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

## Repository Identity

- Worktree: `/Users/madhuram/tradebot-vwap-reclaim-phase3b-closure`
- Branch: `fix/vwap-reclaim-phase3b-closure`
- Starting head: `3e21821b211cedff8c1f8c26e8e4d4e88c360be5`
- Implementation commit: `526bce2c`
- First evidence commit: `8f2b79f8`
- Aggregate-provenance follow-up commit: `eb3725794cd8216e0d0b1611b4f526dfa53057ef`
- Latest documentation commit / final head before this update: `a4264fe91a36cdb13765a900db5ae9f5f3b69a42`

## Files Changed

- [`strategies/movement/vwap_reclaim.py`](../../strategies/movement/vwap_reclaim.py)
- [`tests/vwap_reclaim_test_support.py`](../../tests/vwap_reclaim_test_support.py)
- [`tests/test_vwap_reclaim_temporal_conformance.py`](../../tests/test_vwap_reclaim_temporal_conformance.py)
- [`tests/test_vwap_trap_movement_strategies.py`](../../tests/test_vwap_trap_movement_strategies.py)
- [`tests/test_strategy_generators_lineage.py`](../../tests/test_strategy_generators_lineage.py)
- [`tests/test_strategy_missing_evidence_observability.py`](../../tests/test_strategy_missing_evidence_observability.py)
- [`tests/test_strategy_missing_evidence_policy.py`](../../tests/test_strategy_missing_evidence_policy.py)
- [`tests/test_candidate_phase2_semantic_ownership.py`](../../tests/test_candidate_phase2_semantic_ownership.py)
- [`tests/test_vwap_reclaim_runtime_conformance.py`](../../tests/test_vwap_reclaim_runtime_conformance.py)
- [`docs/agent_reviews/strategy_truth_vwap_reclaim_phase3b_gap_audit.md`](./strategy_truth_vwap_reclaim_phase3b_gap_audit.md)

## Causal Contract

The repaired runtime contract is:

1. `completed_bar_history` must be present and structurally valid.
2. Bars must be completed 1-minute bars with ordered timestamps and matching symbol/session identity.
3. A candidate can only emit when the final completed prefix forms the ordered sequence:
   - establishment
   - reclaim
   - hold
4. `ctx.vwap` must match the final causal VWAP from the validated completed-bar prefix.
5. Missing or inconsistent history blocks the strategy and emits a deterministic blocked event.

## Complete Evidence Matrix

| item | result | evidence |
| --- | --- | --- |
| production callable | PROVEN | `generate_vwap_reclaim_rejection_candidates()` still owns the strategy entrypoint |
| completed history contract | PROVEN | `completed_bar_history` is required for the causal path |
| causal sequencing | PROVEN | final 3 completed bars must satisfy establishment → reclaim → hold |
| runtime/direct agreement | PROVEN | direct and runtime-propagated contexts produce the same fingerprint |
| runtime VWAP truth | PROVEN | `_strategy_context_from_market_symbol()` carries canonical VWAP into `StrategyContext.vwap`; no OHLC-close substitution is used |
| runtime path split | PROVEN | canonical ranked snapshots run through `build_ranked_opportunity_report`; live Phase 2 top-opportunity exposure remains downstream-owned through `cycle_ranked_candidates` |
| missing history | PROVEN | `STRATEGY_EVIDENCE_BLOCKED` is emitted for missing temporal evidence |
| malformed history | PROVEN | invalid or inconsistent history is blocked deterministically |
| future mutation safety | PROVEN | future bars after the cutoff do not change the candidate identity |
| truncation equivalence | PROVEN | physical truncation at the decision prefix matches the full dataset before the cutoff |
| bearish causal path | PROVEN | a valid bearish sequence emits `BUY_PUT`; the bearish lineage pre-existed the causal repair |
| previous-spot fallback | PROVEN | `previous_spot_ltp` is supplemental only and cannot fabricate the sequence |
| aggregate provenance | PROVEN | any zero/missing-volume bar in the causal prefix emits `VWAP_UNIT_WEIGHT_PROXY` |
| metadata-only confirmation | PROVEN | metadata does not override the completed-bar truth |
| raw ownership | PROVEN | emitted candidates remain `RAW_CANDIDATE` |
| downstream ownership | PROVEN | Phase 2 truth remains outside the generator contract |

## Direct And Runtime Fingerprint

The accepted complete causal context now emits the same direct and runtime fingerprint:

```text
('vwap_reclaim_rejection_v1', 0.392377, 'BUY_CALL', 'RAW_CANDIDATE', 'confirmed_vwap_reclaim_or_rejection', 'price_crosses_back_through_vwap', 'confirmed VWAP reclaim/rejection in a non-chop regime')
```

The causal history also supports the bearish path when the spot/VWAP relationship is reversed and the completed prefix is bearish.

## Temporal Behavior

- `completed_bar_history` is authoritative temporal evidence.
- `ts_epoch` is only used as the evaluation cutoff; future bars past the cutoff are ignored.
- The strategy does not rely on `previous_spot_ltp` or metadata confirmation to manufacture a reclaim.
- The strategy blocks when the final causal VWAP does not match the runtime `vwap`.
- VWAP provenance is reported from the validated causal prefix, not only the last bar, so early zero/missing-volume bars keep the proxy provenance visible.

## Blocked Event Shape

Blocked evidence is emitted as deterministic, sorted, loggable proof:

```text
event=STRATEGY_EVIDENCE_BLOCKED
runtime_strategy_id=vwap_reclaim_rejection_v1
missing_fields=...
invalid_fields=...
reason=missing_required_temporal_evidence|invalid_completed_history|inconsistent_causal_vwap
```

## Tests And Results

- Focused VWAP reclaim / adjacent slice:
  - `python -m pytest -q tests/test_vwap_reclaim_temporal_conformance.py tests/test_vwap_reclaim_runtime_conformance.py tests/test_vwap_trap_movement_strategies.py tests/test_strategy_generators_lineage.py tests/test_strategy_missing_evidence_observability.py tests/test_strategy_missing_evidence_policy.py tests/test_candidate_phase2_semantic_ownership.py`
  - Result: `70 passed, 1 warning in 4.49s`
- Full repository suite:
  - `python -m pytest -q`
  - Result: `6030 passed, 1 failed, 24 deselected, 935 warnings in 355.73s`

## First Failure

The remaining full-suite failure is pre-existing and unrelated to this repair:

```text
tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports
RuntimeError: [AUTH] missing_kite_access_token
```

The failure stack is in the orchestrator auth path, not in the VWAP reclaim strategy, completed-bar propagation, or the repaired temporal tests.

## Risks

- The repository still has the known auth gate failure in the full suite.
- The runtime regime timeline log is a generated artifact and can be dirtied by test runs; it was restored after the suite.
- The causal contract is only as strong as the upstream completed-bar history truth.
- Runtime VWAP provenance remains labeled at the provenance layer rather than split into separate authoritative-versus-fallback source fields; the value truth is proven, but label granularity is still a documentation-level limitation.

## Rollback

- Revert commits `526bce2c` and `eb3725794cd8216e0d0b1611b4f526dfa53057ef` to remove the causal VWAP reclaim rewrite, the aggregate-provenance follow-up, and the test fixture updates.

## Explicit Non-Claims

- No profitability claim.
- No production-readiness claim.
- No execution-readiness claim.
- No live-trading claim.
- No claim that Phase 2 ownership was changed.

---

## Upstream Runtime VWAP Producer Verification

IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Prove the upstream runtime VWAP producer chain for `StrategyContext.vwap` using the real market-data producer, not a hand-built fixture.

WHAT WAS ACTUALLY IMPLEMENTED:
- Added [`tests/test_vwap_reclaim_runtime_source_contract.py`](../../tests/test_vwap_reclaim_runtime_source_contract.py) to exercise the real producer chain from `core.market_data.fetch_live_market_data()` through `core.orchestrator._snapshot_symbol_payload()` and `core.runtime_snapshot_producer._strategy_context_from_market_symbol()`.
- Seeded a valid completed 1-minute bar sequence through the production `core.ohlc_buffer.OhlcBuffer.seed_bars()` path so the upstream producer computes VWAP from completed OHLC history.
- Proved that the final completed close differs from the canonical VWAP and that the runtime builder consumes the canonical VWAP rather than falling back to OHLC close.
- Proved that removing the truth VWAP while keeping close present yields `StrategyContext.vwap is None`, and the VWAP reclaim generator fails closed instead of silently substituting close.
- Proved the default candidate pool and ranked pipeline can still execute the repaired VWAP reclaim generator using the produced runtime truth.

ARCHITECTURE CHANGE:
NONE

REQUIRED FIXES COMPLETED:
3
- Verified the upstream producer path emits canonical VWAP from completed-bar history.
- Verified the runtime context builder reads the canonical VWAP truth and not the final OHLC close.
- Verified the ranked pipeline executes the VWAP reclaim generator from produced runtime truth.

REQUIRED FIXES REMAINING:
0

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

## Upstream Producer Chain

| stage | observed behavior | source truth |
| --- | --- | --- |
| completed-bar seed | 35 completed 1-minute bars seeded through `core.ohlc_buffer.OhlcBuffer.seed_bars()` | `core.ohlc_buffer.OhlcBuffer` |
| indicator compute | `core.indicators_live.compute_indicators()` computes VWAP from completed OHLC bars | completed OHLC history |
| market-data row | `core.market_data.fetch_live_market_data()` returns `vwap=22540.0`, `completed_bar_history` length 35, and `completed_bar_history_provenance.status=TRUTHFUL` | `core.market_data.fetch_live_market_data` |
| runtime snapshot payload | `core.orchestrator._snapshot_symbol_payload()` preserves market-data VWAP into the snapshot payload metadata truth | `core.market_data.fetch_live_market_data` |
| strategy context | `core.runtime_snapshot_producer._strategy_context_from_market_symbol()` resolves `StrategyContext.vwap=22540.0` from metadata truth | `metadata.strategy_context_truth.vwap` |
| fallback control | removing truth VWAP while keeping close present leaves `StrategyContext.vwap is None` | no close-as-VWAP fallback |
| ranked pipeline | `build_ranked_opportunity_report()` emits `vwap_reclaim_rejection_v1` from produced runtime truth | ranked candidate path |

## Exact Runtime Proof

Observed fixture values:

- final completed close: `22580.0`
- canonical VWAP from the producer: `22540.0`
- `StrategyContext.vwap`: `22540.0`
- `StrategyContext.vwap != final completed close`
- completed-bar history length: `35`
- ranked-path candidate direction: `BUY_CALL`
- ranked-path candidate status: `VALIDATED_CANDIDATE`
- ranked-path candidate raw score: `0.600710`
- ranked-path provenance label: `VWAP_AUTHORITATIVE`

## Control Result

When the truth VWAP is removed from snapshot metadata while close remains present:

- `StrategyContext.vwap` becomes `None`
- `generate_vwap_reclaim_rejection_candidates()` emits no candidate
- the blocked evidence path remains observable through `STRATEGY_EVIDENCE_BLOCKED`

## Commit Graph

- starting head: `b02118a4dbbf6189ece5342ce33da6921f1155ee`
- implementation head before this evidence update: `b02118a4dbbf6189ece5342ce33da6921f1155ee`
- evidence commit: pending

## Claim Boundary

This update proves the upstream producer chain and runtime builder contract for `StrategyContext.vwap`.
It does not change VWAP reclaim strategy logic, thresholds, ownership boundaries, or production execution behavior.
