from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ValidationState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ResearchValidationPolicy:
    minimum_psr: float = 0.95
    minimum_dsr: float = 0.95
    minimum_power: float = 0.80
    maximum_pbo: float = 0.50
    require_search_adjustment_when_multiple_trials: bool = True
    require_wfa: bool = True
    require_cost_robustness: bool = True
    require_holdout: bool = True
    require_prospective_confirmation: bool = True


@dataclass(frozen=True)
class ResearchEvidence:
    search_history_complete: bool
    total_trials: int
    effective_trials: float | None
    psr: float | None
    dsr: float | None
    actual_track_record: int
    minimum_track_record: float | None
    power: float | None
    pbo: float | None
    inference_model_valid: bool
    wfa: ValidationState
    cost_robustness: ValidationState
    holdout: ValidationState
    prospective: ValidationState


@dataclass(frozen=True)
class ResearchVerdict:
    passed: bool
    verdict: str
    blockers: tuple[str, ...]
    allowed_for_live_execution: bool = False
    broker_api_called: bool = False
    is_order_action: bool = False
    read_only: bool = True


def _probability_or_none(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name}_must_be_probability")
    return float(value)


def evaluate_research_evidence(
    evidence: ResearchEvidence,
    policy: ResearchValidationPolicy = ResearchValidationPolicy(),
) -> ResearchVerdict:
    """Apply the offline research gate without granting execution authority."""
    if evidence.total_trials < 1:
        raise ValueError("total_trials_must_be_positive")
    if evidence.actual_track_record < 0:
        raise ValueError("actual_track_record_must_be_nonnegative")
    if evidence.effective_trials is not None and not (
        1.0 <= evidence.effective_trials <= evidence.total_trials + 1e-9
    ):
        raise ValueError("effective_trials_out_of_range")
    psr = _probability_or_none("psr", evidence.psr)
    dsr = _probability_or_none("dsr", evidence.dsr)
    power = _probability_or_none("power", evidence.power)
    pbo = _probability_or_none("pbo", evidence.pbo)

    blockers: list[str] = []
    if not evidence.search_history_complete:
        blockers.append("SEARCH_HISTORY_INCOMPLETE")
    if not evidence.inference_model_valid:
        blockers.append("INFERENCE_MODEL_INVALID")

    if evidence.minimum_track_record is None:
        blockers.append("MINIMUM_TRACK_RECORD_MISSING")
    elif evidence.actual_track_record < evidence.minimum_track_record:
        blockers.append("UNDERPOWERED_TRACK_RECORD")

    if power is None:
        blockers.append("POWER_MISSING")
    elif power < policy.minimum_power:
        blockers.append("UNDERPOWERED")

    if psr is None:
        blockers.append("PSR_MISSING")
    elif psr < policy.minimum_psr:
        blockers.append("PSR_FAIL")

    multiple_trials = evidence.total_trials > 1 or (
        evidence.effective_trials is not None
        and evidence.effective_trials > 1.0 + 1e-9
    )
    if multiple_trials and policy.require_search_adjustment_when_multiple_trials:
        if evidence.effective_trials is None:
            blockers.append("EFFECTIVE_TRIAL_COUNT_MISSING")
        if dsr is None:
            blockers.append("SEARCH_ADJUSTMENT_MISSING")
        elif dsr < policy.minimum_dsr:
            blockers.append("DSR_FAIL")

    if pbo is not None and pbo > policy.maximum_pbo:
        blockers.append("PBO_HIGH")

    if policy.require_wfa:
        if evidence.wfa is ValidationState.FAIL:
            blockers.append("WFA_FAIL")
        elif evidence.wfa is not ValidationState.PASS:
            blockers.append("WFA_NOT_PROVEN")

    if policy.require_cost_robustness:
        if evidence.cost_robustness is ValidationState.FAIL:
            blockers.append("COST_ROBUSTNESS_FAIL")
        elif evidence.cost_robustness is not ValidationState.PASS:
            blockers.append("COST_ROBUSTNESS_UNKNOWN")

    if policy.require_holdout:
        if evidence.holdout is ValidationState.FAIL:
            blockers.append("HOLDOUT_FAIL")
        elif evidence.holdout is not ValidationState.PASS:
            blockers.append("HOLDOUT_NOT_RUN")

    if policy.require_prospective_confirmation:
        if evidence.prospective is ValidationState.FAIL:
            blockers.append("PROSPECTIVE_FAIL")
        elif evidence.prospective is not ValidationState.PASS:
            blockers.append("PROSPECTIVE_NOT_CONFIRMED")

    if blockers:
        return ResearchVerdict(False, blockers[0], tuple(blockers))
    return ResearchVerdict(True, "RESEARCH_EVIDENCE_PASS", tuple())
