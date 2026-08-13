"""Fail-closed provenance validation for feed runtime artifacts."""

from __future__ import annotations

from typing import Any, Mapping

from core.runtime_boot_identity import RuntimeBootIdentity, get_runtime_boot_identity


def validate_feed_runtime_provenance(
    payload: Mapping[str, Any] | None,
    *,
    current_generation: int | None,
    current_identity: RuntimeBootIdentity | None = None,
) -> dict[str, Any]:
    """Validate runtime identity without accepting missing values as current."""
    data = dict(payload or {})
    identity = current_identity or get_runtime_boot_identity()
    reasons: list[str] = []

    run_id = str(data.get("run_id") or "").strip()
    if not run_id:
        reasons.append("missing_run_id")
    elif run_id != identity.run_id:
        reasons.append("run_id_mismatch")

    try:
        boot_epoch = float(data.get("boot_epoch"))
    except (TypeError, ValueError):
        boot_epoch = None
        reasons.append("missing_or_invalid_boot_epoch")
    if boot_epoch is not None and boot_epoch != float(identity.boot_epoch):
        reasons.append("boot_epoch_mismatch")

    raw_generation = data.get("recovery_generation_id")
    try:
        generation = int(raw_generation)
    except (TypeError, ValueError):
        generation = None
        reasons.append("missing_or_invalid_recovery_generation_id")
    if current_generation is None:
        reasons.append("missing_current_recovery_generation_id")
    elif generation is not None and generation != int(current_generation):
        reasons.append("recovery_generation_id_mismatch")

    return {
        "valid": not reasons,
        "reasons": reasons,
        "run_id": run_id or None,
        "boot_epoch": boot_epoch,
        "recovery_generation_id": generation,
        "current_run_id": identity.run_id,
        "current_boot_epoch": float(identity.boot_epoch),
        "current_recovery_generation_id": current_generation,
    }


__all__ = ["validate_feed_runtime_provenance"]
