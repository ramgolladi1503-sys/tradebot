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

    # 1. Canonical Candidate Selection Call (Hop 9)
    import core.opportunity_engine as opp_engine
    candidate_dicts = [c.to_dict() for c in strategy_result.candidates]
    best_candidate, ranked_candidates = opp_engine.select_best_opportunity(
        candidate_dicts,
        scope="build:causal_observation",
    )

    # 2. Canonical RiskEngine Evaluation (Hop 10)
    risk_engine = RiskEngine()
    portfolio = dict(portfolio_state or {
        "capital": 1000000.0,
        "equity_high": 1000000.0,
        "daily_profit": 0.0,
        "daily_loss": 0.0,
        "open_risk_pct": 0.0,
        "symbol_profit": {},
        "trades_today": 0,
    })
    risk_decision = risk_engine.evaluate_trade(
        portfolio=portfolio,
        regime=strategy_result.regime,
        trade=best_candidate,
    )

    for cand_dict in ranked_candidates:
        cand_id = cand_dict.get("candidate_id")
        orig_cand = next((c for c in strategy_result.candidates if c.candidate_id == cand_id), None)
        if not orig_cand:
            continue

        if best_candidate and cand_id == best_candidate.get("candidate_id") and risk_decision.allowed:
            selected.append(orig_cand)
        else:
            reason = risk_decision.reason if (best_candidate and cand_id == best_candidate.get("candidate_id")) else "opportunity_rank_suboptimal"
            rejected.append({
                "candidate_id": cand_id,
                "symbol": orig_cand.symbol,
                "reason_code": str(risk_decision.reason_code) if (best_candidate and cand_id == best_candidate.get("candidate_id")) else "REJECT_RANK_NOT_SELECTED",
                "detail": str(reason),
            })

    risk_verdict = "PASS_SHADOW" if risk_decision.allowed else "BLOCKED_BY_RISK_ENGINE"

    return ShadowDecisionResult(
        pulse_id=pulse.pulse_id,
        selected_candidates=selected,
        rejected_decisions=rejected,
        risk_verdict=risk_verdict,
        timestamp_epoch=pulse.timestamp_epoch,
    )

