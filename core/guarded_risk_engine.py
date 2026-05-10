from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.risk_data_guard import evaluate_data_risk
from core.risk_engine import OfflineCandidateRiskAssessment, evaluate_candidate_risk


def evaluate_candidate_risk_guarded(
    candidate: Any,
    *,
    portfolio_state: dict[str, Any] | None = None,
    selected_candidates: list[Any] | None = None,
    family_learning_state: dict[str, Any] | None = None,
) -> OfflineCandidateRiskAssessment:
    """Risk evaluation with data-truth guard applied first.

    This is the safe guard-mode integration point: dirty data is treated as risk
    and blocked before the normal risk decision is allowed to approve it. Clean
    candidates still flow through the existing risk engine unchanged.
    """
    data_guard = evaluate_data_risk(candidate)
    base = evaluate_candidate_risk(
        candidate,
        portfolio_state=portfolio_state,
        selected_candidates=selected_candidates,
        family_learning_state=family_learning_state,
    )
    context = dict(base.context or {})
    context.update(data_guard.to_context())
    if data_guard.allowed:
        return replace(base, context=context)

    return replace(
        base,
        risk_budget_ok=False,
        risk_budget_reason=data_guard.reason_code,
        rejected_at_stage="risk_data_truth",
        rejection_reason_code=data_guard.reason_code,
        rejection_bucket="DATA_RISK",
        rejection_severity="hard",
        context=context,
    )
