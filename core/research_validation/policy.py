from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

PASS = "PASS"
FAIL = "FAIL"
INCONCLUSIVE = "INCONCLUSIVE"
BLOCKED = "BLOCKED"
POLICY_ID = "RESEARCH_CERT_V1"
MAX_PBO = 0.20
MIN_PSR = 0.95
MIN_DSR = 0.95
MIN_POWER = 0.80

@dataclass(frozen=True)
class CertificationInput:
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
    policy_id: str = POLICY_ID
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False
    append: bool = False

def _is_real_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))

def _finite_probability(value: object) -> bool:
    return _is_real_number(value) and 0.0 <= float(value) <= 1.0

def _is_plain_bool(value: object) -> bool:
    return type(value) is bool

def _is_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0

def certify_research(
    evidence: CertificationInput,
    *,
    max_pbo: float = MAX_PBO,
    min_psr: float = MIN_PSR,
    min_dsr: float = MIN_DSR,
    min_power: float = MIN_POWER,
    require_prospective: bool = False,
) -> CertificationVerdict:
    """Fail-closed research-only certification gate with locked v1 policy thresholds."""
    if (max_pbo, min_psr, min_dsr, min_power) != (MAX_PBO, MIN_PSR, MIN_DSR, MIN_POWER):
        return _blocked("POLICY_THRESHOLD_OVERRIDE_FORBIDDEN")
    if not isinstance(evidence.hypothesis_id, str) or not evidence.hypothesis_id.strip():
        return _blocked("MISSING_HYPOTHESIS_ID")
    if not _is_nonnegative_int(evidence.registered_experiments) or not _is_nonnegative_int(evidence.declared_experiments):
        return _blocked("INVALID_EXPERIMENT_COUNT")
    if evidence.registered_experiments < 1 or evidence.declared_experiments < 1:
        return _blocked("MISSING_EXPERIMENT_HISTORY")
    if evidence.declared_experiments != evidence.registered_experiments:
        return _blocked("SEARCH_HISTORY_INCOMPLETE")
    for value, reason in (
        (evidence.parameter_stability_pass, "INVALID_PARAMETER_STABILITY_FLAG"),
        (evidence.wfa_pass, "INVALID_WFA_FLAG"),
        (evidence.cost_robust_pass, "INVALID_COST_FLAG"),
        (evidence.inference_model_valid, "INVALID_INFERENCE_FLAG"),
        (evidence.search_history_complete, "INVALID_SEARCH_HISTORY_FLAG"),
    ):
        if not _is_plain_bool(value):
            return _blocked(reason)
    if not evidence.search_history_complete:
        return _blocked("SEARCH_HISTORY_INCOMPLETE")
    if not evidence.inference_model_valid:
        return _blocked("INFERENCE_MODEL_INVALID")
    if not _is_nonnegative_int(evidence.actual_track_record):
        return _blocked("INVALID_TRACK_RECORD")
    if not isinstance(evidence.holdout_status, str) or evidence.holdout_status not in {"PASS", "FAIL", "NOT_RUN"}:
        return _blocked("INVALID_HOLDOUT_STATUS")
    if not isinstance(evidence.prospective_status, str) or evidence.prospective_status not in {"PASS", "FAIL", "NOT_RUN"}:
        return _blocked("INVALID_PROSPECTIVE_STATUS")
    for name, value in evidence.additional_gates.items():
        if not isinstance(name, str) or not name.strip() or not _is_plain_bool(value):
            return _blocked("INVALID_ADDITIONAL_GATE")

    gates: dict[str, str] = {}
    reasons: list[str] = []
    def hard_gate(name: str, passed: bool, reason: str) -> None:
        gates[name] = PASS if passed else FAIL
        if not passed:
            reasons.append(reason)

    hard_gate("parameter_stability", evidence.parameter_stability_pass, "PARAMETER_FRAGILE")
    hard_gate("wfa", evidence.wfa_pass, "WFA_FAIL")
    for name, value, minimum, maximum, reason in (
        ("pbo", evidence.pbo, None, MAX_PBO, "PBO_HIGH"),
        ("psr", evidence.psr, MIN_PSR, None, "PSR_FAIL"),
        ("dsr", evidence.dsr, MIN_DSR, None, "DSR_FAIL"),
    ):
        if not _finite_probability(value):
            gates[name] = BLOCKED
            reasons.append(f"{name.upper()}_MISSING_OR_INVALID")
        else:
            passed = float(value) <= maximum if maximum is not None else float(value) >= minimum
            hard_gate(name, passed, reason)

    if evidence.minimum_track_record is None or not _is_real_number(evidence.minimum_track_record):
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
    elif float(evidence.power) < MIN_POWER:
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
        hard_gate(f"additional:{name}", passed, f"ADDITIONAL_GATE_FAIL:{name}")

    if any(v == BLOCKED for v in gates.values()): status = BLOCKED
    elif any(v == FAIL for v in gates.values()): status = FAIL
    elif any(v == INCONCLUSIVE for k, v in gates.items() if k != "prospective"): status = INCONCLUSIVE
    else: status = "CERTIFIED_RESEARCH"
    return CertificationVerdict(status=status, reasons=tuple(dict.fromkeys(reasons)), gates=gates)

def _blocked(reason: str) -> CertificationVerdict:
    return CertificationVerdict(status=BLOCKED, reasons=(reason,), gates={"preflight": BLOCKED})
