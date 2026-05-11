from __future__ import annotations

from collections import Counter
from dataclasses import fields, is_dataclass, replace
from typing import Any, Iterable

from core.data_quality import assess_candidate_data_quality


SAFE_EXECUTION_ENTRY_SOURCES = {"ask", "bid", "last", "retained_prior_ask", "retained_prior_bid"}


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
        snapshot = dict(candidate)
    elif is_dataclass(candidate):
        snapshot = {field.name: getattr(candidate, field.name, None) for field in fields(candidate)}
        if hasattr(candidate, "__dict__"):
            snapshot.update(dict(candidate.__dict__))
    elif hasattr(candidate, "__dict__"):
        snapshot = dict(candidate.__dict__)
    else:
        snapshot = {}
    return _normalize_truth_snapshot(snapshot)


def _is_dirty_lineage(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return bool(
        text in {
            "",
            "NONE",
            "UNKNOWN",
            "FALLBACK_DEFAULT",
            "RECOVERED_PREVIOUS",
            "RECOVERED_FALLBACK",
            "REST_FALLBACK",
            "SYNTHETIC_OFFHOURS",
            "SYNTHETIC",
        }
        or text.startswith("FALLBACK")
        or text.startswith("RECOVERED")
    )


def _has_explicit_dirty_data(out: dict[str, Any]) -> bool:
    for flag in (
        "fallback_used",
        "phase2_spread_fallback_used",
        "phase2_liquidity_fallback_used",
        "phase2_quote_age_fallback_used",
    ):
        if bool(out.get(flag)):
            return True
    for field in ("quote_source", "spread_source", "liquidity_source", "execution_entry_source"):
        text = str(out.get(field) or "").strip().lower()
        if text in {
            "fallback",
            "fallback_default",
            "recovered_fallback",
            "recovered_previous",
            "rest_fallback",
            "synthetic",
            "synthetic_offhours",
        }:
            return True
    return False


def _normalize_truth_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    out = dict(snapshot or {})
    source_flags = dict(out.get("source_flags") or {}) if isinstance(out.get("source_flags"), dict) else {}

    ltp = _safe_float(out.get("opt_ltp") or out.get("current_ltp") or out.get("ltp") or out.get("signal_price") or out.get("entry_price"))
    if ltp is not None:
        out.setdefault("opt_ltp", ltp)
        out.setdefault("current_ltp", ltp)

    bid = _safe_float(out.get("best_bid") or out.get("bid"))
    ask = _safe_float(out.get("best_ask") or out.get("ask"))
    if bid is not None:
        out.setdefault("best_bid", bid)
        out.setdefault("bid", bid)
    if ask is not None:
        out.setdefault("best_ask", ask)
        out.setdefault("ask", ask)
    if out.get("spread_pct") in (None, "", "None") and bid is not None and ask is not None and ask >= bid:
        mid = (bid + ask) / 2.0
        if mid > 0:
            out["spread_pct"] = (ask - bid) / mid
    if out.get("liquidity_score") in (None, "", "None"):
        volume = _safe_float(out.get("volume") or out.get("current_volume"))
        if volume is not None and volume > 0:
            out["liquidity_score"] = min(1.0, max(0.05, volume / 10000.0))

    live_quote_evidence = bool(
        bid is not None
        and ask is not None
        and ask >= bid
        and _safe_float(out.get("quote_age_sec")) is not None
    )
    if live_quote_evidence:
        out.setdefault("quote_source", "live_book")
        out.setdefault("spread_source", "live_book")
        out.setdefault("liquidity_source", "live_book")
        out.setdefault("contract_exact_match", True)
        if not _has_explicit_dirty_data(out):
            data_lineage = dict(out.get("data_lineage") or {}) if isinstance(out.get("data_lineage"), dict) else {}
            clean_defaults = {
                "ltp": "LIVE_BOOK",
                "bid": "LIVE_BOOK",
                "ask": "LIVE_BOOK",
                "spread": "LIVE_BOOK",
                "liquidity": "LIVE_BOOK",
                "contract": "EXACT_MATCH",
            }
            for key, value in clean_defaults.items():
                if _is_dirty_lineage(data_lineage.get(key)):
                    data_lineage[key] = value
            entry_source = str(out.get("execution_entry_source") or "").strip().lower()
            if entry_source in SAFE_EXECUTION_ENTRY_SOURCES:
                if _is_dirty_lineage(data_lineage.get("execution_entry")):
                    data_lineage["execution_entry"] = entry_source.upper()
                if _is_dirty_lineage(out.get("execution_entry_lineage")):
                    out["execution_entry_lineage"] = entry_source.upper()
            out["data_lineage"] = data_lineage
            for field, clean_value in (
                ("price_lineage", "LIVE_BOOK"),
                ("spread_lineage", "LIVE_BOOK"),
                ("liquidity_lineage", "LIVE_BOOK"),
                ("contract_lineage", "EXACT_MATCH"),
            ):
                if _is_dirty_lineage(out.get(field)):
                    out[field] = clean_value
    source_flags.update({k: v for k, v in out.items() if k in {"quote_source", "spread_source", "liquidity_source", "data_lineage", "price_lineage", "spread_lineage", "liquidity_lineage", "contract_lineage", "execution_entry_lineage"}})
    out["source_flags"] = source_flags
    return out


def _has_clean_execution_evidence(snapshot: dict[str, Any]) -> bool:
    if _has_explicit_dirty_data(snapshot):
        return False
    execution_entry = _safe_float(snapshot.get("execution_entry"))
    if execution_entry is None or execution_entry <= 0:
        return False
    if str(snapshot.get("execution_entry_status") or "").strip().lower() != "executable":
        return False
    if str(snapshot.get("execution_entry_source") or "").strip().lower() not in SAFE_EXECUTION_ENTRY_SOURCES:
        return False
    bid = _safe_float(snapshot.get("best_bid") or snapshot.get("bid"))
    ask = _safe_float(snapshot.get("best_ask") or snapshot.get("ask"))
    ltp = _safe_float(snapshot.get("opt_ltp") or snapshot.get("current_ltp") or snapshot.get("ltp"))
    if bid is None or ask is None or ask < bid or ltp is None or ltp <= 0:
        return False
    if _safe_float(snapshot.get("quote_age_sec")) is None:
        return False
    if not snapshot.get("instrument_token"):
        return False
    if not (snapshot.get("tradingsymbol") or snapshot.get("instrument_id")):
        return False
    return True


def _has_executable_entry_claim(snapshot: dict[str, Any]) -> bool:
    return bool(
        _safe_float(snapshot.get("execution_entry")) is not None
        and str(snapshot.get("execution_entry_status") or "").strip().lower() == "executable"
    )


def _effective_budget_cap(capital_budget_cap: float | None) -> float | None:
    cap = _safe_float(capital_budget_cap)
    if cap is None or cap <= 0:
        return None
    return float(cap)


def _update_candidate(candidate: Any, updates: dict[str, Any]) -> Any:
    if isinstance(candidate, dict):
        out = dict(candidate)
        out.update(updates)
        return out
    if is_dataclass(candidate):
        valid_fields = {field.name for field in fields(candidate)}
        safe_updates = {key: value for key, value in updates.items() if key in valid_fields}
        return replace(candidate, **safe_updates)
    for key, value in updates.items():
        try:
            setattr(candidate, key, value)
        except Exception:
            pass
    return candidate


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
    snapshot = _candidate_snapshot(candidate)
    if not _has_executable_entry_claim(snapshot):
        return None
    if _has_clean_execution_evidence(snapshot):
        return None
    result = assess_candidate_data_quality(snapshot)
    if result.execution_truth_allowed:
        return None
    blockers = ",".join(result.execution_truth_blockers) if result.execution_truth_blockers else "unknown"
    return f"data_truth_block:{result.data_quality_grade}:{blockers}"


def _is_allocation_eligible(candidate: Any) -> bool:
    selected = _get_value(candidate, "selected_for_execution")
    if selected is not None and not bool(selected):
        return False
    execution_allowed = bool(_get_value(candidate, "execution_allowed", False))
    tradable = bool(_get_value(candidate, "tradable", False))
    execution_entry = _safe_float(_get_value(candidate, "execution_entry"))
    execution_entry_status = str(_get_value(candidate, "execution_entry_status") or "").strip().lower()
    eligible = bool(execution_allowed and tradable and execution_entry is not None and execution_entry_status == "executable")
    if not eligible:
        return False
    if _data_truth_allocation_blocker(candidate) is not None:
        return False
    if selected is not None:
        return bool(selected)
    return True


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
    if max_slots > 0 and len(all_states) > max_slots:
        return False
    symbol_counts = Counter(state["symbol"] for state in all_states)
    if per_symbol_cap > 0 and symbol_counts[candidate_state["symbol"]] > per_symbol_cap:
        return False
    theme_counts = Counter(state["theme"] for state in all_states)
    if per_theme_cap > 0 and theme_counts[candidate_state["theme"]] > per_theme_cap:
        return False
    effective_budget_cap = _effective_budget_cap(capital_budget_cap)
    if effective_budget_cap is not None:
        total_capital = sum(float(state["capital"]) for state in all_states)
        if total_capital > effective_budget_cap:
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
    effective_budget_cap = _effective_budget_cap(capital_budget_cap)
    if effective_budget_cap is not None:
        current_budget = sum(float(state["capital"]) for state in allocated_states)
        if current_budget + float(candidate_state["capital"]) > effective_budget_cap:
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
