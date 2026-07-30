"""Read-only opportunity scoring v1.

This module scores candidates only after normalization, classification, and hard
downgrade decisions. It is explainability-only at this stage: it does not rank,
execute, call brokers, touch depth subscriptions, tune live thresholds, or change
dashboard behavior.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from core.candidate_outcome_contract import CandidateOutcomeContract
from core.hard_downgrade_engine import HardDowngradeDecision, HardDowngradeReport
from core.feed_risk_truth import classify_feed_risk_reasons
from core.movement_contract import StrategyCandidate

SCORING_SCHEMA_VERSION = 1

COMPONENT_WEIGHTS: dict[str, float] = {
    "price_structure": 0.18,
    "option_confirmation": 0.18,
    "liquidity": 0.14,
    "freshness": 0.14,
    "regime_alignment": 0.14,
    "timing": 0.08,
    "confluence": 0.08,
    "volatility": 0.06,
}

BUCKET_SCORE_CAPS: dict[str, float] = {
    "EXECUTABLE_CANDIDATE": 1.00,
    "NEAR_EXECUTABLE_CANDIDATE": 0.65,
    "ADVISORY_CANDIDATE": 0.35,
    "SUPPRESSED_CANDIDATE": 0.05,
    "NO_TRADE_CANDIDATE": 0.00,
}

DOWNGRADE_REASON_PENALTIES: dict[str, float] = {
    "fallback_quote_data": 0.40,
    "stale_option_ltp": 0.30,
    "wide_spread": 0.25,
    "missing_depth": 0.25,
    "liquidity_quality_failure": 0.25,
    "weak_option_confirmation": 0.20,
    "unresolved_contract": 0.35,
    "untrusted_quote_source": 0.30,
    "conflicting_trap_signal": 0.25,
    "global_no_trade_active": 0.80,
    "no_trade_suppression": 0.80,
    "candidate_is_no_trade_signal": 1.00,
    "market_closed": 0.50,
    "broker_unavailable": 0.50,
    "soft_safety_evidence_requires_confirmation": 0.15,
}

REGIME_POLICY_EVIDENCE_KEYS: frozenset[str] = frozenset(
    {
        "entropy_state",
        "regime_entropy",
        "regime_entropy_normalized",
        "regime_entropy_state",
        "regime_status",
        "session_bucket",
        "stable_regime",
        "stable_regime_confirmed",
        "trend_state",
        "primary_regime",
        "volume_impulse",
        "liquidity_quality",
        "is_expiry_day",
        "model_source",
        "probability_semantics",
    }
)

SCORE_ELIGIBLE = "SCORE_ELIGIBLE"
NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
ADVISORY_ONLY = "ADVISORY_ONLY"
SUPPRESSED_BY_DOWNGRADE = "SUPPRESSED_BY_DOWNGRADE"
NO_TRADE_ONLY = "NO_TRADE_ONLY"


@dataclass(frozen=True)
class OpportunityScoreBreakdown:
    """Explainable component and penalty breakdown for one candidate score."""

    component_scores: dict[str, float]
    component_weights: dict[str, float]
    weighted_component_scores: dict[str, float]
    base_score: float
    penalties: dict[str, float]
    total_penalty: float
    bucket_cap: float
    trap_risk_penalty: float
    final_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_scores": dict(self.component_scores),
            "component_weights": dict(self.component_weights),
            "weighted_component_scores": dict(self.weighted_component_scores),
            "base_score": self.base_score,
            "penalties": dict(self.penalties),
            "total_penalty": self.total_penalty,
            "bucket_cap": self.bucket_cap,
            "trap_risk_penalty": self.trap_risk_penalty,
            "final_score": self.final_score,
        }


@dataclass(frozen=True)
class OpportunityScoreRecord:
    """Read-only score record for one candidate."""

    strategy_id: str
    symbol: str
    direction: str
    movement_type: str
    bucket: str
    score_eligibility: str
    final_score: float
    executable_candidate: bool
    score_explanation: str
    downgrade_reasons: tuple[str, ...]
    safety_flags: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    breakdown: OpportunityScoreBreakdown
    outcome_contract: Optional[CandidateOutcomeContract] = None
    feed_risk_reasons: tuple[str, ...] = ()
    feed_risk_precomputed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "movement_type": self.movement_type,
            "bucket": self.bucket,
            "score_eligibility": self.score_eligibility,
            "final_score": self.final_score,
            "executable_candidate": self.executable_candidate,
            "score_explanation": self.score_explanation,
            "downgrade_reasons": list(self.downgrade_reasons),
            "safety_flags": list(self.safety_flags),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "feed_risk_reasons": list(self.feed_risk_reasons),
            "feed_risk_precomputed": self.feed_risk_precomputed,
            "breakdown": self.breakdown.to_dict(),
            "outcome_contract": self.outcome_contract.to_dict() if self.outcome_contract else None,
        }


@dataclass(frozen=True)
class OpportunityScoreReport:
    """Read-only opportunity score report."""

    schema_version: int
    score_count: int
    score_eligible_count: int
    needs_confirmation_count: int
    advisory_count: int
    suppressed_count: int
    no_trade_count: int
    scores: tuple[OpportunityScoreRecord, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    safety_flags: tuple[str, ...]
    read_only: bool = True
    append: bool = False
    is_order_action: bool = False  # is_order_action=false
    broker_api_called: bool = False  # broker_api_called=false
    live_order_action: bool = False  # live_order_action=false
    broker_order_action: bool = False  # broker_order_action=false
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "is_order_action": False,
            "append": self.append,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
            "score_count": self.score_count,
            "score_eligible_count": self.score_eligible_count,
            "needs_confirmation_count": self.needs_confirmation_count,
            "advisory_count": self.advisory_count,
            "suppressed_count": self.suppressed_count,
            "no_trade_count": self.no_trade_count,
            "scores": [score.to_dict() for score in self.scores],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "safety_flags": list(self.safety_flags),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def score_opportunities(
    candidates: Iterable[StrategyCandidate],
    downgrade_report: HardDowngradeReport | Iterable[HardDowngradeDecision],
    *,
    scoring_profile: Any = None,
) -> OpportunityScoreReport:
    """Score candidates using downgrade decisions as the safety source of truth.

    ``scoring_profile`` is intentionally opt-in. When omitted, the existing fixed
    component weights remain unchanged.
    """

    candidate_tuple = tuple(candidates or ())
    for candidate in candidate_tuple:
        if not isinstance(candidate, StrategyCandidate):
            raise TypeError("opportunity_scoring_expected_strategy_candidate")

    decisions = _coerce_decisions(downgrade_report)
    decision_by_id = {decision.strategy_id: decision for decision in decisions}
    missing = tuple(candidate.strategy_id for candidate in candidate_tuple if candidate.strategy_id not in decision_by_id)
    if missing:
        raise ValueError(f"missing_downgrade_decision:{','.join(sorted(missing))}")

    component_weights = _component_weights(scoring_profile)
    records = tuple(
        score_candidate(candidate, decision_by_id[candidate.strategy_id], component_weights=component_weights)
        for candidate in candidate_tuple
    )
    blockers = tuple(sorted(set(blocker for record in records for blocker in record.blockers)))
    warnings = tuple(sorted(set(warning for record in records for warning in record.warnings)))
    safety_flags = tuple(sorted(set(flag for record in records for flag in record.safety_flags)))

    return OpportunityScoreReport(
        schema_version=SCORING_SCHEMA_VERSION,
        read_only=True,
        append=False,
        score_count=len(records),
        score_eligible_count=sum(1 for record in records if record.score_eligibility == SCORE_ELIGIBLE),
        needs_confirmation_count=sum(1 for record in records if record.score_eligibility == NEEDS_CONFIRMATION),
        advisory_count=sum(1 for record in records if record.score_eligibility == ADVISORY_ONLY),
        suppressed_count=sum(1 for record in records if record.score_eligibility == SUPPRESSED_BY_DOWNGRADE),
        no_trade_count=sum(1 for record in records if record.score_eligibility == NO_TRADE_ONLY),
        scores=records,
        blockers=blockers,
        warnings=warnings,
        safety_flags=safety_flags,
        metadata={
            "scorer": "opportunity_score_v1",
            "scope": "read_only_no_execution_no_ranking",
            "component_weights": dict(component_weights),
            "base_component_weights": dict(COMPONENT_WEIGHTS),
            "scoring_profile_applied": bool(scoring_profile is not None),
            "scoring_profile_name": _profile_name(scoring_profile),
            "source_downgrade_engine": getattr(downgrade_report, "metadata", {}).get("downgrade_engine")
            if isinstance(downgrade_report, HardDowngradeReport)
            else None,
        },
    )


def _regime_policy_inputs(candidate: StrategyCandidate) -> dict[str, Any]:
    """Resolve canonical regime-policy inputs from candidate evidence.

    The resolver supports the legacy nested ``entropy_state`` object and the
    explicit Regime Robustness V1 fields. It does not invent missing evidence.
    """
    evidence = dict(candidate.evidence or {})
    nested_entropy = evidence.get("entropy_state")
    if isinstance(nested_entropy, Mapping):
        raw_entropy = nested_entropy.get("current_value")
        normalized_entropy = nested_entropy.get("normalized")
        entropy_state = nested_entropy.get("state")
    else:
        raw_entropy = evidence.get("regime_entropy", evidence.get("entropy_value", 0.0))
        normalized_entropy = evidence.get(
            "regime_entropy_normalized",
            evidence.get("normalized_entropy", 0.0),
        )
        entropy_state = evidence.get(
            "regime_entropy_state",
            nested_entropy if nested_entropy is not None else "UNKNOWN",
        )

    stable_raw = evidence.get("stable_regime_confirmed")
    stable_regime = stable_raw if isinstance(stable_raw, bool) else None
    trend_state = (
        evidence.get("trend_state")
        or evidence.get("stable_regime")
        or evidence.get("primary_regime")
        or "UNKNOWN"
    )
    return {
        "session_bucket": evidence.get("session_bucket", "DEFAULT"),
        "entropy_value": raw_entropy if raw_entropy is not None else 0.0,
        "normalized_entropy": normalized_entropy if normalized_entropy is not None else 0.0,
        "entropy_state": entropy_state or "UNKNOWN",
        "trend_state": trend_state,
        "volume_impulse": bool(evidence.get("volume_impulse", False)),
        "liquidity_quality": evidence.get("liquidity_quality", "UNKNOWN"),
        "is_expiry_day": bool(evidence.get("is_expiry_day", False)),
        "regime_status": evidence.get("regime_status"),
        "stable_regime": stable_regime,
    }


def _regime_policy_is_authoritative(candidate: StrategyCandidate) -> bool:
    """Return whether regime policy owns this candidate's scoring decision.

    Production movement candidates are always governed by the policy, including
    unknown future strategy IDs. Generic scorer-only fixtures with no canonical
    strategy, no movement lineage, and no regime evidence retain the scorer's
    pre-policy compatibility contract.
    """
    from core.strategy_regime_policy import canonical_strategy_family

    evidence = dict(candidate.evidence or {})
    lineage = dict(candidate.lineage or {})
    source = str(lineage.get("source") or "").strip().lower()
    has_regime_evidence = any(key in evidence for key in REGIME_POLICY_EVIDENCE_KEYS)
    return bool(
        canonical_strategy_family(candidate.strategy_id) is not None
        or source == "movement_strategy"
        or has_regime_evidence
    )


def score_candidate(
    candidate: StrategyCandidate,
    decision: HardDowngradeDecision,
    *,
    component_weights: Mapping[str, float] | None = None,
) -> OpportunityScoreRecord:
    """Score a single candidate with a matching hard-downgrade decision."""

    if not isinstance(candidate, StrategyCandidate):
        raise TypeError("opportunity_scoring_expected_strategy_candidate")
    if not isinstance(decision, HardDowngradeDecision):
        raise TypeError("opportunity_scoring_expected_downgrade_decision")
    if candidate.strategy_id != decision.strategy_id:
        raise ValueError("candidate_and_downgrade_strategy_id_mismatch")

    policy_result = "ELIGIBLE"
    if _regime_policy_is_authoritative(candidate):
        from core.strategy_regime_policy import evaluate_strategy_regime_policy

        policy_inputs = _regime_policy_inputs(candidate)
        volatility_expansion = (candidate.regime_scores or {}).get("VOLATILITY_EXPANSION", 0.0) > 0.5
        policy_output = evaluate_strategy_regime_policy(
            strategy=candidate.strategy_id,
            volatility_expansion=volatility_expansion,
            **policy_inputs,
        )
        policy_result = policy_output.get("policy_result", "ELIGIBLE")

    policy_bucket = decision.downgraded_bucket
    policy_eligibility = _score_eligibility(decision)
    safety_flags = list(decision.safety_flags)

    if policy_result == "BLOCKED" and policy_eligibility != NO_TRADE_ONLY:
        policy_bucket = "SUPPRESSED_CANDIDATE"
        policy_eligibility = "SUPPRESSED_BY_DOWNGRADE"
    elif policy_result == "ADVISORY_ONLY":
        if policy_bucket == "EXECUTABLE_CANDIDATE":
            policy_bucket = "ADVISORY_CANDIDATE"
            policy_eligibility = "ADVISORY_ONLY"

    # Strict promotion state enforcement
    promotion_state = (candidate.lineage or {}).get("promotion_state", "ADVISORY_ONLY")

    # 1. Negative evidence -> DISABLED
    if promotion_state == "DISABLED" or promotion_state == "NEGATIVE_EVIDENCE":
        policy_bucket = "NO_TRADE_CANDIDATE"
        policy_eligibility = "NO_TRADE_ONLY"
    # 2. ADVISORY or EXPERIMENTAL or unknown -> not executable
    elif promotion_state in ("ADVISORY_ONLY", "EXPERIMENTAL", "UNKNOWN"):
        if policy_bucket == "EXECUTABLE_CANDIDATE":
            policy_bucket = "ADVISORY_CANDIDATE"
            policy_eligibility = "ADVISORY_ONLY"
    # 3. PAPER_EXECUTABLE -> adds a safety flag to block real execution
    elif promotion_state == "PAPER_EXECUTABLE":
        if "paper_executable_only" not in safety_flags:
            safety_flags.append("paper_executable_only")
    # 4. MANUAL_APPROVAL_ELIGIBLE or PROMOTED -> no downgrade (but doesn't upgrade if truth gates blocked it)

    feed_risk_reasons = classify_feed_risk_reasons(
        safety_flags=safety_flags,
        downgrade_reasons=tuple(sorted(decision.downgrade_reasons)),
        blockers=tuple(sorted(decision.blockers)),
        warnings=tuple(sorted(decision.warnings)),
        candidate_class=policy_bucket,
    )

    weights = _component_weights(component_weights)
    component_scores = _component_scores(candidate)
    weighted = {name: _round(component_scores[name] * weights[name]) for name in weights}
    base_score = _round(sum(weighted.values()))
    trap_penalty = _round(clamp(float(candidate.trap_risk_score)) * 0.15)
    penalties = _penalties(decision)
    total_penalty = _round(sum(penalties.values()) + trap_penalty)
    bucket_cap = BUCKET_SCORE_CAPS.get(policy_bucket, 0.0)
    raw_final = clamp(base_score - total_penalty)
    final_score = _round(min(raw_final, bucket_cap))
    if policy_eligibility == NO_TRADE_ONLY:
        final_score = 0.0

    return OpportunityScoreRecord(
        strategy_id=candidate.strategy_id,
        symbol=candidate.symbol,
        direction=candidate.direction,
        movement_type=candidate.movement_type,
        bucket=policy_bucket,
        score_eligibility=policy_eligibility,
        final_score=final_score,
        executable_candidate=bool(decision.executable_candidate and policy_eligibility == SCORE_ELIGIBLE),
        score_explanation=_score_explanation(policy_eligibility, base_score, total_penalty, bucket_cap, final_score),
        downgrade_reasons=tuple(sorted(decision.downgrade_reasons)),
        safety_flags=tuple(sorted(safety_flags)),
        blockers=tuple(sorted(decision.blockers)),
        warnings=tuple(sorted(decision.warnings)),
        feed_risk_reasons=feed_risk_reasons,
        feed_risk_precomputed=True,
        breakdown=OpportunityScoreBreakdown(
            component_scores=component_scores,
            component_weights=dict(weights),
            weighted_component_scores=weighted,
            base_score=base_score,
            penalties=penalties,
            total_penalty=total_penalty,
            bucket_cap=bucket_cap,
            trap_risk_penalty=trap_penalty,
            final_score=final_score,
        ),
        outcome_contract=candidate.outcome_contract,
    )


def _component_scores(candidate: StrategyCandidate) -> dict[str, float]:
    return {
        "price_structure": _round(clamp(candidate.price_structure_score)),
        "option_confirmation": _round(clamp(candidate.option_confirmation_score)),
        "liquidity": _round(clamp(candidate.liquidity_score)),
        "freshness": _round(clamp(candidate.freshness_score)),
        "regime_alignment": _round(clamp(candidate.regime_alignment_score)),
        "timing": _round(clamp(candidate.timing_score)),
        "confluence": _round(clamp(candidate.confluence_score)),
        "volatility": _round(clamp(candidate.volatility_score)),
    }


def _component_weights(scoring_profile: Any = None) -> dict[str, float]:
    if scoring_profile is None:
        return dict(COMPONENT_WEIGHTS)
    if isinstance(scoring_profile, Mapping):
        candidate_weights = dict(scoring_profile)
    else:
        candidate_weights = dict(getattr(scoring_profile, "adjusted_component_weights", {}) or {})
    normalized = {str(key).strip(): clamp(value) for key, value in candidate_weights.items()}
    if set(normalized) != set(COMPONENT_WEIGHTS):
        raise ValueError("opportunity_scoring_profile_component_mismatch")
    total = sum(normalized.values())
    if total <= 0.0:
        raise ValueError("opportunity_scoring_profile_weight_sum_zero")
    return {key: _round(normalized[key] / total) for key in sorted(normalized)}


def _profile_name(scoring_profile: Any = None) -> str | None:
    if scoring_profile is None:
        return None
    value = getattr(scoring_profile, "primary_regime", None) or getattr(scoring_profile, "profile_name", None)
    if value:
        return str(value)
    return "custom_component_weights"


def _penalties(decision: HardDowngradeDecision) -> dict[str, float]:
    penalties: dict[str, float] = {}
    for reason in decision.downgrade_reasons:
        key = str(reason).strip().lower()
        if key in DOWNGRADE_REASON_PENALTIES:
            penalties[key] = max(penalties.get(key, 0.0), DOWNGRADE_REASON_PENALTIES[key])
    if decision.hard_blockers:
        penalties["hard_blocker_count_penalty"] = min(0.35, 0.10 * len(decision.hard_blockers))
    return {key: _round(value) for key, value in sorted(penalties.items())}


def _score_eligibility(decision: HardDowngradeDecision) -> str:
    bucket = str(decision.downgraded_bucket)
    if bucket == "NO_TRADE_CANDIDATE":
        return NO_TRADE_ONLY
    if bucket == "SUPPRESSED_CANDIDATE":
        return SUPPRESSED_BY_DOWNGRADE
    if bucket == "ADVISORY_CANDIDATE":
        return ADVISORY_ONLY
    if bucket == "NEAR_EXECUTABLE_CANDIDATE":
        return NEEDS_CONFIRMATION
    if bucket == "EXECUTABLE_CANDIDATE" and decision.executable_candidate:
        return SCORE_ELIGIBLE
    return ADVISORY_ONLY


def _score_explanation(eligibility: str, base_score: float, total_penalty: float, bucket_cap: float, final_score: float) -> str:
    return (
        f"{eligibility}: base={base_score:.4f}, penalty={total_penalty:.4f}, "
        f"cap={bucket_cap:.4f}, final={final_score:.4f}"
    )


def _coerce_decisions(downgrade_report: HardDowngradeReport | Iterable[HardDowngradeDecision]) -> tuple[HardDowngradeDecision, ...]:
    if isinstance(downgrade_report, HardDowngradeReport):
        return tuple(downgrade_report.decisions)
    decisions = tuple(downgrade_report or ())
    for decision in decisions:
        if not isinstance(decision, HardDowngradeDecision):
            raise TypeError("opportunity_scoring_expected_downgrade_decision")
    return decisions


def clamp(value: float) -> float:
    try:
        out = float(value)
    except Exception:
        return 0.0
    if out < 0.0:
        return 0.0
    if out > 1.0:
        return 1.0
    return out


def _round(value: float) -> float:
    return round(float(value), 6)


__all__ = [
    "ADVISORY_ONLY",
    "BUCKET_SCORE_CAPS",
    "COMPONENT_WEIGHTS",
    "DOWNGRADE_REASON_PENALTIES",
    "NEEDS_CONFIRMATION",
    "NO_TRADE_ONLY",
    "REGIME_POLICY_EVIDENCE_KEYS",
    "SCORE_ELIGIBLE",
    "SCORING_SCHEMA_VERSION",
    "SUPPRESSED_BY_DOWNGRADE",
    "OpportunityScoreBreakdown",
    "OpportunityScoreRecord",
    "OpportunityScoreReport",
    "clamp",
    "score_candidate",
    "score_opportunities",
]
