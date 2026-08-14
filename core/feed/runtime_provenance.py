"""Fail-closed provenance validation for feed runtime artifacts."""

from __future__ import annotations

from typing import Any, Mapping

from core.runtime_boot_identity import RuntimeBootIdentity, get_runtime_boot_identity


def validate_feed_runtime_provenance(
    payload: Mapping[str, Any] | None,
    *,
    current_feed_epoch: int | None,
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

    raw_feed_epoch = data.get("feed_epoch")
    try:
        feed_epoch = int(raw_feed_epoch)
    except (TypeError, ValueError):
        feed_epoch = None
        reasons.append("missing_or_invalid_feed_epoch")
    if current_feed_epoch is None:
        reasons.append("missing_current_feed_epoch")
    elif feed_epoch is not None and feed_epoch != int(current_feed_epoch):
        reasons.append("feed_epoch_mismatch")

    return {
        "valid": not reasons,
        "reasons": reasons,
        "run_id": run_id or None,
        "boot_epoch": boot_epoch,
        "feed_epoch": feed_epoch,
        "current_run_id": identity.run_id,
        "current_boot_epoch": float(identity.boot_epoch),
        "current_feed_epoch": current_feed_epoch,
    }


__all__ = ["validate_feed_runtime_provenance"]
