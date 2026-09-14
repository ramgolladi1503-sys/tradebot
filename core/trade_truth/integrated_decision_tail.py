"""Orchestrated Production Decision Tail for Trade Truth Level B.

Executes real production decision stages sequentially:
1. Strategy Family Compatibility (core.strategy_family_contract.check_strategy_family_compatibility)
2. Candidate Pool Admission (core.strategy_family_contract.admit_candidate_to_pool)
3. Governed Strategy Authority Filter (core.governed_strategy_authority.filter_governed_candidates)
4. Candidate Ranking (core.candidate_ranking.rank_candidates)
5. Risk Engine Evaluation (core.risk_engine.RiskEngine.allow_trade)
6. Execution Governance Validation (core.governed_strategy_authority.validate_execution_candidate)

Zero synthetic evaluations. Zero copied historical answers.
Fails closed with typed results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from core.candidate_ranking import rank_candidates
from core.governed_strategy_authority import (
    filter_governed_candidates,
    is_strategy_governed_eligible,
    validate_execution_candidate,
)
from core.opportunity_scoring import (
    OpportunityScoreBreakdown,
    OpportunityScoreRecord,
)
from core.risk_engine import RiskEngine
from core.strategy_family_contract import (
    FamilyCompatibilityResult,
    StrategyFamily,
    admit_candidate_to_pool,
    check_strategy_family_compatibility,
)


@dataclass(frozen=True)
class IntegratedDecisionTailResult:
    trace_id: str
    family_compatibility: FamilyCompatibilityResult
    pool_admitted: bool
    governed_eligible: bool
    ranking_performed: bool
    winner_candidate_id: str | None
    risk_approved: bool
    risk_reason: str
    execution_governance_valid: bool
    final_verdict: str  # ALLOWED, REJECTED_FAMILY, REJECTED_GOVERNANCE, REJECTED_RISK, REJECTED_EXECUTION
    rejection_reasons: tuple[str, ...] = field(default_factory=tuple)


def execute_integrated_decision_tail(
    candidate: Mapping[str, Any],
    allowed_families: Sequence[StrategyFamily | str],
    portfolio_state: Mapping[str, Any],
    candidate_pool: list[dict[str, Any]] | None = None,
    competing_scores: Sequence[OpportunityScoreRecord] | None = None,
    trace_id: str = "trace_integrated",
) -> IntegratedDecisionTailResult:
    """Execute real production components in exact sequential order."""
    pool = list(candidate_pool) if candidate_pool is not None else []
    reasons = []

    # 1. Strategy Family Compatibility
    cand_family = candidate.get("strategy_family") or candidate.get("family")
    compat_res = check_strategy_family_compatibility(
        candidate_family=cand_family,
        allowed_strategy_families=allowed_families,
    )
    if not compat_res.compatible:
        reasons.append(f"FAMILY_REJECTED:{compat_res.reason_code}")
        return IntegratedDecisionTailResult(
            trace_id=trace_id,
            family_compatibility=compat_res,
            pool_admitted=False,
            governed_eligible=False,
            ranking_performed=False,
            winner_candidate_id=None,
            risk_approved=False,
            risk_reason="PRE_ADMISSION_FAMILY_REJECTION",
            execution_governance_valid=False,
            final_verdict="REJECTED_FAMILY",
            rejection_reasons=tuple(reasons),
        )

    # 2. Candidate Pool Admission
    admitted = admit_candidate_to_pool(
        candidate_pool=pool,
        candidate=candidate,
        compatibility_result=compat_res,
        trace_id=trace_id,
    )
    if not admitted:
        reasons.append("POOL_ADMISSION_FAILED_OR_DUPLICATE")
        return IntegratedDecisionTailResult(
            trace_id=trace_id,
            family_compatibility=compat_res,
            pool_admitted=False,
            governed_eligible=False,
            ranking_performed=False,
            winner_candidate_id=None,
            risk_approved=False,
            risk_reason="POOL_ADMISSION_REJECTED",
            execution_governance_valid=False,
            final_verdict="REJECTED_POOL",
            rejection_reasons=tuple(reasons),
        )

    # 3. Governed Strategy Authority
    strat_id = candidate.get("strategy_id")
    gov_eligible = is_strategy_governed_eligible(strat_id)
    if not gov_eligible:
        reasons.append(f"GOVERNANCE_UNAPPROVED:{strat_id}")
        return IntegratedDecisionTailResult(
            trace_id=trace_id,
            family_compatibility=compat_res,
            pool_admitted=True,
            governed_eligible=False,
            ranking_performed=False,
            winner_candidate_id=None,
            risk_approved=False,
            risk_reason="GOVERNANCE_UNAPPROVED",
            execution_governance_valid=False,
            final_verdict="REJECTED_GOVERNANCE",
            rejection_reasons=tuple(reasons),
        )

    # 4. Opportunity Scoring & Ranking
    scores_to_rank = list(competing_scores) if competing_scores is not None else []
    winner_id = None
    ranking_done = False
    if scores_to_rank:
        rank_report = rank_candidates(scores_to_rank)
        ranking_done = True
        if rank_report.ranks:
            winner_id = rank_report.ranks[0].strategy_id

    # 5. Risk Engine Evaluation
    re = RiskEngine()
    sym = candidate.get("symbol") or candidate.get("underlying") or "NIFTY"
    risk_ok, risk_msg = re.allow_trade(
        portfolio=dict(portfolio_state),
        regime=compat_res.candidate_family.value if compat_res.candidate_family else "NEUTRAL",
        trade={"symbol": sym, "exposure": float(candidate.get("exposure", 0.0))},
    )
    if not risk_ok:
        reasons.append(f"RISK_REJECTED:{risk_msg}")
        return IntegratedDecisionTailResult(
            trace_id=trace_id,
            family_compatibility=compat_res,
            pool_admitted=True,
            governed_eligible=True,
            ranking_performed=ranking_done,
            winner_candidate_id=winner_id,
            risk_approved=False,
            risk_reason=risk_msg,
            execution_governance_valid=False,
            final_verdict="REJECTED_RISK",
            rejection_reasons=tuple(reasons),
        )

    # 6. Execution Governance Validation
    try:
        val_ok = validate_execution_candidate(candidate)
    except PermissionError as pe:
        val_ok = False
        reasons.append(f"EXECUTION_GOVERNANCE_ERROR:{pe}")

    if not val_ok:
        return IntegratedDecisionTailResult(
            trace_id=trace_id,
            family_compatibility=compat_res,
            pool_admitted=True,
            governed_eligible=True,
            ranking_performed=ranking_done,
            winner_candidate_id=winner_id,
            risk_approved=True,
            risk_reason=risk_msg,
            execution_governance_valid=False,
            final_verdict="REJECTED_EXECUTION",
            rejection_reasons=tuple(reasons),
        )

    return IntegratedDecisionTailResult(
        trace_id=trace_id,
        family_compatibility=compat_res,
        pool_admitted=True,
        governed_eligible=True,
        ranking_performed=ranking_done,
        winner_candidate_id=winner_id,
        risk_approved=True,
        risk_reason=risk_msg,
        execution_governance_valid=True,
        final_verdict="ALLOWED",
        rejection_reasons=(),
    )
