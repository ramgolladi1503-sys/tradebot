from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any, Iterable

from core.data_quality import assess_candidate_data_quality


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _get_value(candidate: Any, field: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(field, default)
    return getattr(candidate, field, default)


def _candidate_snapshot(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return dict(candidate)
    if hasattr(candidate, "__dict__"):
        return dict(candidate.__dict__)
    return {}


def _update_candidate(candidate: Any, updates: dict[str, Any]) -> Any:
    if isinstance(candidate, dict):
        out = dict(candidate)
        out.update(updates)
        return out
    return replace(candidate, **updates)


def _candidate_source_flags(candidate: Any) -> dict[str, Any]:
    source_flags = _get_value(candidate, "source_flags", {}) or {}
    return dict(source_flags) if isinstance(source_flags, dict) else {}


def _candidate_theme(candidate: Any) -> str:
    source_flags = _candidate_source_flags(candidate)
    origin = source_flags.get("candidate_origin") if isinstance(source_flags.get("candidate_origin"), dict) else {}
    theme = (
        origin.get("setup_family")
        or source_flags.get("setup_family")
        or _get_value(candidate, "setup_family")
        or _get_value(candidate, "strategy")
        or "UNKNOWN"
    )
    return str(theme).strip().lower() or "unknown"


def _candidate_symbol(candidate: Any) -> str:
    symbol = _get_value(candidate, "symbol") or _get_value(candidate, "underlying") or "UNKNOWN"
    return str(symbol).strip().upper() or "UNKNOWN"


def _allocation_score(candidate: Any) -> float:
    return float(
        _safe_float(_get_value(candidate, "opportunity_score"))
        or _safe_float(_get_value(candidate, "gating_final_confidence"))
        or _safe_float(_get_value(candidate, "permission_confidence"))
        or _safe_float(_get_value(candidate, "builder_confidence"))
        or _safe_float(_get_value(candidate, "confidence"))
        or 0.0
    )


def _requested_capital(candidate: Any) -> float:
    requested = _safe_float(_get_value(candidate, "capital_at_risk"))
    if requested is not None and requested > 0:
        return float(requested)
    entry_price = _safe_float(_get_value(candidate, "entry_price")) or _safe_float(_get_value(candidate, "display_entry")) or 0.0
    qty = _safe_float(_get_value(candidate, "qty_units"))
    if qty is None or qty <= 0:
        qty = _safe_float(_get_value(candidate, "qty"))
    if qty is None or qty <= 0:
        qty = 1.0
    notional = float(entry_price) * float(qty)
    return max(0.0, notional)


def _data_truth_allocation_blocker(candidate: Any) -> str | None:
    result = assess_candidate_data_quality(_candidate_snapshot(candidate))
    if result.execution_truth_allowed:
        return None
    blockers = ",".join(result.execution_truth_blockers) if result.execution_truth_blockers else "unknown"
    return f"data_truth_block:{result.data_quality_grade}:{blockers}"


def _is_allocation_eligible(candidate: Any) -> bool:
    if _data_truth_allocation_blocker(candidate) is not None:
        return False
    selected = _get_value(candidate, "selected_for_execution")
    if selected is not None:
        return bool(selected)
    execution_allowed = bool(_get_value(candidate, "execution_allowed", False))
    tradable = bool(_get_value(candidate, "tradable", False))
    execution_entry = _safe_float(_get_value(candidate, "execution_entry"))
    execution_entry_status = str(_get_value(candidate, "execution_entry_status") or "").strip().lower()
    return bool(execution_allowed and tradable and execution_entry is not None and execution_entry_status == "executable")


def _annotate_default(candidate: Any) -> Any:
    source_flags = _candidate_source_flags(candidate)
    source_flags.setdefault("allocation_scope", "capital_allocator")
    result = assess_candidate_data_quality(_candidate_snapshot(candidate))
    source_flags.update(result.to_updates())
    current_size_mult = _safe_float(_get_value(candidate, "size_mult")) or 0.0
    return _update_candidate(
        candidate,
        {
            "slot_id": _get_value(candidate, "slot_id"),
            "allocation_reason": _get_value(candidate, "allocation_reason"),
            "allocation_score": round(_allocation_score(candidate), 6),
            "capital_assigned": _safe_float(_get_value(candidate, "capital_assigned")) or 0.0,
            "size_multiplier_effective": _safe_float(_get_value(candidate, "size_multiplier_effective")) or current_size_mult,
            "data_quality_grade": result.data_quality_grade,
            "execution_truth_allowed": result.execution_truth_allowed,
            "execution_truth_blockers": list(result.execution_truth_blockers),
            "fallback_fields": list(result.fallback_fields),
            "data_lineage": dict(result.lineage),
            "source_flags": source_flags,
        },
    )


def _apply_deferred(candidate: Any, *, reason: str, selection_reason: str | None = None) -> Any:
    source_flags = _candidate_source_flags(candidate)
    source_flags["allocation_reason"] = reason
    if selection_reason:
        source_flags["ranking_selection_reason"] = selection_reason
    updates = {
        "slot_id": None,
        "allocation_reason": reason,
        "allocation_score": round(_allocation_score(candidate), 6),
        "capital_assigned": 0.0,
        "size_multiplier_effective": 0.0,
        "selected_for_execution": False,
        "source_flags": source_flags,
    }
    if selection_reason:
        updates["selection_reason"] = selection_reason
    return _update_candidate(candidate, updates)


def _apply_allocated(candidate: Any, *, slot_id: str, capital_assigned: float, selection_reason: str | None = None) -> Any:
    data_blocker = _data_truth_allocation_blocker(candidate)
    if data_blocker is not None:
        return _apply_deferred(candidate, reason=data_blocker, selection_reason="allocation_data_truth_block")
    source_flags = _candidate_source_flags(candidate)
    source_flags["allocation_reason"] = "allocated"
    source_flags["slot_id"] = slot_id
    current_size_mult = _safe_float(_get_value(candidate, "size_mult")) or 0.0
    updates = {
        "slot_id": slot_id,
        "allocation_reason": "allocated",
        "allocation_score": round(_allocation_score(candidate), 6),
        "capital_assigned": round(float(capital_assigned), 6),
        "size_multiplier_effective": round(float(current_size_mult), 6),
        "selected_for_execution": True,
        "source_flags": source_flags,
    }
    if selection_reason:
        updates["selection_reason"] = selection_reason
    return _update_candidate(candidate, updates)


def _build_state(candidate: Any, index: int, *, slot_id: str) -> dict[str, Any]:
    return {
        "index": int(index),
        "symbol": _candidate_symbol(candidate),
        "theme": _candidate_theme(candidate),
        "score": float(_allocation_score(candidate)),
        "capital": float(_requested_capital(candidate)),
        "slot_id": slot_id,
        "trade_id": str(_get_value(candidate, "trade_id") or _get_value(candidate, "trade_key") or f"candidate-{index}"),
    }


def _fits_constraints(
    states: list[dict[str, Any]],
    candidate_state: dict[str, Any],
    *,
    max_slots: int,
    per_symbol_cap: int,
    per_theme_cap: int,
    capital_budget_cap: float | None,
) -> bool:
    all_states = list(states) + [candidate_state]
    if len(all_states) > max_slots:
        return False
    symbol_counts = Counter(state["symbol"] for state in all_states)
    if per_symbol_cap > 0 and symbol_counts[candidate_state["symbol"]] > per_symbol_cap:
        return False
    theme_counts = Counter(state["theme"] for state in all_states)
    if per_theme_cap > 0 and theme_counts[candidate_state["theme"]] > per_theme_cap:
        return False
    if capital_budget_cap is not None:
        total_capital = sum(float(state["capital"]) for state in all_states)
        if total_capital > capital_budget_cap:
            return False
    return True


def _candidate_slot_conflicts(
    allocated_states: list[dict[str, Any]],
    candidate_state: dict[str, Any],
    *,
    max_slots: int,
    per_symbol_cap: int,
    per_theme_cap: int,
    capital_budget_cap: float | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    reasons: list[str] = []
    pool: dict[int, dict[str, Any]] = {}
    if max_slots > 0 and len(allocated_states) >= max_slots:
        reasons.append("deferred_slot_cap")
        for state in allocated_states:
            pool[state["index"]] = state
    if per_symbol_cap > 0:
        symbol_matches = [state for state in allocated_states if state["symbol"] == candidate_state["symbol"]]
        if len(symbol_matches) >= per_symbol_cap:
            reasons.append("deferred_per_symbol_cap")
            for state in symbol_matches:
                pool[state["index"]] = state
    if per_theme_cap > 0:
        theme_matches = [state for state in allocated_states if state["theme"] == candidate_state["theme"]]
        if len(theme_matches) >= per_theme_cap:
            reasons.append("deferred_per_theme_cap")
            for state in theme_matches:
                pool[state["index"]] = state
    if capital_budget_cap is not None:
        current_budget = sum(float(state["capital"]) for state in allocated_states)
        if current_budget + float(candidate_state["capital"]) > capital_budget_cap:
            reasons.append("deferred_budget_cap")
            for state in allocated_states:
                pool[state["index"]] = state
    return reasons, list(pool.values())


def allocate_capital_slots(
    candidates: Iterable[Any],
    *,
    max_slots: int,
    per_symbol_cap: int,
    per_theme_cap: int,
    capital_budget_cap: float | None,
    minimum_quality_threshold: float,
    replacement_enabled: bool,
    replacement_min_delta: float,
) -> list[Any]:
    candidate_list = [_annotate_default(candidate) for candidate in list(candidates or [])]
    allocated_states: list[dict[str, Any]] = []
    next_slot_num = 1

    for index, candidate in enumerate(candidate_list):
        score = float(_allocation_score(candidate))
        current_selection_reason = str(_get_value(candidate, "selection_reason") or "").strip() or None
        data_blocker = _data_truth_allocation_blocker(candidate)
        if data_blocker is not None:
            candidate_list[index] = _apply_deferred(candidate, reason=data_blocker, selection_reason="allocation_data_truth_block")
            continue
        if not _is_allocation_eligible(candidate):
            candidate_list[index] = _apply_deferred(candidate, reason="not_selected_for_execution", selection_reason=current_selection_reason)
            continue
        if score < float(minimum_quality_threshold):
            candidate_list[index] = _apply_deferred(candidate, reason="below_minimum_quality", selection_reason="allocation_deferred")
            continue

        state = _build_state(candidate, index, slot_id=f"slot-{next_slot_num}")
        fits_directly = _fits_constraints(
            allocated_states,
            state,
            max_slots=max_slots,
            per_symbol_cap=per_symbol_cap,
            per_theme_cap=per_theme_cap,
            capital_budget_cap=capital_budget_cap,
        )
        if fits_directly:
            assigned_slot = state["slot_id"]
            candidate_list[index] = _apply_allocated(candidate, slot_id=assigned_slot, capital_assigned=state["capital"])
            allocated_states.append(_build_state(candidate_list[index], index, slot_id=assigned_slot))
            next_slot_num += 1
            continue

        reasons, replacement_pool = _candidate_slot_conflicts(
            allocated_states,
            state,
            max_slots=max_slots,
            per_symbol_cap=per_symbol_cap,
            per_theme_cap=per_theme_cap,
            capital_budget_cap=capital_budget_cap,
        )
        if replacement_enabled and replacement_pool:
            weakest = min(replacement_pool, key=lambda item: (float(item["score"]), item["slot_id"], item["trade_id"]))
            score_delta = float(state["score"]) - float(weakest["score"])
            replacement_states = [item for item in allocated_states if item["index"] != weakest["index"]]
            replacement_state = dict(state)
            replacement_state["slot_id"] = weakest["slot_id"]
            if score_delta >= float(replacement_min_delta) and _fits_constraints(
                replacement_states,
                replacement_state,
                max_slots=max_slots,
                per_symbol_cap=per_symbol_cap,
                per_theme_cap=per_theme_cap,
                capital_budget_cap=capital_budget_cap,
            ):
                replaced_candidate = candidate_list[weakest["index"]]
                replacement_reason = f"replaced_by_better_candidate:{state['trade_id']}"
                candidate_list[weakest["index"]] = _apply_deferred(
                    replaced_candidate,
                    reason=replacement_reason,
                    selection_reason="allocation_replaced",
                )
                candidate_list[index] = _apply_allocated(
                    candidate,
                    slot_id=weakest["slot_id"],
                    capital_assigned=replacement_state["capital"],
                )
                allocated_states = replacement_states + [_build_state(candidate_list[index], index, slot_id=weakest["slot_id"])]
                continue

        defer_reason = reasons[0] if reasons else "deferred_allocation"
        candidate_list[index] = _apply_deferred(candidate, reason=defer_reason, selection_reason="allocation_deferred")

    return candidate_list


def compute_desk_budgets(*, days: int, global_capital: float, desk_db_paths: dict) -> dict:
    budgets: dict[str, float] = {}
    notes: list[str] = []

    if not desk_db_paths:
        notes.append("no_desk_data")
    else:
        for desk_name in sorted(desk_db_paths):
            budgets[str(desk_name)] = 0.0
        notes.append("desk_data_not_loaded")

    return {
        "days": int(days),
        "global_capital": float(global_capital),
        "budgets": budgets,
        "notes": notes,
    }
