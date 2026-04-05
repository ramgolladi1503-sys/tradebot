from __future__ import annotations

from typing import Any

from core.threshold_audit import classify_rejection_metadata

_STAGE_PRIORITY: dict[str, int] = {
    "setup": 10,
    "trigger": 20,
    "entry_quality": 30,
    "family_survival": 40,
    "risk_budget": 50,
    "portfolio_heat": 60,
    "kill_switch": 70,
    "selector": 80,
}

_STAGE_OWNER: dict[str, str] = {
    "setup": "builder",
    "trigger": "builder",
    "entry_quality": "builder",
    "family_survival": "builder",
    "risk_budget": "risk_engine",
    "portfolio_heat": "risk_engine",
    "kill_switch": "risk_engine",
    "selector": "opportunity_engine",
}


def _normalize_meta(stage: Any, reason: Any) -> dict[str, Any]:
    return classify_rejection_metadata(
        reason,
        rejected_at_stage=stage,
    )


def _priority(stage: Any) -> int:
    normalized = str(stage or "").strip().lower()
    return int(_STAGE_PRIORITY.get(normalized, 999))


def normalize_rejection_stage(record: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(record or {})
    existing_meta = _normalize_meta(
        payload.get("existing_rejected_at_stage"),
        payload.get("existing_rejection_reason_code"),
    )
    incoming_meta = _normalize_meta(
        payload.get("incoming_rejected_at_stage", payload.get("rejected_at_stage")),
        payload.get("incoming_rejection_reason_code", payload.get("rejection_reason_code")),
    )

    existing_present = bool(
        existing_meta.get("rejected_at_stage") or existing_meta.get("rejection_reason_code")
    )
    incoming_present = bool(
        incoming_meta.get("rejected_at_stage") or incoming_meta.get("rejection_reason_code")
    )

    if existing_present and incoming_present:
        existing_priority = _priority(existing_meta.get("rejected_at_stage"))
        incoming_priority = _priority(incoming_meta.get("rejected_at_stage"))
        if existing_priority <= incoming_priority:
            chosen = existing_meta
        else:
            chosen = incoming_meta
    elif existing_present:
        chosen = existing_meta
    else:
        chosen = incoming_meta

    conflict = False
    if existing_present and incoming_present:
        conflict = (
            existing_meta.get("rejected_at_stage") != incoming_meta.get("rejected_at_stage")
            or existing_meta.get("rejection_reason_code") != incoming_meta.get("rejection_reason_code")
        )

    chosen_stage = str(chosen.get("rejected_at_stage") or "").strip().lower() or None
    return {
        "rejected_at_stage": chosen_stage,
        "rejection_reason_code": chosen.get("rejection_reason_code"),
        "rejection_bucket": chosen.get("rejection_bucket"),
        "rejection_severity": chosen.get("rejection_severity"),
        "stage_authority_owner": _STAGE_OWNER.get(chosen_stage or "", "unknown"),
        "stage_authority_warning": bool(conflict),
    }


def apply_stage_authority(record: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(record or {})
    payload.update(normalize_rejection_stage(payload))
    return payload
