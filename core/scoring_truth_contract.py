from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.candidate_state_contract import classify_candidate_state
from core.candidate_status_contract import classify_candidate_status_contract

SCORING_TRUTH_CONTRACT_VERSION = "edge48.v1"

EXECUTION_SCORE_CAP = 1.0
RANKABLE_SCORE_CAP = 0.79
ADVISORY_SCORE_CAP = 0.49
SOFT_REJECT_SCORE_CAP = 0.24
DEBUG_ONLY_SCORE_CAP = 0.0
HARD_REJECT_SCORE_CAP = 0.0


@dataclass(frozen=True)
class ScoringTruthDecision:
    raw_score: float
    truth_score: float
    score_cap: float
    score_allowed_for_ranking: bool = False
    score_allowed_for_execution: bool = False
    score_rejected: bool = False
    reasons: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_get(candidate: Any, field: str, default: Any = None) -> Any:
    return candidate.get(field, default) if isinstance(candidate, dict) else getattr(candidate, field, default)


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        if value in (None, "", "None"):
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp01(value: Any) -> float:
    return max(0.0, min(1.0, _safe_float(value)))


def _score_from_payload(score_payload: Any) -> float:
    if isinstance(score_payload, dict):
        for field in ("final_score", "truth_score", "priority_score", "score"):
            if field in score_payload:
                return _clamp01(score_payload.get(field))
    return _clamp01(score_payload)


def _append_unique(items: list[str], item: str | None) -> None:
    text = str(item or "").strip()
    if text and text not in items:
        items.append(text)


def _cap_for_state(state: str) -> tuple[float, str]:
    if state == "hard_reject":
        return HARD_REJECT_SCORE_CAP, "hard_reject_score_cap"
    if state == "soft_reject":
        return SOFT_REJECT_SCORE_CAP, "soft_reject_score_cap"
    if state == "debug_only":
        return DEBUG_ONLY_SCORE_CAP, "debug_only_score_cap"
    if state == "advisory":
        return ADVISORY_SCORE_CAP, "advisory_score_cap"
    if state == "rankable":
        return RANKABLE_SCORE_CAP, "rankable_score_cap"
    if state == "executable":
        return EXECUTION_SCORE_CAP, "executable_score_cap"
    return SOFT_REJECT_SCORE_CAP, "unknown_state_score_cap"


def harden_scoring_truth(candidate: Any, score_payload: Any) -> ScoringTruthDecision:
    """Apply candidate-truth caps to a score payload.

    Scores can describe priority, but they must not override candidate safety,
    freshness, price-feasibility, or explicit execution-permission evidence.
    This function is pure and read-only.
    """
    raw_score = _score_from_payload(score_payload)
    state_decision = classify_candidate_state(candidate)
    status_decision = classify_candidate_status_contract(candidate)

    cap, cap_reason = _cap_for_state(state_decision.state)
    reasons: list[str] = [cap_reason]
    for reason in state_decision.reasons:
        _append_unique(reasons, reason)
    for reason in status_decision.reasons:
        _append_unique(reasons, reason)

    if not status_decision.price_feasible:
        cap = min(cap, SOFT_REJECT_SCORE_CAP)
        _append_unique(reasons, "price_not_score_trusted")
    if not status_decision.execution_allowed:
        _append_unique(reasons, "execution_permission_not_granted")
    if state_decision.is_hard_reject:
        cap = HARD_REJECT_SCORE_CAP
        _append_unique(reasons, "hard_reject_zero_score")
    if state_decision.is_debug_only:
        cap = DEBUG_ONLY_SCORE_CAP
        _append_unique(reasons, "debug_only_zero_score")

    truth_score = round(min(raw_score, cap), 6)
    allowed_for_ranking = (
        state_decision.is_rankable or state_decision.is_executable
    ) and status_decision.price_feasible
    allowed_for_execution = state_decision.is_executable and status_decision.execution_allowed
    rejected = state_decision.is_hard_reject or state_decision.is_soft_reject or state_decision.is_debug_only

    return ScoringTruthDecision(
        raw_score=round(raw_score, 6),
        truth_score=truth_score,
        score_cap=round(float(cap), 6),
        score_allowed_for_ranking=bool(allowed_for_ranking),
        score_allowed_for_execution=bool(allowed_for_execution),
        score_rejected=bool(rejected),
        reasons=tuple(reasons),
        context={
            "contract_version": SCORING_TRUTH_CONTRACT_VERSION,
            "candidate_id": _candidate_get(candidate, "candidate_id"),
            "candidate_state": state_decision.state,
            "price_feasibility_status": status_decision.price_feasibility_status,
            "execution_permission_status": status_decision.execution_permission_status,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_action": False,
            "broker_order_action": False,
        },
    )
