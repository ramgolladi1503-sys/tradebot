from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProfileRejectionSetupResult:
    detected: bool
    direction: str
    setup_score: float
    trigger_score: float
    entry_quality_score: float
    rr: float
    entry: float
    stop: float
    target: float
    telemetry: dict[str, Any]


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _candidate_get(candidate: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in candidate and candidate.get(key) is not None:
            return candidate.get(key)
    return None


def _normalize_direction(raw_value: Any) -> str:
    text = str(raw_value or "").strip().upper()
    if text in {"BUY_CALL", "CALL", "CE", "LONG_CALL", "BUY"}:
        return "BUY_CALL"
    if text in {"BUY_PUT", "PUT", "PE", "LONG_PUT"}:
        return "BUY_PUT"
    if "PUT" in text or text.endswith("PE"):
        return "BUY_PUT"
    return "BUY_CALL"


def _looks_like_profile_rejection(candidate: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    source_flags = candidate.get("source_flags")
    if not isinstance(source_flags, dict):
        source_flags = {}
    strategy_family = str(candidate.get("strategy_family") or "").strip().lower()
    setup_name = str(candidate.get("setup_name") or "").strip().lower()
    decision_playbook = str(candidate.get("decision_playbook") or "").strip().lower()
    explicit_detected = bool(candidate.get("profile_rejection_detected")) or bool(
        source_flags.get("profile_rejection_detected")
    )
    hinted = (
        strategy_family == "profile_rejection"
        or setup_name == "mean_reversion_profile_rejection"
        or decision_playbook == "profile_rejection"
        or explicit_detected
    )
    telemetry: dict[str, Any] = {
        "strategy_family": strategy_family,
        "setup_name": setup_name,
        "decision_playbook": decision_playbook,
        "explicit_detected": explicit_detected,
    }
    if hinted:
        telemetry["detection_source"] = "explicit_profile_rejection_identity"
        return True, telemetry
    telemetry["detection_source"] = "none"
    return False, telemetry


def _entry_levels(
    candidate: dict[str, Any], *, direction: str
) -> tuple[float | None, float | None, float | None]:
    entry = _safe_float(
        _candidate_get(candidate, "execution_entry", "display_entry", "entry", "opt_ltp", "current_ltp", "ltp")
    )
    stop = _safe_float(_candidate_get(candidate, "stop_loss", "stop", "stop_price"))
    target = _safe_float(_candidate_get(candidate, "target", "target_price"))
    if entry is None or entry <= 0:
        return None, stop, target
    if stop is None or target is None:
        if direction == "BUY_PUT":
            stop = stop if stop is not None else round(entry * 1.25, 3)
            target = target if target is not None else round(entry * 0.65, 3)
        else:
            stop = stop if stop is not None else round(entry * 0.75, 3)
            target = target if target is not None else round(entry * 1.35, 3)
    return entry, stop, target


def _rr(entry: float, stop: float, target: float) -> float:
    reward = abs(float(target) - float(entry))
    risk = max(abs(float(entry) - float(stop)), 1e-6)
    return float(reward / risk)


def evaluate_profile_rejection_setup(candidate: dict[str, Any]) -> ProfileRejectionSetupResult:
    if not isinstance(candidate, dict):
        return ProfileRejectionSetupResult(
            detected=False,
            direction="BUY_CALL",
            setup_score=0.0,
            trigger_score=0.0,
            entry_quality_score=0.0,
            rr=0.0,
            entry=0.0,
            stop=0.0,
            target=0.0,
            telemetry={"detection_source": "invalid_candidate"},
        )

    detected, telemetry = _looks_like_profile_rejection(candidate)
    direction = _normalize_direction(
        _candidate_get(candidate, "setup_direction", "direction", "side", "option_type", "right")
    )
    entry, stop, target = _entry_levels(candidate, direction=direction)
    if not detected or entry is None or stop is None or target is None:
        telemetry["detected"] = False
        telemetry["has_entry"] = bool(entry is not None)
        telemetry["has_stop"] = bool(stop is not None)
        telemetry["has_target"] = bool(target is not None)
        return ProfileRejectionSetupResult(
            detected=False,
            direction=direction,
            setup_score=0.0,
            trigger_score=0.0,
            entry_quality_score=0.0,
            rr=0.0,
            entry=float(entry or 0.0),
            stop=float(stop or 0.0),
            target=float(target or 0.0),
            telemetry=telemetry,
        )

    setup_score = max(
        float(_safe_float(candidate.get("setup_score")) or 0.0),
        float(_safe_float(candidate.get("profile_rejection_setup_score")) or 0.68),
    )
    trigger_score = max(
        float(_safe_float(candidate.get("trigger_score")) or 0.0),
        float(_safe_float(candidate.get("profile_rejection_trigger_score")) or 0.66),
    )
    entry_quality_score = max(
        float(_safe_float(candidate.get("entry_quality_score")) or 0.0),
        float(_safe_float(candidate.get("profile_rejection_entry_quality_score")) or 0.64),
    )
    rr_value = _rr(entry, stop, target)
    telemetry.update(
        {
            "detected": True,
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "target": target,
            "rr": rr_value,
        }
    )
    return ProfileRejectionSetupResult(
        detected=True,
        direction=direction,
        setup_score=float(setup_score),
        trigger_score=float(trigger_score),
        entry_quality_score=float(entry_quality_score),
        rr=float(rr_value),
        entry=float(entry),
        stop=float(stop),
        target=float(target),
        telemetry=telemetry,
    )

