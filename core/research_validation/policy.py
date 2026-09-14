from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping


PASS = "PASS"
FAIL = "FAIL"
INCONCLUSIVE = "INCONCLUSIVE"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CertificationInput:
    """Evidence bundle for offline research certification.

    Missing or malformed evidence blocks certification. This object carries only
    research evidence; it has no runtime or execution authority.
    """

    hypothesis_id: str
    registered_experiments: int
    declared_experiments: int
    parameter_stability_pass: bool
    wfa_pass: bool
    pbo: float | None
    psr: float | None
    dsr: float | None
    actual_track_record: int
    minimum_track_record: int | float | None
    power: float | None
    cost_robust_pass: bool
    holdout_status: str
    prospective_status: str = "NOT_RUN"
    inference_model_valid: bool = True
    search_history_complete: bool = True
    additional_gates: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class CertificationVerdict:
    status: str
    reasons: tuple[str, ...]
    gates: Mapping[str, str]
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False
    append: bool = False


def _finite_probability(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and 0.0 <= value <= 1.0


def _valid_threshold(value: float) -> bool:
    return math.isfinite(value) and 0.0 <= value <= 1.0


def certify_research(
    evidence: CertificationInput,
    *,
    max_pbo: float = 0.20,
    min_psr: float = 0.95,
    min_dsr: float = 0.95,
    min_power: float = 0.80,
    require_prospective: bool = False,
) -> CertificationVerdict:
    """Fail-closed research-only certification gate.

    `CERTIFIED_RESEARCH` means the supplied offline evidence passed these gates.
    It never authorizes paper/live execution or broker actions.
    """
    if not all(_valid_threshold(v) for v in (max_pbo, min_psr, min_dsr, min_power)):
        return _blocked("INVALID_POLICY_THRESHOLD")
    if not evidence.hypothesis_id.strip():
        return _blocked("MISSING_HYPOTHESIS_ID")
    if evidence.registered_experiments < 1 or evidence.declared_experiments < 1:
        return _blocked("MISSING_EXPERIMENT_HISTORY")
    if evidence.declared_experiments != evidence.registered_experiments:
        return _blocked("SEARCH_HISTORY_INCOMPLETE")
    if not evidence.search_history_complete:
        return _blocked("SEARCH_HISTORY_INCOMPLETE")
    if not evidence.inference_model_valid:
        return _blocked("INFERENCE_MODEL_INVALID")
    if evidence.actual_track_record < 0:
        return _blocked("INVALID_TRACK_RECORD")

    gates: dict[str, str] = {}
    reasons: list[str] = []

    def hard_gate(name: str, passed: bool, reason: str) -> None:
        gates[name] = PASS if passed else FAIL
        if not passed:
            reasons.append(reason)

    hard_gate("parameter_stability", evidence.parameter_stability_pass, "PARAMETER_FRAGILE")
    hard_gate("wfa", evidence.wfa_pass, "WFA_FAIL")

    if not _finite_probability(evidence.pbo):
        gates["pbo"] = BLOCKED
        reasons.append("PBO_MISSING_OR_INVALID")
    else:
        hard_gate("pbo", evidence.pbo <= max_pbo, "PBO_HIGH")

    if not _finite_probability(evidence.psr):
        gates["psr"] = BLOCKED
        reasons.append("PSR_MISSING_OR_INVALID")
    else:
        hard_gate("psr", evidence.psr >= min_psr, "PSR_FAIL")

    if not _finite_probability(evidence.dsr):
        gates["dsr"] = BLOCKED
        reasons.append("DSR_MISSING_OR_INVALID")
    else:
        hard_gate("dsr", evidence.dsr >= min_dsr, "DSR_FAIL")

    if evidence.minimum_track_record is None or not math.isfinite(float(evidence.minimum_track_record)):
        gates["track_record"] = INCONCLUSIVE
        reasons.append("UNDERPOWERED")
    elif float(evidence.minimum_track_record) < 0:
        gates["track_record"] = BLOCKED
        reasons.append("INVALID_MINIMUM_TRACK_RECORD")
    elif evidence.actual_track_record < int(math.ceil(float(evidence.minimum_track_record))):
        gates["track_record"] = INCONCLUSIVE
        reasons.append("UNDERPOWERED")
    else:
        gates["track_record"] = PASS

    if not _finite_probability(evidence.power):
        gates["power"] = BLOCKED
        reasons.append("POWER_MISSING_OR_INVALID")
    elif evidence.power < min_power:
        gates["power"] = INCONCLUSIVE
        reasons.append("UNDERPOWERED")
    else:
        gates["power"] = PASS

    hard_gate("cost_robustness", evidence.cost_robust_pass, "COST_ROBUSTNESS_FAIL")
    hard_gate("holdout", evidence.holdout_status == "PASS", "HOLDOUT_NOT_PASS")

    if require_prospective:
        hard_gate("prospective", evidence.prospective_status == "PASS", "PROSPECTIVE_NOT_CONFIRMED")
    else:
        gates["prospective"] = PASS if evidence.prospective_status == "PASS" else INCONCLUSIVE

    for name, passed in sorted(evidence.additional_gates.items()):
        hard_gate(f"additional:{name}", bool(passed), f"ADDITIONAL_GATE_FAIL:{name}")

    if any(value == BLOCKED for value in gates.values()):
        status = BLOCKED
    elif any(value == FAIL for value in gates.values()):
        status = FAIL
    elif any(value == INCONCLUSIVE for key, value in gates.items() if key != "prospective"):
        status = INCONCLUSIVE
    else:
        status = "CERTIFIED_RESEARCH"

    return CertificationVerdict(
        status=status,
        reasons=tuple(dict.fromkeys(reasons)),
        gates=gates,
    )


def _blocked(reason: str) -> CertificationVerdict:
    return CertificationVerdict(status=BLOCKED, reasons=(reason,), gates={"preflight": BLOCKED})
