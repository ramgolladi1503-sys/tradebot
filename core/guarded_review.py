from __future__ import annotations

from typing import Any, Mapping

from core.data_quality import assess_candidate_data_quality


EXECUTION_PERMISSION_VALUES = {"EXECUTE"}
EXECUTION_ACTION_VALUES = {"EXECUTE"}
EXECUTION_STATUS_VALUES = {"executable"}


def _entry_dict(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(entry or {})


def _is_execution_claim(entry: Mapping[str, Any]) -> bool:
    permission = str(entry.get("permission") or "").strip().upper()
    final_action = str(entry.get("final_action") or "").strip().upper()
    execution_status = str(entry.get("execution_status") or "").strip().lower()
    candidate_status = str(entry.get("candidate_status") or "").strip().lower()
    return bool(
        permission in EXECUTION_PERMISSION_VALUES
        or final_action in EXECUTION_ACTION_VALUES
        or execution_status in EXECUTION_STATUS_VALUES
        or candidate_status in EXECUTION_STATUS_VALUES
        or entry.get("execution_allowed")
        or entry.get("eligible_for_execution")
        or entry.get("selected_for_execution")
        or entry.get("is_executable")
    )


def enforce_review_data_truth(entry: Mapping[str, Any] | None) -> dict[str, Any]:
    """Downgrade review/final-action execution claims when data truth is dirty.

    This function is intentionally pure: it returns a new dict and does not write
    queues, approvals, orders, or files. It is safe to call immediately before a
    review row is emitted/saved/executed.
    """
    out = _entry_dict(entry)
    result = assess_candidate_data_quality(out)
    source_flags = dict(out.get("source_flags") or {})
    updates = result.to_updates()
    out.update(updates)
    source_flags.update({key: value for key, value in updates.items() if key != "source_flags"})
    out["source_flags"] = source_flags

    if result.execution_truth_allowed:
        out["review_data_truth_guard_applied"] = False
        out["source_flags"]["review_data_truth_guard_applied"] = False
        return out

    blockers = list(result.execution_truth_blockers)
    primary = blockers[0] if blockers else "data_truth_blocked"
    hard_execution_claim = _is_execution_claim(out)
    out["review_data_truth_guard_applied"] = True
    out["source_flags"]["review_data_truth_guard_applied"] = True
    out["execution_allowed"] = False
    out["eligible_for_execution"] = False
    out["selected_for_execution"] = False
    out["is_executable"] = False
    out["tradable"] = False
    out["capital_assigned"] = 0.0
    out["final_emit_block_reason"] = primary
    out["permission_reason"] = out.get("permission_reason") or primary
    out["primary_blocker"] = out.get("primary_blocker") or primary
    gates_failed = list(out.get("gates_failed") or [])
    for blocker in blockers:
        if blocker not in gates_failed:
            gates_failed.append(blocker)
    out["gates_failed"] = gates_failed
    warnings = list(out.get("warnings") or [])
    if "review_data_truth_execution_block" not in warnings:
        warnings.append("review_data_truth_execution_block")
    out["warnings"] = warnings

    if hard_execution_claim:
        out["permission"] = "BLOCK"
        out["final_action"] = "BLOCK"
        out["readiness"] = "BLOCKED"
        out["execution_status"] = "blocked"
        out["candidate_status"] = "blocked"
        out["final_blocker"] = out.get("final_blocker") or primary
    else:
        out["permission"] = "ADVISORY_ONLY"
        out["final_action"] = "ADVISORY_ONLY"
        out["readiness"] = "ADVISORY_ONLY"
        out["execution_status"] = "advisory_only"
        out["candidate_status"] = "advisory_only"
    return out
