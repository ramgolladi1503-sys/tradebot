from __future__ import annotations

from dataclasses import fields as dataclass_fields, replace
from typing import Any

from config import config as cfg
from core.data_quality import EXECUTION_CRITICAL_FIELDS, assess_candidate_data_quality


def _candidate_field(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _candidate_field_names(candidate: Any) -> set[str]:
    try:
        return {field.name for field in dataclass_fields(candidate)}
    except Exception:
        return set()


def _candidate_snapshot(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return dict(candidate)
    payload: dict[str, Any] = {}
    try:
        for field in dataclass_fields(candidate):
            payload[field.name] = getattr(candidate, field.name, None)
    except Exception:
        if hasattr(candidate, "__dict__"):
            payload.update(dict(candidate.__dict__))
    if hasattr(candidate, "__dict__"):
        payload.update(dict(candidate.__dict__))
    return payload


def _normalize_code_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    elif value in (None, "", "None"):
        raw_items = []
    else:
        raw_items = [value]
    out: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def apply_candidate_updates(candidate: Any, updates: dict[str, Any]) -> Any:
    if not isinstance(updates, dict) or not updates:
        return candidate
    if isinstance(candidate, dict):
        out = dict(candidate)
        out.update(updates)
        return out

    field_names = _candidate_field_names(candidate)
    declared_updates = {key: value for key, value in updates.items() if key in field_names}
    extra_updates = {key: value for key, value in updates.items() if key not in field_names}
    out = candidate
    if declared_updates:
        try:
            out = replace(candidate, **declared_updates)
        except Exception:
            out = candidate
            for key, value in declared_updates.items():
                try:
                    object.__setattr__(out, key, value)
                except Exception:
                    continue

    if out is not candidate and hasattr(candidate, "__dict__"):
        for key, value in dict(candidate.__dict__).items():
            if key in field_names or key in updates:
                continue
            try:
                object.__setattr__(out, key, value)
            except Exception:
                continue

    for key, value in extra_updates.items():
        try:
            object.__setattr__(out, key, value)
        except Exception:
            continue
    return out


def _enforce_data_truth(candidate: Any) -> Any:
    """Attach canonical data-truth fields and downgrade unsafe execution claims.

    This is guard-mode wiring. It does not create trades. It only prevents a
    finalized candidate from continuing to claim executable/selected/capitalized
    status when execution-critical data is fallback, stale, missing, recovered,
    synthetic, or unknown.
    """
    payload = _candidate_snapshot(candidate)
    result = assess_candidate_data_quality(payload)
    source_flags = dict(_candidate_field(candidate, "source_flags", {}) or {})
    updates = result.to_updates()
    source_flags.update({key: value for key, value in updates.items() if key != "source_flags"})
    updates["source_flags"] = source_flags

    if not result.execution_truth_allowed:
        blockers = list(result.execution_truth_blockers)
        primary_blocker = blockers[0] if blockers else "data_truth_blocked"
        gates_failed = _normalize_code_list(_candidate_field(candidate, "gates_failed", []))
        warnings = _normalize_code_list(_candidate_field(candidate, "warnings", []))
        for blocker in blockers:
            if blocker not in gates_failed:
                gates_failed.append(blocker)
        if "data_truth_execution_block" not in warnings:
            warnings.append("data_truth_execution_block")
        candidate_status = str(_candidate_field(candidate, "candidate_status", "") or "").strip().lower()
        if candidate_status in {"", "executable", "ready", "selected"}:
            candidate_status = "data_invalid" if result.data_quality_grade == "F" else "advisory_only"
        updates.update(
            {
                "execution_allowed": False,
                "eligible_for_execution": False,
                "selected_for_execution": False,
                "is_executable": False,
                "capital_assigned": 0.0,
                "candidate_status": candidate_status,
                "primary_blocker": primary_blocker,
                "gates_failed": gates_failed,
                "warnings": warnings,
            }
        )
        source_flags.update(
            {
                "execution_allowed": False,
                "eligible_for_execution": False,
                "selected_for_execution": False,
                "is_executable": False,
                "capital_assigned": 0.0,
                "candidate_status": candidate_status,
                "primary_blocker": primary_blocker,
                "gates_failed": gates_failed,
                "warnings": warnings,
                "data_truth_guard_applied": True,
            }
        )
    else:
        source_flags["data_truth_guard_applied"] = False
    updates["source_flags"] = source_flags
    return apply_candidate_updates(candidate, updates)


def stamp_lifecycle_stage(candidate: Any, lifecycle_stage: str | None) -> Any:
    stage = str(lifecycle_stage or "").strip().lower() or None
    if not stage:
        return candidate
    source_flags = dict(_candidate_field(candidate, "source_flags", {}) or {})
    source_flags["lifecycle_stage"] = stage
    return apply_candidate_updates(
        candidate,
        {
            "lifecycle_stage": stage,
            "source_flags": source_flags,
        },
    )


def mirror_candidate_truth(
    candidate: Any,
    *,
    decision_trace: dict | None = None,
    lifecycle: dict | None = None,
    contract_resolution: dict | None = None,
    fallback_metadata: dict | None = None,
    lifecycle_stage: str | None = None,
) -> Any:
    if candidate is None:
        return candidate

    out = candidate
    updates: dict[str, Any] = {}
    source_flags = dict(_candidate_field(out, "source_flags", {}) or {})
    decision_trace_out = dict(_candidate_field(out, "decision_trace", {}) or {})

    if isinstance(lifecycle, dict):
        lifecycle_fields = {
            "execution_entry": lifecycle.get("execution_entry"),
            "execution_entry_source": lifecycle.get("execution_entry_source"),
            "execution_entry_status": lifecycle.get("execution_entry_status"),
            "display_entry": lifecycle.get("display_entry"),
            "display_entry_source": lifecycle.get("display_entry_source"),
            "display_entry_status": lifecycle.get("display_entry_status"),
            "entry": lifecycle.get("entry"),
            "entry_source": lifecycle.get("entry_source"),
            "entry_status": lifecycle.get("entry_status"),
            "entry_reason": lifecycle.get("entry_reason"),
            "entry_clear_reason": lifecycle.get("entry_clear_reason"),
            "entry_block_code": lifecycle.get("entry_block_code"),
        }
        updates.update({key: value for key, value in lifecycle_fields.items() if value is not None})
        source_flags["entry_status"] = lifecycle.get("entry_status")
        source_flags["execution_entry_status"] = lifecycle.get("execution_entry_status")

    if isinstance(contract_resolution, dict):
        contract_fields = {
            "requested_strike": contract_resolution.get("requested_strike"),
            "resolved_strike": contract_resolution.get("resolved_strike"),
            "requested_expiry": contract_resolution.get("requested_expiry"),
            "resolved_expiry": contract_resolution.get("resolved_expiry"),
            "contract_exact_match": contract_resolution.get("contract_exact_match"),
            "resolution_mode": contract_resolution.get("resolution_mode"),
            "resolution_penalty": contract_resolution.get("resolution_penalty"),
            "fallback_used": contract_resolution.get("fallback_used"),
            "fallback_class": contract_resolution.get("fallback_class"),
            "fallback_reason": contract_resolution.get("fallback_reason"),
            "fallback_execution_policy": contract_resolution.get("fallback_execution_policy"),
            "tradingsymbol": contract_resolution.get("tradingsymbol"),
            "instrument_token": contract_resolution.get("instrument_token"),
            "instrument_id": contract_resolution.get("instrument_id"),
            "expiry": contract_resolution.get("resolved_expiry"),
            "expiry_date": contract_resolution.get("resolved_expiry"),
        }
        updates.update({key: value for key, value in contract_fields.items() if value is not None})
        source_flags["contract_resolution"] = dict(contract_resolution)

    if isinstance(fallback_metadata, dict):
        fallback_fields = {
            "fallback_used": fallback_metadata.get("fallback_used"),
            "fallback_class": fallback_metadata.get("fallback_class"),
            "fallback_reason": fallback_metadata.get("fallback_reason"),
            "fallback_execution_policy": fallback_metadata.get("fallback_execution_policy"),
        }
        updates.update({key: value for key, value in fallback_fields.items() if value is not None})
        if fallback_metadata.get("fallback_reason") is not None:
            source_flags["fallback_reason"] = fallback_metadata.get("fallback_reason")
        if fallback_metadata.get("fallback_class") is not None:
            source_flags["fallback_class"] = fallback_metadata.get("fallback_class")
        if fallback_metadata.get("fallback_used") is not None:
            source_flags["fallback_used"] = bool(fallback_metadata.get("fallback_used"))

    if isinstance(decision_trace, dict):
        decision_trace_out.update(dict(decision_trace))

    if decision_trace_out:
        updates["decision_trace"] = decision_trace_out
        rank_score = _candidate_field(out, "rank_score")
        if rank_score in (None, "", "None") and decision_trace_out.get("rank_score") is not None:
            updates["rank_score"] = _candidate_field(decision_trace_out, "rank_score")
        opportunity_score = _candidate_field(out, "opportunity_score")
        if opportunity_score in (None, "", "None") and decision_trace_out.get("opportunity_score") is not None:
            updates["opportunity_score"] = _candidate_field(decision_trace_out, "opportunity_score")
        final_score = _candidate_field(out, "final_score")
        if final_score in (None, "", "None") and decision_trace_out.get("final_score") is not None:
            updates["final_score"] = _candidate_field(decision_trace_out, "final_score")
        permission = str(
            decision_trace_out.get("permission")
            or decision_trace_out.get("preliminary_permission")
            or _candidate_field(out, "permission")
            or ""
        ).strip().upper() or None
        permission_reason = str(
            decision_trace_out.get("permission_reason")
            or decision_trace_out.get("preliminary_permission_reason")
            or _candidate_field(out, "permission_reason")
            or ""
        ).strip() or None
        final_action = str(
            decision_trace_out.get("final_action")
            or _candidate_field(out, "final_action")
            or ""
        ).strip().upper() or None
        readiness = str(
            decision_trace_out.get("readiness")
            or _candidate_field(out, "readiness")
            or ""
        ).strip().upper() or None
        execution_status = str(
            decision_trace_out.get("execution_status")
            or _candidate_field(out, "execution_status")
            or ""
        ).strip().lower() or None
        execution_allowed = decision_trace_out.get("exec_allowed")
        if execution_allowed is None:
            execution_allowed = decision_trace_out.get("execution_allowed")
        execution_entry_status = str(
            decision_trace_out.get("execution_entry_status")
            or _candidate_field(out, "execution_entry_status")
            or ""
        ).strip().lower() or None
        candidate_status = str(
            decision_trace_out.get("candidate_status")
            or _candidate_field(out, "candidate_status")
            or ""
        ).strip().lower() or None
        gates_failed = _normalize_code_list(
            decision_trace_out.get("gates_failed")
            or _candidate_field(out, "gates_failed")
            or []
        )
        warnings = _normalize_code_list(
            decision_trace_out.get("warnings")
            or _candidate_field(out, "warnings")
            or []
        )
        updates.update(
            {
                "permission": permission,
                "permission_reason": permission_reason,
                "final_action": final_action,
                "readiness": readiness,
                "execution_status": execution_status,
                "execution_allowed": bool(execution_allowed) if execution_allowed is not None else None,
                "execution_entry_status": execution_entry_status,
                "candidate_status": candidate_status,
                "gates_failed": gates_failed,
                "warnings": warnings,
            }
        )
        source_flags.update(
            {
                "permission": permission,
                "permission_reason": permission_reason,
                "final_action": final_action,
                "readiness": readiness,
                "execution_status": execution_status,
                "execution_allowed": bool(execution_allowed) if execution_allowed is not None else None,
                "execution_entry_status": execution_entry_status,
                "candidate_status": candidate_status,
                "gates_failed": gates_failed,
                "warnings": warnings,
            }
        )

    if lifecycle_stage:
        stage = str(lifecycle_stage or "").strip().lower() or None
        if stage:
            updates["lifecycle_stage"] = stage
            source_flags["lifecycle_stage"] = stage

    if _candidate_field(out, "rank_score") is not None:
        updates.setdefault("rank_score", _candidate_field(out, "rank_score"))
    if _candidate_field(out, "opportunity_score") is not None:
        updates.setdefault("opportunity_score", _candidate_field(out, "opportunity_score"))
    if _candidate_field(out, "final_score") is not None:
        updates.setdefault("final_score", _candidate_field(out, "final_score"))
    if _candidate_field(out, "selected_for_execution") is not None:
        updates.setdefault("selected_for_execution", _candidate_field(out, "selected_for_execution"))
    if _candidate_field(out, "selection_reason") is not None:
        updates.setdefault("selection_reason", _candidate_field(out, "selection_reason"))

    if source_flags:
        if decision_trace_out:
            source_flags["decision_trace"] = decision_trace_out
        updates["source_flags"] = source_flags
    return _enforce_data_truth(apply_candidate_updates(out, updates))


def assert_ranked_candidate_ready(candidate: Any) -> None:
    if not bool(getattr(cfg, "CANDIDATE_FINALIZATION_ASSERT_ENABLE", True)):
        return
    required = (
        "trade_id",
        "symbol",
        "strategy_family",
        "candidate_status",
        "confidence",
        "rank_score",
    )
    missing = [
        field
        for field in required
        if _candidate_field(candidate, field) in (None, "", "None")
    ]
    if missing:
        raise AssertionError(f"ranked candidate missing required fields: {','.join(missing)}")


def assert_executable_candidate_ready(candidate: Any) -> None:
    if not bool(getattr(cfg, "CANDIDATE_FINALIZATION_ASSERT_ENABLE", True)):
        return
    required = (
        "trade_id",
        "symbol",
        "strategy_family",
        "candidate_status",
        "confidence",
        "rank_score",
        "permission",
        "final_action",
        "execution_allowed",
        "execution_entry_status",
    )
    missing = [
        field
        for field in required
        if _candidate_field(candidate, field) in (None, "", "None")
    ]
    if missing:
        raise AssertionError(f"executable candidate missing required fields: {','.join(missing)}")

    result = assess_candidate_data_quality(_candidate_snapshot(candidate))
    if not result.execution_truth_allowed:
        raise AssertionError(
            "executable candidate failed data truth: " + ",".join(result.execution_truth_blockers)
        )
    if result.data_quality_grade not in {"A", "B"}:
        raise AssertionError(f"executable candidate has non-executable data grade: {result.data_quality_grade}")
    dirty_fallback_fields = sorted(set(result.fallback_fields).intersection(EXECUTION_CRITICAL_FIELDS))
    if dirty_fallback_fields:
        raise AssertionError(
            "executable candidate has fallback execution-critical fields: "
            + ",".join(dirty_fallback_fields)
        )
