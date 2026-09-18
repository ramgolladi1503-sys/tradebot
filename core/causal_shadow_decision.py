"""Shadow Selection Authority & Risk Gatekeeper (Hops 9-10).

Ranks strategy candidates and enforces fail-closed risk controls in pure shadow
mode with zero broker execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from core.causal_pulse import NativePulse
from core.causal_strategy_harness import CausalCandidate, StrategyEvaluationResult


@dataclass(frozen=True)
class ShadowDecisionResult:
    pulse_id: str
    selected_candidates: list[CausalCandidate]
    rejected_decisions: list[dict[str, Any]]
    risk_verdict: str
    max_portfolio_exposure: float
    timestamp_epoch: float
    read_only: bool = True
    order_authority: bool = False
    broker_write_authority: bool = False
    orders_placed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pulse_id": self.pulse_id,
            "selected_count": len(self.selected_candidates),
            "selected_candidates": [c.to_dict() for c in self.selected_candidates],
            "rejected_count": len(self.rejected_decisions),
            "rejected_decisions": self.rejected_decisions,
            "risk_verdict": self.risk_verdict,
            "max_portfolio_exposure": self.max_portfolio_exposure,
            "timestamp_epoch": self.timestamp_epoch,
            "read_only": self.read_only,
            "order_authority": self.order_authority,
            "broker_write_authority": self.broker_write_authority,
            "orders_placed": self.orders_placed,
        }


def evaluate_shadow_decision(
    *,
    pulse: NativePulse,
    strategy_result: StrategyEvaluationResult,
    feed_health_truth: Mapping[str, Any] | None,
    max_concurrent_exposure: float = 200000.0,
) -> ShadowDecisionResult:
    """Apply selection ranking & risk gatekeeping in shadow observation mode."""
    selected: list[CausalCandidate] = []
    rejected: list[dict[str, Any]] = []

    # 1. Selection Authority Ranking
    sorted_candidates = sorted(
        strategy_result.candidates,
        key=lambda c: float(c.confidence),
        reverse=True,
    )

    current_exposure = 0.0
    for candidate in sorted_candidates:
        estimated_cost = candidate.entry_price * 15.0  # approximate single lot
        if current_exposure + estimated_cost > max_concurrent_exposure:
            rejected.append({
                "candidate_id": candidate.candidate_id,
                "symbol": candidate.symbol,
                "reason_code": "REJECT_RISK_PORTFOLIO_EXPOSURE_LIMIT",
                "detail": f"exceeds max exposure cap {max_concurrent_exposure}",
            })
            continue

        selected.append(candidate)
        current_exposure += estimated_cost

    risk_verdict = "PASS_SHADOW" if (feed_health_truth or {}).get("websocket_ok") is True else "DEGRADED_SHADOW"

    return ShadowDecisionResult(
        pulse_id=pulse.pulse_id,
        selected_candidates=selected,
        rejected_decisions=rejected,
        risk_verdict=risk_verdict,
        max_portfolio_exposure=max_concurrent_exposure,
        timestamp_epoch=pulse.timestamp_epoch,
    )
