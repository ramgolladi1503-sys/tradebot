"""Shadow Selection Authority & Risk Gatekeeper Adapter (Hops 9-10).

Wraps the canonical opportunity selection engine (select_best_opportunity) and
production RiskEngine in pure read-only observation mode with zero order authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.causal_pulse import NativePulse
from core.causal_strategy_harness import CausalCandidate, StrategyEvaluationResult
from core.opportunity_engine import select_best_opportunity
from core.risk_engine import RiskEngine


@dataclass(frozen=True)
class ShadowDecisionResult:
    pulse_id: str
    selected_candidates: list[CausalCandidate]
    rejected_decisions: list[dict[str, Any]]
    risk_verdict: str
    timestamp_epoch: float
    read_only: bool = True
    order_authority: bool = False
    broker_write_authority: bool = False
    orders_placed: int = 0
    orders_modified: int = 0
    orders_cancelled: int = 0
    actual_execution: bool = False
    execution_status: str = "NOT_EXECUTED_OBSERVATION_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pulse_id": self.pulse_id,
            "selected_count": len(self.selected_candidates),
            "selected_candidates": [c.to_dict() for c in self.selected_candidates],
            "rejected_count": len(self.rejected_decisions),
            "rejected_decisions": self.rejected_decisions,
            "risk_verdict": self.risk_verdict,
            "timestamp_epoch": self.timestamp_epoch,
            "read_only": True,
            "order_authority": False,
            "broker_write_authority": False,
            "orders_placed": 0,
            "orders_modified": 0,
            "orders_cancelled": 0,
            "actual_execution": False,
            "execution_status": "NOT_EXECUTED_OBSERVATION_ONLY",
        }


def evaluate_shadow_decision(
    *,
    pulse: NativePulse,
    strategy_result: StrategyEvaluationResult,
    feed_health_truth: Mapping[str, Any] | None,
    portfolio_state: Mapping[str, Any] | None = None,
) -> ShadowDecisionResult:
    """Apply selection ranking & risk gatekeeping in shadow observation mode."""
    selected: list[CausalCandidate] = []
    rejected: list[dict[str, Any]] = []

    if not strategy_result.candidates:
        return ShadowDecisionResult(
            pulse_id=pulse.pulse_id,
            selected_candidates=[],
            rejected_decisions=[],
            risk_verdict="NOT_APPLICABLE_NO_CANDIDATES",
            timestamp_epoch=pulse.timestamp_epoch,
        )

    # Shadow-only CAS candidates are observations, never risk-approved orders.
    # Do not invent a default portfolio to manufacture risk PASS.
    from core.governed_strategy_authority import is_strategy_governed_eligible
    admissible = [
        c for c in strategy_result.candidates
        if c.execution_eligible and is_strategy_governed_eligible(c.strategy_id)
    ]
    if not admissible:
        return ShadowDecisionResult(
            pulse_id=pulse.pulse_id, selected_candidates=[],
            rejected_decisions=[
                {"candidate_id": c.candidate_id, "symbol": c.symbol,
                 "reason_code": "SHADOW_ONLY_OR_EXECUTION_GATES_NOT_PASSED"}
                for c in strategy_result.candidates
            ],
            risk_verdict="NOT_EVALUATED_SHADOW_ONLY",
            timestamp_epoch=pulse.timestamp_epoch,
        )
    if portfolio_state is None:
        return ShadowDecisionResult(
            pulse_id=pulse.pulse_id, selected_candidates=[],
            rejected_decisions=[
                {"candidate_id": c.candidate_id, "symbol": c.symbol,
                 "reason_code": "PORTFOLIO_STATE_MISSING"}
                for c in admissible
            ],
            risk_verdict="NOT_EVALUATED_PORTFOLIO_UNKNOWN",
            timestamp_epoch=pulse.timestamp_epoch,
        )
    # This branch remains available for future *actually authorized* strategies.
    import core.opportunity_engine as opp_engine
    candidate_dicts = [c.to_dict() for c in admissible]
    best, ranked = opp_engine.select_best_opportunity(
        candidate_dicts, scope="build:causal_observation",
    )
    if not isinstance(best, Mapping):
        return ShadowDecisionResult(
            pulse_id=pulse.pulse_id, selected_candidates=[],
            rejected_decisions=[], risk_verdict="NOT_EVALUATED_NO_SELECTION",
            timestamp_epoch=pulse.timestamp_epoch,
        )
    from core.risk_engine import RiskEngine
    decision = RiskEngine().evaluate_trade(
        portfolio=dict(portfolio_state), regime=strategy_result.regime, trade=best,
    )
    selected = [
        c for c in admissible
        if c.candidate_id == best.get("candidate_id") and decision.allowed
    ]
    rejected = [
        {"candidate_id": c.candidate_id, "symbol": c.symbol,
         "reason_code": str(decision.reason_code) if
         c.candidate_id == best.get("candidate_id") else "REJECT_RANK_NOT_SELECTED"}
        for c in admissible if c not in selected
    ]
    return ShadowDecisionResult(
        pulse_id=pulse.pulse_id, selected_candidates=selected,
        rejected_decisions=rejected,
        risk_verdict="PASS_SHADOW" if decision.allowed else "BLOCKED_BY_RISK_ENGINE",
        timestamp_epoch=pulse.timestamp_epoch,
    )
