from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CertificationArea:
    name: str
    tier: str
    line_min: float
    branch_min: float
    modules: tuple[str, ...]
    required_test_families: tuple[str, ...]


# This manifest covers the authoritative runtime and operator-truth surface.
# Research-only utilities remain outside the production certificate unless they
# are promoted into the live/replay decision path.
WHOLE_TRADEBOT_AREAS: tuple[CertificationArea, ...] = (
    CertificationArea(
        name="runtime_startup_and_auth",
        tier="A",
        line_min=100.0,
        branch_min=100.0,
        modules=(
            "core/auth.py",
            "core/auth_manager.py",
            "core/kite_client.py",
            "core/security_guard.py",
            "core/runtime_safety_boot_guard.py",
            "core/readiness_gate.py",
            "core/startup_recovery.py",
            "core/instance_lock.py",
            "core/session_guard.py",
        ),
        required_test_families=("behavior", "safety", "chaos", "regression"),
    ),
    CertificationArea(
        name="feed_and_market_data_truth",
        tier="A",
        line_min=100.0,
        branch_min=100.0,
        modules=(
            "core/kite_depth_ws.py",
            "core/market_data.py",
            "core/depth_store.py",
            "core/option_liquidity_cache.py",
            "core/quote_truth.py",
            "core/gates/quote_age_gate.py",
        ),
        required_test_families=("behavior", "safety", "chaos", "replay", "certification"),
    ),
    CertificationArea(
        name="orchestration_and_decision_flow",
        tier="A",
        line_min=100.0,
        branch_min=100.0,
        modules=(
            "core/orchestrator.py",
            "core/orchestrator_parts/cycle.py",
            "core/orchestrator_parts/data.py",
            "core/orchestrator_parts/decisions.py",
            "core/orchestrator_parts/finalize.py",
        ),
        required_test_families=("behavior", "safety", "regression", "replay"),
    ),
    CertificationArea(
        name="trade_builder_and_instrument_truth",
        tier="A",
        line_min=100.0,
        branch_min=100.0,
        modules=(
            "strategies/trade_builder.py",
            "core/engine_phase2_adapter.py",
            "core/candidate_finalization.py",
            "core/decision_builder.py",
            "core/decision_dag.py",
        ),
        required_test_families=("behavior", "safety", "edge", "regression"),
    ),
    CertificationArea(
        name="risk_approval_and_execution_boundary",
        tier="A",
        line_min=100.0,
        branch_min=100.0,
        modules=(
            "core/risk_engine.py",
            "core/execution_guard.py",
            "core/risk_halt.py",
            "core/risk_state.py",
            "core/portfolio_risk_allocator.py",
            "core/circuit_breaker.py",
            "core/decision_breakers.py",
            "core/slippage_guard.py",
            "core/slo_guard.py",
            "core/review_queue_contract.py",
            "core/execution_engine.py",
            "core/execution_router.py",
        ),
        required_test_families=("behavior", "safety", "chaos", "broker_firewall", "regression"),
    ),
    CertificationArea(
        name="persistence_reconciliation_and_recovery",
        tier="A",
        line_min=100.0,
        branch_min=100.0,
        modules=(
            "core/events.py",
            "core/audit_log.py",
            "core/decision_logger.py",
            "core/decision_store.py",
            "core/runtime_snapshot_store.py",
            "core/broker_truth_reconciler.py",
        ),
        required_test_families=("behavior", "safety", "chaos", "regression", "replay"),
    ),
    CertificationArea(
        name="candidate_scoring_ranking_and_capital_selection",
        tier="B",
        line_min=95.0,
        branch_min=90.0,
        modules=(
            "core/opportunity_engine.py",
            "core/trade_scoring.py",
            "core/capital_allocator.py",
            "core/portfolio_optimizer.py",
            "core/decision_authority.py",
        ),
        required_test_families=("behavior", "edge", "regression", "ui_read_model"),
    ),
    CertificationArea(
        name="dashboard_observability_and_operator_truth",
        tier="B",
        line_min=95.0,
        branch_min=90.0,
        modules=(
            "dashboard/streamlit_app.py",
            "dashboard/streamlit_app_runtime.py",
            "dashboard/metrics_runtime.py",
            "core/runtime_health.py",
            "core/runtime_snapshot_producer.py",
            "core/observability/pipeline.py",
        ),
        required_test_families=("behavior", "ui_read_model", "safety", "regression"),
    ),
    CertificationArea(
        name="feature_strategy_replay_and_ml_truth",
        tier="B",
        line_min=95.0,
        branch_min=90.0,
        modules=(
            "core/feature_builder.py",
            "core/v2_pipeline.py",
            "core/pro_strategy_pipeline.py",
            "core/option_backtest/engine.py",
            "ml/trade_predictor.py",
        ),
        required_test_families=("behavior", "edge", "replay", "chaos", "regression"),
    ),
)


def all_modules() -> tuple[str, ...]:
    seen: list[str] = []
    for area in WHOLE_TRADEBOT_AREAS:
        for module in area.modules:
            if module not in seen:
                seen.append(module)
    return tuple(seen)


def tier_a_modules() -> tuple[str, ...]:
    return tuple(
        module
        for area in WHOLE_TRADEBOT_AREAS
        if area.tier == "A"
        for module in area.modules
    )


def tier_b_modules() -> tuple[str, ...]:
    return tuple(
        module
        for area in WHOLE_TRADEBOT_AREAS
        if area.tier == "B"
        for module in area.modules
    )
