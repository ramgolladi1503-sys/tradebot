# Executive Verdict v2

Principal outcome: `END_TO_END_PIPELINE_NOT_AUDITABLE`

This is not a profitability or production-readiness claim. The audit found a mapped, partially testable lifecycle, but a valid live market event is not yet proven to traverse feed -> strategy -> TradeBuilder -> Phase 1 -> Phase 2 -> candidate pool -> orchestration -> ranking -> UI approval -> order intent -> broker boundary -> reconciliation with stable identity, reconciled accounting, and fault-injection proof.

Worktree HEAD: `1da7732aaa0d1d4ae3f67447fdf447f4f54bef09`

Origin/main: `24d2e8b97859250598aef8cd706c43f71209475b`; merge-base: `24d2e8b97859250598aef8cd706c43f71209475b`; ahead/behind: `1/0`. Drift from original base `24d2e8b97859250598aef8cd706c43f71209475b`: none at generation time.

Reachable/conditionally reachable runtime callable rows audited: `1082`

Active movement strategies represented: `12/12`

Severity counts over reachable callable matrix: P0=0, P1=21, P2=19, P3=1042

Stage sub-verdicts:

- feed_and_market_data_robustness: `NOT_PROVEN`
- market_state_construction: `NOT_PROVEN`
- strategy_invocation_and_signal_integrity: `PARTIALLY_VERIFIED`
- tradebuilder_correctness: `NOT_PROVEN`
- phase1_gate_integrity: `NOT_PROVEN`
- phase2_gate_integrity: `PARTIALLY_VERIFIED_WITH_GAPS`
- candidate_pool_integrity: `PARTIALLY_VERIFIED_WITH_GAPS`
- orchestration_correctness: `PARTIALLY_VERIFIED_WITH_GAPS`
- risk_and_executable_truth_safety: `PARTIALLY_VERIFIED_WITH_GAPS`
- scoring_and_ranking_robustness: `PARTIALLY_VERIFIED_WITH_LIMITATIONS`
- ui_and_approval_authority: `FAILED_PARTIAL_PROOF`
- order_intent_and_broker_boundary_correctness: `NOT_PROVEN`
- order_state_and_reconciliation_robustness: `NOT_PROVEN`
- observability_recovery_and_auditability: `PARTIALLY_VERIFIED_WITH_GAPS`
- overall_test_adequacy: `INSUFFICIENT_FOR_END_TO_END_CERTIFICATION`

Top defects/gaps:

1. `dashboard/streamlit_app_runtime.py` fallback display paths can surface rows not proven to be ranked-snapshot backed.
2. `strategies/trade_builder.py:TradeBuilder` is safety-critical but not fully certified by frozen end-to-end scenarios.
3. `core/_engine_phase2_adapter_base.py:build_candidates_phase2` mutates candidate dictionaries and fallback/soft-penalty fields; full reason preservation is partial.
4. `core/execution_engine/router.py` broker-boundary mapping lacks v2 mock timeout/rejection/idempotency proof.
5. `core/broker_truth_reconciler.py` reconciliation exists but partial-fill/out-of-order/restart recovery is not proven.
